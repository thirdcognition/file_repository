// Used to convert templates.json into more structured format used by code.

const fs = require("fs");
const { title } = require("process");

let usedIds = new Set();

function get_id(str, uniq = true) {
    let id = str
        .toString()
        .replace(/[^a-z0-9]/gi, " ")
        .replace(/^\s+|\s+$/g, "")
        .toLowerCase()
        .replace(/ +/g, "_");

    // Check if id has been used previously
    let counter = 1;
    origId = id
    while (uniq && usedIds.has(id)) {
        // If id has been used, append the next available integer to it
        id = origId +"_" + counter;
        counter++;
    }

    // Add id to the set of used ids
    usedIds.add(id);

    return id;
}

function convert(obj, level = 0) {
    const types = ["journey", "section", "module", "action"];
    const new_obj = [];
    let eod = 0;
    let index = 0;

    if (Array.isArray(obj)) {
        for (let i = 0; i < obj.length; i++) {
            const child = obj[i];
            new_obj.push({
                id: get_id(child["description"]),
                type: types[level],
                end_of_day: child["day"],
                title: child["description"],
                action : child["action"],
                description: child["content"],
                content_instructions: {
                    role: child["system_prompt"]["role"],
                    topic: child["system_prompt"]["topic"],
                },
                icon: child["logo"],
            });
        }
    } else if (typeof obj === "object") {
        for (let key in obj) {
            if (obj.hasOwnProperty(key)) {
                const new_key = get_id(key);
                const new_item = {
                    id: new_key,
                    type: types[level],
                    title: key,
                };

                if (typeof obj[key] !== "object") {
                    new_item["end_of_day"] = eod;
                } else {
                    const children = convert(obj[key], level + 1);
                    new_item["end_of_day"] = Math.max(
                        ...children.map((child) => child.end_of_day)
                    );
                    new_item["children"] = children;
                    eod = Math.max(eod, new_item["end_of_day"]);
                }

                new_obj.push(new_item);
                index++;
            }
        }
    }

    return new_obj;
}

fs.readFile("knowledge_services_roles.json", "utf8", (err, data) => {
    mappings = {};
    file_mappings = {};
    if (err) throw err;

    // Convert the JSON string to a JavaScript object
    const obj = JSON.parse(data);
    const new_obj = [];
    for (var key in obj) {
        if (obj.hasOwnProperty(key)) {
            const new_key = get_id(key);
            const new_item = {
                id: new_key,
                title: key,
            };
            new_item["children"] = obj[key].map((item) => {
                id = get_id(item);
                mappings[id] = new_key;
                return {
                    id: id,
                    title: item,
                };
            });
            new_obj.push(new_item);
            // new_obj.push({
            //     id: new_key,
            //     title: key,
            // });
            // const json = JSON.stringify(new_item, null, 4);

            // Write the JSON string to a new file

            // fs.writeFile(
            //     `./structured/${new_key}.json`,
            //     json,
            //     "utf8",
            //     (err) => {
            //         if (err) throw err;
            //         console.log(
            //             `The file ./structured/${new_key}.json has been saved!`
            //         );
            //     }
            // );
        }
    }
    const json = JSON.stringify(new_obj, null, 4);
    // Write the JSON string to a new file
    fs.writeFile(`./structured/index.json`, json, "utf8", (err) => {
        if (err) throw err;
        console.log(`The file ./structured/index.json has been saved!`);
    });

    // fs.writeFile(`./structured/mappings.json`, mappings, "utf8", (err) => {
    //     if (err) throw err;
    //     console.log(`The file ./structured/mappings.json has been saved!`);
    // });
    usedIds = new Set();
    // Read the JSON file
    fs.readFile("templates.json", "utf8", (err, data) => {
        if (err) throw err;

        // Convert the JSON string to a JavaScript object
        const obj = JSON.parse(data);

        const new_obj = convert(obj);
        new_obj.forEach((item) => {
            delete item["index"];
            const json = JSON.stringify(item, null, 4);

            // Write the JSON string to a new file
            mapping = mappings[item.id];
            const dir = `./structured/${mapping}`;
            const filename = `${dir}/${item.id}.json`;
            file_mappings[item.id] = `${mapping}/${item.id}.json`;
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, (options = { recursive: true }));
            }
            fs.writeFile(filename, json, "utf8", (err) => {
                if (err) throw err;
                console.log(`The file ${filename} has been saved!`);
            });
        });
        const json = JSON.stringify(file_mappings, null, 4);
        fs.writeFile(
            `./structured/mappings.json`,
            json,
            "utf8",
            (err) => {
                if (err) throw err;
                console.log(
                    `The file ./structured/mappings.json has been saved!`
                );
            }
        );
    });
});
