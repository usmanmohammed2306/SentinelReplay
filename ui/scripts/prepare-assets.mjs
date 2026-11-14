import { cpSync, mkdirSync, realpathSync } from "node:fs";
import path from "node:path";
const root = realpathSync("node_modules/monaco-editor");
mkdirSync("public/monaco", { recursive: true });
cpSync(path.join(root, "min/vs"), "public/monaco/vs", { recursive: true });
cpSync(path.join(root, "LICENSE"), "public/monaco/LICENSE");
