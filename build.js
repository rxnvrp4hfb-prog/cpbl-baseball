import { copyFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const publicDir = join(here, "public");
const baseballDir = join(publicDir, "baseball");

mkdirSync(baseballDir, { recursive: true });
copyFileSync(join(here, "..", "index.html"), join(baseballDir, "index.html"));
copyFileSync(join(here, "..", "index.html"), join(publicDir, "index.html"));
