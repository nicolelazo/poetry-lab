// pm2 config: keeps the Python MCP server and the ngrok tunnel running.
// Start with:  pm2 start ecosystem.config.js
// No secrets live here. The server reads MCP_TOKEN from .env itself, and ngrok
// uses the authtoken saved in its own config.

const fs = require("fs");
const path = require("path");

// Tiny .env reader so this file needs no npm packages. Real environment variables win.
function loadDotEnv(file) {
  const values = {};
  if (!fs.existsSync(file)) return values;
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (!match || line.trim().startsWith("#")) continue;
    values[match[1]] = match[2].replace(/^(['"])(.*)\1$/, "$2");
  }
  return values;
}

const env = { ...loadDotEnv(path.join(__dirname, ".env")), ...process.env };

// pm2 resolves a bare script name against the project folder, so give it a full path to ngrok.
// Order: NGROK_PATH from .env, then PATH, then the folder winget installs it into.
function findNgrok() {
  if (env.NGROK_PATH) return env.NGROK_PATH;
  const exe = process.platform === "win32" ? "ngrok.exe" : "ngrok";
  const dirs = (process.env.PATH || "").split(path.delimiter).filter(Boolean);
  if (process.env.LOCALAPPDATA) {
    const packages = path.join(process.env.LOCALAPPDATA, "Microsoft", "WinGet", "Packages");
    if (fs.existsSync(packages)) {
      for (const name of fs.readdirSync(packages)) {
        if (name.toLowerCase().startsWith("ngrok.ngrok")) dirs.push(path.join(packages, name));
      }
    }
  }
  for (const dir of dirs) {
    const candidate = path.join(dir, exe);
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error("ngrok not found. Set NGROK_PATH=C:\\full\\path\\to\\ngrok.exe in .env.");
}

const domain = (env.NGROK_DOMAIN || "")
  .trim()
  .replace(/^https?:\/\//, "")
  .replace(/\/+$/, "");
if (!domain) {
  throw new Error("NGROK_DOMAIN is not set. Add it to .env (see .env.example).");
}

const host = env.MCP_HOST || "127.0.0.1";
const port = env.MCP_PORT || "8000";
const python = path.join(
  __dirname,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python"
);
const logs = path.join(__dirname, "logs");

module.exports = {
  apps: [
    {
      name: "poetry-lab-server",
      script: python,
      args: "server.py",
      interpreter: "none",
      cwd: __dirname,
      autorestart: true,
      restart_delay: 3000,
      max_restarts: 20,
      time: true,
      out_file: path.join(logs, "server.out.log"),
      error_file: path.join(logs, "server.err.log"),
      env: { PYTHONUNBUFFERED: "1" },
    },
    {
      name: "poetry-lab-ngrok",
      script: findNgrok(),
      args: `http --domain=${domain} --log=stdout ${host}:${port}`,
      interpreter: "none",
      cwd: __dirname,
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 20,
      time: true,
      out_file: path.join(logs, "ngrok.out.log"),
      error_file: path.join(logs, "ngrok.err.log"),
    },
  ],
};
