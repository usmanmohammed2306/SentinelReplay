import { cpSync, existsSync } from "node:fs";
import { spawn } from "node:child_process";
const portIndex = process.argv.indexOf("--port");
const port =
  portIndex < 0 ? (process.env.PORT ?? "3000") : process.argv[portIndex + 1];
if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535)
  throw new Error("Invalid listen port");
cpSync(".next/static", ".next/standalone/.next/static", { recursive: true });
if (existsSync("public"))
  cpSync("public", ".next/standalone/public", { recursive: true });
const child = spawn(process.execPath, [".next/standalone/server.js"], {
  stdio: "inherit",
  env: { ...process.env, PORT: port, HOSTNAME: "127.0.0.1" },
});
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => child.kill(signal));
child.on("exit", (code) => process.exit(code ?? 1));
