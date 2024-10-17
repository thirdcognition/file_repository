import os
import json
import re

from dotenv import load_dotenv

load_dotenv()

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
files_dir = os.path.join(script_dir, "../files")

used_ids = set()

def get_id(string, uniq=True):
    # Convert string to a valid id format
    id = re.sub(r'[^a-z0-9]', ' ', string.lower())
    id = re.sub(r'\s+', '_', id.strip())

    # Ensure the id is unique
    counter = 1
    orig_id = id
    while uniq and id in used_ids:
        id = f"{orig_id}_{counter}"
        counter += 1

    used_ids.add(id)
    return id

def convert(obj, level=0):
    types = ["journey", "section", "module", "action"]
    new_obj = []
    eod = 0

    if isinstance(obj, list):
        for child in obj:
            new_obj.append({
                "id": get_id(child["description"]),
                "type": types[level],
                "end_of_day": child.get("day", 0),
                "title": child["description"],
                "action": child.get("action", ""),
                "description": child.get("content", ""),
                "content_instructions": {
                    "role": child["system_prompt"]["role"],
                    "topic": child["system_prompt"]["topic"],
                },
                "icon": child.get("logo", "")
            })
    elif isinstance(obj, dict):
        for key, value in obj.items():
            new_key = get_id(key)
            new_item = {"id": new_key, "type": types[level], "title": key}

            if not isinstance(value, dict):
                new_item["end_of_day"] = eod
            else:
                children = convert(value, level + 1)
                new_item["end_of_day"] = max(child["end_of_day"] for child in children)
                if children:
                    new_item["icon"] = children[0]["icon"]
                new_item["children"] = children
                eod = max(eod, new_item["end_of_day"])

            new_obj.append(new_item)

    return new_obj

with open("knowledge_services_roles.json", "r", encoding="utf8") as file:
    data = json.load(file)
    mappings = {}
    file_mappings = {}
    new_obj = []

    for key, items in data.items():
        new_key = get_id(key)
        new_item = {
            "id": new_key,
            "title": key,
            "children": [{"id": get_id(item), "title": item} for item in items],
        }
        for item in items:
            mappings[get_id(item)] = new_key
        new_obj.append(new_item)

    with open("./structured/index.json", "w", encoding="utf8") as outfile:
        json.dump(new_obj, outfile, indent=4)

used_ids = set()

with open(os.path.join(files_dir, "templates.json"), "r", encoding="utf8") as file:
    data = json.load(file)
    new_obj = convert(data)

    for item in new_obj:
        item.pop("index", None)
        json_data = json.dumps(item, indent=4)
        mapping = mappings[item["id"]]
        dir_path = os.path.join(files_dir, f"structured/{mapping}")
        filename = os.path.join(dir_path, f"{item['id']}.json")
        file_mappings[item["id"]] = f"{mapping}/{item['id']}.json"

        os.makedirs(dir_path, exist_ok=True)
        with open(filename, "w", encoding="utf8") as outfile:
            outfile.write(json_data)

    with open(os.path.join(files_dir, "structured/mappings.json"), "w", encoding="utf8") as outfile:
        json.dump(file_mappings, outfile, indent=4)
