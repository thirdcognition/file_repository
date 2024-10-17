import asyncio
import json
import os
import textwrap
from pydantic import BaseModel, Field
import yaml
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import (
    SystemMessage,
)
from langchain_core.prompts.chat import HumanMessagePromptTemplate

# Load environment variables from .env file
load_dotenv()

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
files_dir = os.path.join(script_dir, "../files")

# Load logos.yaml from the same directory
with open(os.path.join(files_dir, "icons.yaml"), "r") as file:
    logos: dict = yaml.safe_load(file)

# Load templates.json from the same directory
with open(os.path.join(files_dir, "templates.json"), "r") as file:
    templates = json.load(file)

logos_prompt = """
You are a helpful assistant that chooses an logo for a given module based on its description.



Only 1 logo should be chosen and use the id of the logo for the assignment.
"""

logo_message_template = """
Content:
{content}

Use the following logos to choose the most appropriate logo for the module:
{available_logos}

Task:
Find 5 logos that best represents the content from the previously defined list.
The logos should be ordered and chosen based on which description matches the content best.

If there's no logo that matches the content, return "no_logo" as id.

Follow the format instructions exactly.

Format:
{format_instructions}
"""

prompt = ChatPromptTemplate.from_messages(
    [
        SystemMessage(content=logos_prompt),
        HumanMessagePromptTemplate.from_template(logo_message_template),
    ]
)


# Initialize Azure OpenAI
llm = AzureChatOpenAI(
    azure_deployment=os.getenv("AZURE_MODEL"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    model_kwargs={"response_format": {"type": "json_object"}},
    timeout=60000,
    request_timeout=120,
    max_tokens=os.getenv("AZURE_OUT_CTX_SIZE"),
    max_retries=2,
    verbose=True,
    temperature=0.1,
)


class LogoType(BaseModel):
    reasoning: str = Field(description="Reasoning for the selected logo")
    logo: str = Field(description="ID of the selected logo, e.g. 'logo_1'")


class LogoTypeList(BaseModel):
    considered_logos: str = Field(
        description="Consider and think which of the logos would fit the best for the criteria."
    )
    logos: list[LogoType] = Field(description="List of selected logos with reasoning")


# Initialize the parser
parser = PydanticOutputParser(pydantic_object=LogoTypeList)

# Create a chain
chain = prompt | llm | parser

used_logos: dict[str, set] = {}


def reset_all_used_logos():
    global used_logos
    used_logos = {}


def reset_used_logos(journey_id):
    global used_logos
    used_logos[journey_id] = set()


def in_used_logos(journey_id, logo):
    global used_logos
    return logo in used_logos.get(journey_id, set())


def add_used_logos(journey_id, logo):
    global used_logos
    if journey_id not in used_logos:
        used_logos[journey_id] = set()
    used_logos[journey_id].add(logo)


def get_used_logos(journey_id):
    global used_logos
    return used_logos.get(journey_id, set())


async def invoke_chain(actions, journey, exclude_used_logos=False):
    if exclude_used_logos:
        available_logos = "\n\n".join(
            [
                f"ID: {logo}\nUsecases: {description['use_case']}\nDescription: {description['description']}\n\n"
                for logo, description in logos["saas_product_icon"].items()
                if not in_used_logos(journey, logo)
            ]
        )
    else:
        available_logos = "\n\n".join(
            [
                f"ID: {logo}\nUsecases: {description['use_case']}\nDescription: {description['description']}\n\n"
                for logo, description in logos["saas_product_icon"].items()
            ]
        )

    response = await chain.ainvoke(
        {
            "content": "\n\n".join(
                [
                    textwrap.dedent(
                        f"""
                        Title: {action["description"].replace("\n", " ").strip()}
                        Description:
                        {action["content"]}
                        Action: {action["action"].replace("\n", " ").strip()}
                        """
                    )
                    for action in actions
                ]
            ),
            "available_logos": available_logos,
            "format_instructions": parser.get_format_instructions(),
        }
    )
    return response

async def invoke_chain_with_converted_item(converted_items):
    available_logos = "\n\n".join(
        [
            f"ID: {logo}\nUsecases: {description['use_case']}\nDescription: {description['description']}\n\n"
            for logo, description in logos["saas_product_icon"].items()
        ]
    )

    response = await chain.ainvoke(
        {
            "content": "\n\n".join(
                [
                    textwrap.dedent(
                        f"""
                        Title: {item.title.replace("\n", " ").strip()}
                        Description:
                        {item.description or ''}
                        Action: {item.action or ''}
                        """
                    )
                    for item in converted_items
                ]
            ),
            "available_logos": available_logos,
            "format_instructions": parser.get_format_instructions(),
        }
    )
    return response

async def process_logos(
    actions,
    journey,
    exclude_used_logos_flag,
    max_retries=None,
    retries=None,
    debug_cb=None,
):

    logo = None
    response = await invoke_chain(
        actions, journey, exclude_used_logos=exclude_used_logos_flag
    )

    for logo_info in response.logos:
        stripped_logo = logo_info.logo.strip()

        if (
            logo is None
            and not in_used_logos(journey, stripped_logo)
            and stripped_logo in logos["saas_product_icon"].keys()
        ):
            logo = logo_info
            add_used_logos(journey, stripped_logo)

            if not exclude_used_logos_flag:
                break

        elif logo is None and stripped_logo == "no_logo":
            logo = logo_info

    if logo is None or (exclude_used_logos_flag and logo.logo.strip() == "no_logo"):
        if exclude_used_logos_flag and debug_cb is not None:
            if logo is None:
                debug_cb(retries, [logo.logo.strip() for logo in response.logos])
            elif logo.logo.strip() == "no_logo":
                retries = max_retries
        else:
            logo = response.logos[0]

    return logo, retries


async def assign_icons(journey, section, modules):
    max_retries = 3

    for module, actions in modules.items():
        # Run the chain

        logo: LogoType = None
        retries = 0
        response: LogoTypeList = None

        def debug_callback(retries, tried_logos):
            print(
                f"    {journey[:15]} -> {section[:15]}: "
                f"Seek ({retries}) for {module} (tried: {', '.join(tried_logos)})"
            )

        while (
            len(get_used_logos(journey)) == 0
            or logo is None
            or in_used_logos(journey, logo.logo.strip())
            or logo.logo.strip() == "no_logo"
        ) and retries < max_retries:
            retries += 1
            logo, retries = await process_logos(
                actions,
                journey,
                exclude_used_logos_flag=True,
                max_retries=max_retries,
                retries=retries,
                debug_cb=debug_callback,
            )

            if logo and logo.logo.strip() != "no_logo":
                break

        if logo is None or logo.logo.strip() == "no_logo":
            print(
                f"    {journey[:15]} -> {section[:15]}: "
                "Failed to find logo, giving access to all logos."
            )
            logo, _ = await process_logos(
                actions, journey, exclude_used_logos_flag=False
            )

        # The response will now be an instance of LogoType
        for action in actions:
            action["logo"] = logo.logo.strip()

        logo_details = logos["saas_product_icon"].get(
            logo.logo.strip(),
            {
                "description": "No description available",
                "use_case": "No usecase available",
            },
        )
        print(
            f"    {journey[:15]} -> {section[:15]} -> {module}:"
            f"\n\tChose logo: {logo.logo.strip()}"
            f"\n\tDescription: {' '.join(textwrap.wrap(logo_details['description'], width=70))}"
            f"\n\tUse case: {' '.join(textwrap.wrap(logo_details['use_case'], width=70))}"
            f"\n\tReason: {' '.join(textwrap.wrap(logo.reasoning, width=70))}"
            f"\n\tConsiderations: {' '.join(textwrap.wrap(response.considered_logos, width=70))}...\n\n"
        )


# journey = next(iter(templates))
# section = next(iter(templates[journey]))
# module = next(iter(templates[journey][section]))
# action = templates[journey][section][module][0]


all_logos_used = set()


async def main():
    global all_logos_used
    reset_all_used_logos()
    for journey, sections in templates.items():
        print(f"Start journey: {journey}")
        reset_used_logos(journey)
        for section, modules in sections.items():
            tasks = []
            print(f"  Start section: {section}")
            for module, actions in modules.items():
                if isinstance(actions, dict):
                    actions = [actions]
                    templates[journey][section][module] = actions

            tasks.append(assign_icons(journey, section, modules))
            # else:
            #     for action in actions:
            #         tasks.append(assign_icons(action))
            await asyncio.gather(*tasks)
            print(
                f"  End section: {section}\n\tUsed logos so far: {", ".join(get_used_logos(journey))}"
            )
            all_logos_used.update(used_logos)
        print(
            f"End journey: {journey}\n\tUsed logos: {", ".join(get_used_logos(journey))}"
        )


asyncio.run(main())

print(f"All logos used: {', '.join(all_logos_used)}")
print(f"Logos not used: {', '.join(set(logos.keys()) - all_logos_used)}")

# Perform a json dump
response_json = json.dumps(templates, indent=2)  # .model_dump_json(indent=2)
# print(response_json)

# Save templates into templates_new.json
with open(os.path.join(files_dir, "templates_new.json"), "w") as file:
    json.dump(templates, file, indent=2)
