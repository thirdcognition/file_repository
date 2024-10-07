const fs = require("fs");
const yaml = require(require.resolve("js-yaml"));

function extractDescriptions(data, parentKeys = [], first=true) {
    if (typeof data === "object" && !Array.isArray(data)) {
        let rows = [];
        for (let key in data) {
            if (first) rows.push("-- "+key + ":")
            let result = extractDescriptions(data[key], parentKeys.concat(key), false);
            if (Array.isArray(result)) {
                rows = rows.concat(result);
            } else {
                rows.push(result);
            }
        }
        return rows;
    } else if (Array.isArray(data)) {
        let rows = [];
        for (let item of data) {
            let result = extractDescriptions(item, parentKeys, false);
            if (Array.isArray(result)) {
                rows = rows.concat(result);
            } else {
                rows.push(result);
            }
        }
        if (first) rows.push('--')
        return rows;
    } else if (typeof data === "string") {
        return parentKeys.slice(1, -1).join(" -> ") + ": " + data;
    }
}

// Load the YAML data from a file
const yamlData = yaml.load(fs.readFileSync("templates.yaml", "utf8"));

// Extract descriptions with titles
let rows = extractDescriptions(yamlData);

// Filter out undefined values and empty strings
rows = rows.filter(row => row !== undefined && row.trim() !== "");

console.log(rows.join("\n"));
