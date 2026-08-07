import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const publicDir = join(here, "public");

mkdirSync(publicDir,{recursive:true});
copyFileSync(join(here,"..","index.html"), join(publicDir,"index.html"));

console.log("Built for baseball.leokuo.com");
