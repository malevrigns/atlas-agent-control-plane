const { app, BrowserWindow } = require("electron");
const fs = require("node:fs");
const path = require("node:path");

app.commandLine.appendSwitch("headless");
app.commandLine.appendSwitch("disable-gpu");
app.disableHardwareAcceleration();

app.whenReady().then(async () => {
  const output = path.resolve(process.argv[2] || "design-qa-implementation.png");
  const win = new BrowserWindow({
    width: 1488,
    height: 1058,
    show: false,
    useContentSize: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  const consoleErrors = [];
  win.webContents.on("console-message", (_event, level, message) => {
    if (level >= 2) consoleErrors.push(message);
  });
  await win.loadFile(path.join(__dirname, "..", "dist", "client", "index.html"));
  win.setContentSize(1488, 1058);
  await new Promise((resolve) => setTimeout(resolve, 1500));
  const image = await win.webContents.capturePage();
  fs.writeFileSync(output, image.toPNG());
  process.stdout.write(JSON.stringify({ output, size: image.getSize(), consoleErrors }) + "\n");
  app.quit();
});
