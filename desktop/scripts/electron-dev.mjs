import { spawn } from "node:child_process";
import process from "node:process";

const env = { ...process.env, ATLAS_DESKTOP_DEV_URL: "http://127.0.0.1:4173" };
const vite = spawn("npm", ["run", "dev", "--", "--host", "127.0.0.1", "--port", "4173", "--strictPort"], {
  env,
  shell: process.platform === "win32",
  stdio: "inherit",
});

let electron;
const timer = setInterval(async () => {
  try {
    const response = await fetch(env.ATLAS_DESKTOP_DEV_URL);
    if (!response.ok) return;
    clearInterval(timer);
    electron = spawn("npx", ["electron", "."], {
      env,
      shell: process.platform === "win32",
      stdio: "inherit",
    });
    electron.on("exit", () => vite.kill("SIGTERM"));
  } catch {
    // Vite is still starting.
  }
}, 250);

function stop() {
  clearInterval(timer);
  electron?.kill("SIGTERM");
  vite.kill("SIGTERM");
}

process.on("SIGINT", stop);
process.on("SIGTERM", stop);
