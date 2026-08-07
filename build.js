import { existsSync } from "node:fs";

const requiredFiles = [
  "public/index.html",
  "functions/api/[[path]].js",
  "functions/baseball/api/[[path]].js",
];

const missing = requiredFiles.filter((file) => !existsSync(file));

if (missing.length) {
  console.error(`Missing required files: ${missing.join(", ")}`);
  process.exit(1);
}

console.log("CPBL Cloudflare Pages files are ready.");
