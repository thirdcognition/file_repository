import asyncio
import os
import json
import re
import textwrap
import asyncio
from typing import Iterable
from pydantic import BaseModel, Field
from enum import Enum
import uuid

from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import (
    SystemMessage,
)
from langchain_core.prompts.chat import HumanMessagePromptTemplate

# from langchain_core.rate_limiters import InMemoryRateLimiter

from icon_matcher.icon_matcher import (
    LogoTypeList,
    invoke_chain_with_converted_item,
    rate_limiter,
)


load_dotenv()

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
files_dir = os.path.join(script_dir, "../files")

used_ids = set()


# Prompt Definitions
content_prompt = """
You are an assistant that processes ContentItems to identify missing details.
You'll receive a ContentItem with some fields already populated and all of it's childrens details.
Your task is to populate remaining fields using the given data from children.
Follow the style with which the children fields have been populated. Especially adhering to
Content Instructions' role and topic.
Do not start with phrases like "This [item] provides...", "Effective [detail] ...", or
anything similar when writing content for the item.
Do not use words like Effective, Clear, Essential, etc. Use normal descriptive language.
Do not describe what you're doing or what should be done, just provide the output.
The output content should be understandable and human readable as is.
"""

content_message_template = """
Content from children:
{child_content}

Already available content:
{content_information}

Process the content and fill in any missing fields. Consider the titles, icons, and contents of children and their descendants.

Do not start with phrases like "This [item] provides...", "Effective [detail] ...", or
anything similar when writing content for the item.
Do not use words like Effective, Clear, Essential, etc. Use normal descriptive language.
Do not describe what you're doing or what should be done, just provide the output.

The output content should be understandable, approacable and human readable.

Format:
{format_instructions}
"""

# Define the ChatPromptTemplate using the above templates
content_prompt_template = ChatPromptTemplate.from_messages(
    [
        SystemMessage(content=content_prompt),
        HumanMessagePromptTemplate.from_template(content_message_template),
    ]
)

# rate_limiter = InMemoryRateLimiter(
#     requests_per_second=2,  # <-- Super slow! We can only make a request once every 10 seconds!!
#     check_every_n_seconds=0.1,  # Wake up every 100 ms to check whether allowed to make a request,
#     max_bucket_size=2,  # Controls the maximum burst size.
# )

# Define the Azure OpenAI instance
content_llm = AzureChatOpenAI(
    azure_deployment=os.getenv("AZURE_MODEL"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    model_kwargs={"response_format": {"type": "json_object"}},
    timeout=60000,
    request_timeout=120,
    max_tokens=os.getenv("AZURE_OUT_CTX_SIZE"),
    max_retries=2,
    verbose=True,
    temperature=0.1,
    rate_limiter=rate_limiter,
)


class ContentInstructions(BaseModel):
    role: str = Field(
        ..., title="User Role", description="The role of the user in the system."
    )
    topic: str = Field(
        ...,
        title="Content Topic",
        description="The topic related to the content instructions.",
    )


class TypesEnum(str, Enum):
    JOURNEY = "journey"
    SECTION = "section"
    MODULE = "module"
    ACTION = "action"


type_levels = [type_value.value for type_value in TypesEnum]


class ConvertedItem(BaseModel):
    id: str = Field(
        ...,
        title="Unique Identifier",
        description="A unique identifier generated for the item.",
    )
    parent_id: str | None = Field(
        default=None,
        title="Parent ID",
        description="Identifier of the parent item.",
    )
    type: TypesEnum = Field(
        ...,
        title="Type",
        description="The type of the item, represented as an enumeration.",
    )
    title: str = Field(..., title="Title", description="Title of the item.")
    root_id: str | None = Field(
        default=None,
        title="Root ID",
        description="Identifier of the root item in the hierarchy.",
    )
    end_of_day: int | None = Field(
        default=None,
        title="End of Day",
        description="Completed by the end of day.",
    )
    length_in_days: float | int | None = Field(
        default=None,
        title="Length in Days",
        description="Completed within specified days.",
    )
    action: str | None = Field(
        default=None,
        title="Action",
        description="Action associated with the item, if any.",
    )
    description: str | None = Field(
        default=None,
        title="Description",
        description="Content for this item.",
    )
    content_instructions: ContentInstructions | None = Field(
        default=None,
        title="Content Instructions",
        description="Instructions related to the content processing.",
    )
    icon: str | None = Field(
        default=None,
        title="Icon",
        description="Icon associated with the item, represented as a string.",
    )
    children: list["ConvertedItem"] | None = Field(
        default=None,
        title="Children",
        description="List of child items associated with the item.",
    )

    def __str__(self):
        action = f"Action: {self.action}" if self.action else None
        description = f"Description: {self.description}" if self.description else None
        content_instr = (
            f"Content Instructions: {self.content_instructions}"
            if self.content_instructions
            else None
        )
        icon = f"Icon: {self.icon}" if self.icon else None

        return (
            f"ConvertedItem(type={self.type.value},\n"
            + f"\tTitle={self.title},\n"
            + (f"\t{action:.50}\n" if action else "")
            + (f"\t{description:.50}\n" if description else "")
            + (f"\t{content_instr:.50}\n" if content_instr else "")
            + (f"\t{icon:.50}\n)\n" if icon else "")
        )


# Defining a parser for the converted output
class PopulatedContentItem(BaseModel):
    considerations_from_content: str = Field(
        ...,
        title="Content Considerations",
        description="Think, consider and describe the provided content and how it could be best reflected for the expected output.",
    )
    title: str = Field(..., title="Title", description="Title of the content.")
    content_instructions: ContentInstructions = Field(
        title="Content Instructions",
        description="Instructions related to the content processing.",
    )
    description: str = Field(
        title="Content",
        description="Content following the title derived from children and summarized in max 20 words.",
    )
    action: str = Field(
        title="Action",
        description="Action associated with the content, if any.",
    )
    # Add other necessary fields...

    def __str__(self):
        return (
            f"Title: {self.title}\n"
            + f"Considerations: "
            + f"{textwrap.fill(self.considerations_from_content, width=50)}\n"
            + f"Description: "
            + (
                f"{textwrap.fill(self.description or 'N/A', width=50)}\n"
                if self.description
                else ""
            )
            + (
                f"Action: {textwrap.fill(self.action or 'N/A', width=50)}\n"
                if self.action
                else ""
            )
            + (
                (
                    f"Content Instructions: "
                    + f"{textwrap.fill(str(self.content_instructions), width=50)}\n"
                )
                if self.content_instructions
                else ""
            )
        )


# Initialize the parser
content_parser = PydanticOutputParser(pydantic_object=PopulatedContentItem)

# Define the chain for processing ContentItem
content_chain = content_prompt_template | content_llm | content_parser


def get_content_str(content_item: ConvertedItem):
    return (
        f"Title: {content_item.title}"
        + (
            f"Description: {content_item.description}\n"
            if content_item.description
            else ""
        )
        + (f"Action: {content_item.action}\n" if content_item.action else "")
        + (
            f"Content Instructions:\n"
            f"  - Role: {content_item.content_instructions.role}\n"
            f"  - Topic: {content_item.content_instructions.topic}\n"
            if content_item.content_instructions
            else ""
        )
    )


def get_content_list(content_item: ConvertedItem):
    child_content = [get_content_str(item) for item in content_item.children]

    for child in content_item.children:
        if child.children is not None:
            child_content.extend(get_content_list(child))

    return child_content


async def process_content_item(content_item: ConvertedItem):
    # Gather content information with children details

    child_content = get_content_list(content_item)

    # Invoke the content chain
    processed_content: PopulatedContentItem = await content_chain.ainvoke(
        {
            "child_content": "\n\n".join(child_content),
            "content_information": get_content_str(content_item),
            "format_instructions": content_parser.get_format_instructions(),
        }
    )
    # Debug: Initial content item
    print("\n\nProcessed content item:\n", textwrap.indent(str(content_item), "\t"))

    # Debug: Content information gathered from children
    # print(
    #     "\tContent information gathered:",
    #     textwrap.indent(str(content_information), "\t\t"),
    # )

    # Debug: Processed content
    print("\tProcessed content:\n", textwrap.indent(str(processed_content), "\t\t"))

    # Update the main ContentItem with the processed content
    content_item.title = content_item.title or processed_content.title
    content_item.description = content_item.description or processed_content.description
    content_item.action = content_item.action or processed_content.action
    content_item.content_instructions = (
        content_item.content_instructions or processed_content.content_instructions
    )

    # # Debug: Updated content item
    # print("\tUpdated content item:\n", textwrap.indent(str(content_item), "\t\t"))

    # Use invoke_chain_with_converted_item to assign a logo
    if content_item.icon is None:
        assigned_logo: LogoTypeList = await invoke_chain_with_converted_item(
            [content_item]
        )

        # Debug: Assigned logo
        print(
            textwrap.indent(
                textwrap.fill(
                    f"Assigned logo: {assigned_logo.logos[0].logo}\n"
                    f"Reasoning: {assigned_logo.logos[0].reasoning}",
                    width=50,
                ),
                "\t",
            )
        )

        # This assumes invoke_chain_with_converted_item returns logo ID which can be set
        content_item.icon = assigned_logo.logos[0].logo

    # Debug: Final content item with icon
    print(
        "\tFinal content item with icon:\n", textwrap.indent(str(content_item), "\t\t")
    )


used_ids = set()


def get_key(key):
    id = re.sub(r"[^a-z0-9-]", " ", key.lower())
    id = re.sub(r"\s+", "_", id.strip())
    return id


def get_id(key):
    key = get_key(key)
    # Generate a unique UUID based on the key
    counter = 0
    unique_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, key))

    # Check for uniqueness and modify the key if necessary
    while unique_id in used_ids:
        counter += 1
        unique_key = f"{key}_{counter}"
        unique_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, unique_key))

    used_ids.add(unique_id)
    return unique_id


async def convert(obj, level=0, parent_id=None, root_id=None, start_eod=0, prev_eod=0) -> list[ConvertedItem]:
    new_obj: list[ConvertedItem] = []
    eod = start_eod

    # Store all futures to run in parallel
    tasks = []

    if isinstance(obj, list):
        first_eod = obj[0].get("day", 0)
        # last_eod = obj[len(obj)-1].get("day", 0)
        # total_days = last_eod - start_eod
        prev_eod = start_eod if first_eod != start_eod else prev_eod

        divisor = 1
        skip_i = 0
        for i, child in enumerate(obj):
            cur_eod = child.get("day", 0)
            if divisor == 1 and skip_i <= i:
                skip_i = i + 1
                while skip_i < len(obj) - 1 and cur_eod == child[skip_i].get("day", 0):
                    divisor += 1
                    skip_i += 1
            else:
                divisor = 1
                skip_i = i

            item = ConvertedItem(
                id=get_id(child["description"]),
                parent_id=parent_id,
                root_id=root_id
                or get_id(
                    child["description"]
                ),  # Set root_id to the current id if not set
                type=TypesEnum(type_levels[level]),
                end_of_day=cur_eod,
                length_in_days=(cur_eod - prev_eod) / divisor if divisor > 1 else (cur_eod - prev_eod),
                title=child["description"],
                action=child.get("action", ""),
                description=child.get("content", ""),
                content_instructions=ContentInstructions(
                    role=child["system_prompt"]["role"],
                    topic=child["system_prompt"]["topic"],
                ),
                icon=child.get("logo", ""),
            )
            if skip_i <= i:
                prev_eod = cur_eod

            new_obj.append(item)

    elif isinstance(obj, dict):
        # prev_eod = eod
        for key, value in obj.items():
            new_key = get_id(key)
            new_item = ConvertedItem(
                id=new_key,
                parent_id=parent_id,
                root_id=root_id,  # Set root_id to the current id if not set
                type=TypesEnum(type_levels[level]),
                end_of_day=eod,
                title=key,
            )

            if isinstance(value, Iterable) and not isinstance(value, str):
                # For children, pass the current item's id as parent_id and preserve the root_id
                children = await convert(
                    value, level + 1, parent_id=new_key, root_id=root_id or new_key, start_eod=eod, prev_eod=prev_eod
                )
                new_item.end_of_day = max(child.end_of_day for child in children)
                if new_item.end_of_day != start_eod and start_eod > prev_eod:
                    prev_eod = start_eod

                new_item.length_in_days = new_item.end_of_day - eod
                if new_item.length_in_days == 0 or new_item.length_in_days == 0.0:
                    new_item.length_in_days = new_item.end_of_day - prev_eod
                if children and new_item.type == TypesEnum.MODULE:
                    new_item.icon = children[0].icon
                new_item.children = children
                new_eod = max(eod, new_item.end_of_day)

                if new_eod != prev_eod:
                    prev_eod = eod
                    eod = new_eod

            if TypesEnum.JOURNEY == new_item.type:
                new_item.length_in_days = new_item.end_of_day
                eod = 0
            # Collect tasks for items with no description
            if not new_item.description:
                tasks.append(process_content_item(new_item))

            new_obj.append(new_item)

    # Run all tasks in parallel
    if tasks:
        await asyncio.gather(*tasks)

    return new_obj


async def main():
    mappings = {}
    file_mappings = {}

    with open(
        os.path.join(files_dir, "knowledge_services_roles.json"), "r", encoding="utf8"
    ) as file:
        data = json.load(file)
        new_obj = []

        for key, items in data.items():
            new_key = get_key(key)
            new_item = {
                "key": new_key,
                "title": key,
                "children": [{"key": get_key(item), "title": item} for item in items],
            }
            for item in items:
                mappings[get_key(item)] = new_key
            new_obj.append(new_item)

        with open(
            os.path.join(files_dir, "structured/index.json"), "w", encoding="utf8"
        ) as outfile:
            json.dump(new_obj, outfile, indent=4)

    global used_ids
    used_ids = set()

    with open(os.path.join(files_dir, "templates.json"), "r", encoding="utf8") as file:
        data = json.load(file)

        # Since convert is asynchronous, use await here
        new_obj = await convert(data)

        for item in new_obj:
            item_dict = item.model_dump(
                mode="json", exclude_none=True, exclude_unset=True
            )
            json_data = json.dumps(item_dict, indent=4)

            item_key = get_key(item.title)
            mapping = mappings[item_key]
            dir_path = os.path.join(files_dir, f"structured/{mapping}")
            filename = os.path.join(dir_path, f"{item_key}.json")
            file_mappings[item_key] = f"{mapping}/{item_key}.json"

            os.makedirs(dir_path, exist_ok=True)
            with open(filename, "w", encoding="utf8") as outfile:
                outfile.write(json_data)

    with open(
        os.path.join(files_dir, "structured/mappings.json"), "w", encoding="utf8"
    ) as outfile:
        json.dump(file_mappings, outfile, indent=4)


if __name__ == "__main__":
    # Running the asynchronous main function
    asyncio.run(main())
