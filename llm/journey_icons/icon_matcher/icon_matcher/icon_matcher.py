import asyncio
import json
import os
from pydantic import BaseModel, Field
import yaml
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnableLambda, RunnablePassthrough
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

# Load logos.yaml from the same directory
with open(os.path.join(script_dir, "icons.yaml"), "r") as file:
    logos: dict = yaml.safe_load(file)

# Load templates.json from the same directory
with open(os.path.join(script_dir, "templates.json"), "r") as file:
    templates = json.load(file)
logos_prompt = (
    """
You are a helpful assistant that chooses an logo for a given module based on its description.

Use the following logos to choose the most appropriate logo for the module:
"""
    + "\n\n".join(
        [
            f"{logo}: {description['use_case']}"
            for logo, description in logos["saas_product_icon"].items()
        ]
    )
    + """

Only 1 logo should be chosen and use the id of the logo for the assignment.
"""
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


class IconType(BaseModel):
    reasoning: str = Field(description="Reasoning for the selected icon")
    logo: str = Field(description="ID of the selected logo")


# Initialize the parser
parser = PydanticOutputParser(pydantic_object=IconType)


async def perform_action(action):
    # print(f"Performing action:\n{json.dumps(action, indent=2)}")
    # print("Seeking logo for: "+action["description"])

    # Define a prompt template with system prompt
    template = """
    Title: {title}
    Content: {content}
    Action: {action}
    Answer: Let's think step by step and return the answer in the defined format.
    {format_instructions}
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=logos_prompt),
            HumanMessagePromptTemplate.from_template(template),
        ]
    )

    # Create a chain
    chain = prompt | llm | parser

    # Run the chain
    response: IconType = await chain.ainvoke(
        {
            "title": action["description"],
            "content": action["content"],
            "action": action["action"],
            "format_instructions": parser.get_format_instructions(),
        }
    )

    # The response will now be an instance of IconType
    # print(response.model_dump_json(indent=2))
    action["logo"] = response.logo
    print(
        action["description"]
        + "\nChose logo: "
        + response.logo
        + " \nfor reason: "
        + response.reasoning
        + "\n\n"
    )


# journey = next(iter(templates))
# section = next(iter(templates[journey]))
# module = next(iter(templates[journey][section]))
# action = templates[journey][section][module][0]


async def main():
    for journey, sections in templates.items():
        for section, modules in sections.items():
            for module, actions in modules.items():
                tasks = []
                if isinstance(actions, dict):
                    tasks.append(perform_action(actions))
                else:
                    for action in actions:
                        tasks.append(perform_action(action))
                await asyncio.gather(*tasks)


asyncio.run(main())

# Perform a json dump
response_json = json.dumps(templates, indent=2)  # .model_dump_json(indent=2)
# print(response_json)

# Save templates into templates_new.json
with open(os.path.join(script_dir, "templates_new.json"), "w") as file:
    json.dump(templates, file, indent=2)
