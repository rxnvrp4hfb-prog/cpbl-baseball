import { accessSync } from "node:fs";

accessSync("public/index.html");
accessSync("functions/api/[[path]].js");

console.log("Cloudflare Pages files are ready.");
