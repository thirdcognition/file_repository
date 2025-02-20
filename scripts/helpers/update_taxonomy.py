import os
from typing import Callable
import yaml  # type: ignore
import re


def generate_human_readable_id(title):
    """
    Generate a human-readable ID by:
    - Lowercasing the text
    - Replacing non-alphanumeric characters with underscores
    """
    return re.sub(r"[^a-zA-Z0-9]", "_", title.lower())


def sort(data):
    sorted_data = dict(
        sorted(
            data.items(),
            key=lambda item: (
                "parent" in item[1],
                len(item[1].keys()),
                item[1]["title"],
            ),
        )
    )

    return sorted_data


def read_with_callback(file_path, callback: Callable):
    with open(file_path, "r") as file:
        data = yaml.safe_load(file)

    updated_data = callback(data)
    # Write the updated data back to the YAML file
    if updated_data:
        with open(file_path.replace(".yaml", "-ed.yaml"), "w") as file:
            yaml.dump(updated_data, file, sort_keys=False)


def update_taxonomy(data):
    # Create a mapping of old keys to new human-readable IDs
    key_mapping = {}
    for key, value in data.items():
        title = value.get("title", "")
        new_key = generate_human_readable_id(title)
        key_mapping[key] = new_key

    # Update the keys and parent references
    updated_data = {}
    for old_key, value in data.items():
        new_key = key_mapping[old_key]
        updated_entry: dict = value

        # Update the parent field if it exists
        if "parent" in updated_entry.keys():
            parent_field = updated_entry.get("parent")
            parent_key_match = re.search(r"\(([^)]+)\)", parent_field)
            if parent_key_match:
                parent_key = parent_key_match.group(1)
                if parent_key in key_mapping:
                    new_parent_key = key_mapping[parent_key]
                    updated_entry["parent"] = new_parent_key

        updated_data[new_key] = updated_entry

    return updated_data


def split_and_save_categories(data, output_dir="categories"):
    """
    Split the taxonomy data into separate files for each root node and its entire tree of descendants.
    Save each group into a YAML file in the specified output directory.
    """
    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Helper function to recursively collect all descendants
    def collect_children(node_id, data):
        children = {}
        for key, value in data.items():
            if value.get("parent") == node_id:
                children[key] = value
                children.update(
                    collect_children(key, data)
                )  # Recursively add descendants
        return children

    # Identify root nodes and process each
    for key, value in data.items():
        if "parent" not in value:  # Root node
            root_node = {key: value}
            descendants = collect_children(key, data)
            group = {**root_node, **descendants}

            # Save to a YAML file
            output_path = os.path.join(output_dir, f"{key}.yaml")
            with open(output_path, "w") as file:
                yaml.dump(group, file, sort_keys=False)

    print(f"Categories saved to '{output_dir}' directory.")


def alert_missing_parents(data):
    """
    Alerts all items with parents that cannot be found in the data.
    """
    missing_parents = []
    for key, value in data.items():
        parent = value.get("parent")
        if parent and parent not in data:
            missing_parents.append((key, parent))

    if missing_parents:
        print("Items with missing parents:")
        for item, parent in missing_parents:
            print(f"Item: {item}, Missing Parent: {parent}")
    else:
        print("No missing parents found.")


# Example usage
file_path = "../../taxonomy/news.yaml"
read_with_callback(file_path, sort)
# file_path = "../../taxonomy/news-ed-ed.yaml"
# read_with_callback(file_path, alert_missing_parents)
# read_with_callback(
#     file_path,
#     lambda data: split_and_save_categories(
#         data, output_dir="../../taxonomy/categories"
#     ),
# )
