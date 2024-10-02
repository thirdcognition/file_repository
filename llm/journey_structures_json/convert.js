// Used to convert templates.json into more structured format used by code.

const fs = require("fs");

function convert(obj, level = 0) {
    const types = ["journey", "subject", "subsubject", "module"];
    const new_obj = [];
    let eod = 0;
    let index = 0;

    if (Array.isArray(obj)) {
        for (let i = 0; i < obj.length; i++) {
            const child = obj[i];
            new_obj.push({
                index: i,
                id: child["description"]
                    .toString()
                    .replace(/[^a-z0-9]/gi, " ")
                    .replace(/^\s+|\s+$/g, "")
                    .toLowerCase()
                    .replace(/ +/g, "_"),
                type: types[level],
                end_of_day: child["end_of_day"],
                title: child["description"],
            });
        }
    } else if (typeof obj === "object") {
        for (let key in obj) {
            if (obj.hasOwnProperty(key)) {
                const new_key = key
                    .replace(/[^a-z0-9]/gi, " ")
                    .replace(/^\s+|\s+$/g, "")
                    .toLowerCase()
                    .replace(/ +/g, "_");
                const new_item = {
                    index: index,
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

// Read the JSON file
fs.readFile("templates.json", "utf8", (err, data) => {
    if (err) throw err;

    // Convert the JSON string to a JavaScript object
    const obj = JSON.parse(data);

    const new_obj = convert(obj);
    const json = JSON.stringify(new_obj, null, 4);

    // Write the JSON string to a new file
    fs.writeFile("templates_structured.json", json, "utf8", (err) => {
        if (err) throw err;
        console.log("The file has been saved!");
    });
});
