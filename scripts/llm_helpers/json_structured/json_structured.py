import asyncio
import os
import json
import re
import textwrap

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

from icon_matcher.icon_matcher import LogoTypeList, invoke_chain_with_converted_item


load_dotenv()

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
files_dir = os.path.join(script_dir, "../files")

used_ids = set()


# Prompt Definitions
content_prompt = """
You are an assistant that processes ContentItems to identify missing details.
You'll receive a ContentItem with some fields already populated and all of it's children.
Your task is to populate remaining fields using the given data from children.
"""

content_message_template = """
Content Information:
{content_information}

Process the content and fill in any missing fields. Consider the titles, icons, and contents of children and their descendants.

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


class ConvertedItem(BaseModel):
    id: str = Field(
        ...,
        title="Unique Identifier",
        description="A unique identifier generated for the item.",
    )
    parent_id: str = Field(
        None, title="Parent ID", description="Identifier of the parent item."
    )
    type: TypesEnum = Field(
        ...,
        title="Type",
        description="The type of the item, represented as an enumeration.",
    )
    end_of_day: int = Field(
        ...,
        title="End of Day",
        description="Indicator for the end of the day in the context of the item.",
    )
    title: str = Field(..., title="Title", description="Title of the item.")
    root_id: str = Field(
        None,
        title="Root ID",
        description="Identifier of the root item in the hierarchy.",
        default=None,
    )
    action: str = Field(
        None,
        title="Action",
        description="Action associated with the item, if any.",
        default=None,
    )
    description: str = Field(
        None,
        title="Description",
        description="Detailed description of the item.",
        default=None,
    )
    content_instructions: ContentInstructions = Field(
        None,
        title="Content Instructions",
        description="Instructions related to the content processing.",
        default=None,
    )
    icon: str = Field(
        None,
        title="Icon",
        description="Icon associated with the item, represented as a string.",
        default=None,
    )
    children: list["ConvertedItem"] = Field(
        default_factory=list,
        title="Children",
        description="List of child items associated with the item.",
        default=None,
    )

    def __str__(self):
        return (
            f"ConvertedItem(type={self.type.value},\n"
            f"\ttitle={self.title},\n"
            f"\taction={self.action},\n\tdescription={self.description},\n"
            f"\tcontent_instructions={self.content_instructions}, icon={self.icon}\n)\n"
        )


# Defining a parser for the converted output
class PopulatedContentItem(BaseModel):
    considerations_from_content: str = Field(
        ...,
        title="Content Considerations",
        description="Think, consider and describe the provided content and how it could be best reflected for the expected output.",
    )
    title: str = Field(..., title="Title", description="Title of the item.")
    description: str = Field(
        None,
        title="Description",
        description="Detailed description of the item.",
        default=None,
    )
    action: str = Field(
        None,
        title="Action",
        description="Action associated with the item, if any.",
        default=None,
    )
    content_instructions: ContentInstructions = Field(
        None,
        title="Content Instructions",
        description="Instructions related to the content processing.",
        default=None,
    )
    # Add other necessary fields...

    def __str__(self):
        return (
            f"Title: {self.title}\n"
            f"Considerations: {self.considerations_from_content}\n"
            f"Description: {self.description or 'N/A'}\n"
            f"Action: {self.action or 'N/A'}\n"
            f"Content Instructions: {self.content_instructions or 'N/A'}\n"
        )


# Initialize the parser
content_parser = PydanticOutputParser(pydantic_object=PopulatedContentItem)

# Define the chain for processing ContentItem
content_chain = content_prompt_template | content_llm | content_parser


async def process_content_item(content_item: ConvertedItem):
    # Debug: Initial content item
    print("Processing content item:", content_item)

    # Gather content information with children details
    content_information = "\n\n".join(
        [
            textwrap.dedent(
                f"""
            Title: {item.title}
            Description:
            {item.description}
            Action: {item.action}
            Content Instructions:
            - Role: {item.content_instructions.role}
            - Topic: {item.content_instructions.topic}
            """
            )
            for item in content_item.children
        ]
    )

    # Debug: Content information gathered from children
    print("Content information gathered:", content_information)

    # Invoke the content chain
    processed_content: PopulatedContentItem = await content_chain.ainvoke(
        {
            "content_information": content_information,
            "format_instructions": content_parser.get_format_instructions(),
        }
    )

    # Debug: Processed content
    print("Processed content:", processed_content)

    # Update the main ContentItem with the processed content
    content_item.title = content_item.title or processed_content.title
    content_item.description = content_item.description or processed_content.description
    content_item.action = content_item.action or processed_content.action
    content_item.content_instructions = (
        content_item.content_instructions or processed_content.description
    )

    # Debug: Updated content item
    print("Updated content item:", content_item)

    # Use invoke_chain_with_converted_item to assign a logo
    assigned_logo: LogoTypeList = await invoke_chain_with_converted_item([content_item])

    # Debug: Assigned logo
    print("Assigned logo:", assigned_logo)

    # This assumes invoke_chain_with_converted_item returns logo ID which can be set
    content_item.icon = assigned_logo.logos[0].logo

    # Debug: Final content item with icon
    print("Final content item with icon:", content_item)


used_ids = set()


def get_key(key):
    id = re.sub(r"[^a-z0-9-]", " ", key.lower())
    id = re.sub(r"\s+", "_", id.strip())
    return key


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


import asyncio


async def convert(obj, level=0, parent_id=None, root_id=None) -> list[ConvertedItem]:
    new_obj = []
    eod = 0

    # Store all futures to run in parallel
    tasks = []

    if isinstance(obj, list):
        for child in obj:
            item = ConvertedItem(
                id=get_id(child["description"]),
                parent_id=parent_id,
                root_id=root_id
                or get_id(
                    child["description"]
                ),  # Set root_id to the current id if not set
                type=TypesEnum[level],
                end_of_day=child.get("day", 0),
                title=child["description"],
                action=child.get("action", ""),
                description=child.get("content", ""),
                content_instructions=ContentInstructions(
                    role=child["system_prompt"]["role"],
                    topic=child["system_prompt"]["topic"],
                ),
                icon=child.get("logo", ""),
            )

            new_obj.append(item)

    elif isinstance(obj, dict):
        for key, value in obj.items():
            new_key = get_id(key)
            new_item = ConvertedItem(
                id=new_key,
                parent_id=parent_id,
                root_id=root_id,  # Set root_id to the current id if not set
                type=TypesEnum[level],
                title=key,
                end_of_day=eod,
                children=[],
            )

            if isinstance(value, dict):
                # For children, pass the current item's id as parent_id and preserve the root_id
                children = await convert(
                    value, level + 1, parent_id=new_key, root_id=root_id or new_key
                )
                new_item.end_of_day = max(child.end_of_day for child in children)
                if children:
                    new_item.icon = children[0].icon
                new_item.children = children
                eod = max(eod, new_item.end_of_day)

            # Collect tasks for items with no description
            if not new_item.description:
                tasks.append(process_content_item(new_item))

            new_obj.append(new_item)

    # Run all tasks in parallel
    if tasks:
        await asyncio.gather(*tasks)

    return new_obj


async def main():
    files_dir = "path_to_your_files_dir"  # Update with actual directory
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
            item_dict = item.model_dump(mode="json")
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


# Running the asynchronous main function
asyncio.run(main())
