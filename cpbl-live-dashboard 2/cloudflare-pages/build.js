import { copyFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const publicDir = join(here, "public");
const baseballDir = join(publicDir, "baseball");

mkdirSync(baseballDir, { recursive: true });
copyFileSync(join(here, "..", "index.html"), join(baseballDir, "index.html"));
writeFileSync(
  join(publicDir, "index.html"),
  `<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>leokuo.com</title>
</head>
<body>
  <main style="font-family:-apple-system,BlinkMacSystemFont,'Noto Sans TC',sans-serif;padding:32px">
    <h1>leokuo.com</h1>
    <p><a href="/baseball/">CPBL Live Board</a></p>
  </main>
</body>
</html>
`,
);
