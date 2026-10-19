const { app, BrowserWindow, ipcMain, shell, dialog, Menu } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");

const PORT = Number(process.env.LENSFX_PORT || 18765);
const HOST = "127.0.0.1";

let win = null;
let serverProc = null;
let ownedServer = false;

function isDev() {
  return !app.isPackaged;
}

function projectRoot() {
  if (isDev()) return path.join(__dirname, "..");
  return process.resourcesPath;
}

function pythonCmd() {
  if (process.env.LENSFX_PYTHON) return process.env.LENSFX_PYTHON;
  return process.platform === "win32" ? "python" : "python3";
}

function iconPath() {
  const ico = path.join(projectRoot(), "resources", process.platform === "win32" ? "icon.ico" : "icon.png");
  if (fs.existsSync(ico)) return ico;
  const png = path.join(projectRoot(), "resources", "icon.png");
  return fs.existsSync(png) ? png : undefined;
}

function healthOk() {
  return new Promise((resolve) => {
    const req = http.get(`http://${HOST}:${PORT}/api/health`, (res) => {
      resolve(res.statusCode === 200);
      res.resume();
    });
    req.on("error", () => resolve(false));
    req.setTimeout(800, () => {
      req.destroy();
      resolve(false);
    });
  });
}

function waitHealth(timeoutMs = 25000) {
  const t0 = Date.now();
  return new Promise((resolve, reject) => {
    const tick = async () => {
      if (await healthOk()) return resolve();
      if (Date.now() - t0 > timeoutMs) return reject(new Error("引擎启动超时：请确认已安装 Python 3.10+ 与 FFmpeg"));
      setTimeout(tick, 350);
    };
    tick();
  });
}

async function startEngine() {
  if (await healthOk()) {
    ownedServer = false;
    return;
  }
  const root = projectRoot();
  const env = {
    ...process.env,
    LENSFX_PORT: String(PORT),
    PYTHONPATH: [root, process.env.PYTHONPATH || ""].filter(Boolean).join(path.delimiter),
    PYTHONIOENCODING: "utf-8",
  };
  serverProc = spawn(pythonCmd(), ["-m", "lensfx", "serve", "--port", String(PORT)], {
    cwd: root,
    env,
    stdio: "pipe",
    windowsHide: true,
  });
  ownedServer = true;
  serverProc.stdout.on("data", (d) => process.stdout.write(`[engine] ${d}`));
  serverProc.stderr.on("data", (d) => process.stderr.write(`[engine] ${d}`));
  serverProc.on("exit", (code) => {
    if (ownedServer && win && !win.isDestroyed()) {
      dialog.showErrorBox("Lensfx", `引擎退出（code ${code}）。请运行 python -m lensfx doctor`);
    }
  });
  await waitHealth();
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 920,
    minHeight: 620,
    backgroundColor: "#15191e",
    title: "Lensfx",
    icon: iconPath(),
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  Menu.setApplicationMenu(null);
  win.loadURL(`http://${HOST}:${PORT}/`);
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

function stopEngine() {
  if (!ownedServer || !serverProc) return;
  ownedServer = false;
  try {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(serverProc.pid), "/f", "/t"], { windowsHide: true });
    } else {
      serverProc.kill("SIGTERM");
    }
  } catch {
    /* ignore */
  }
  serverProc = null;
}

app.whenReady().then(async () => {
  try {
    await startEngine();
  } catch (err) {
    dialog.showErrorBox("Lensfx 无法启动", String(err.message || err));
    app.quit();
    return;
  }
  createWindow();
});

app.on("window-all-closed", () => {
  stopEngine();
  app.quit();
});

app.on("before-quit", stopEngine);

ipcMain.handle("app:version", () => app.getVersion());
ipcMain.handle("shell:open", (_e, url) => {
  if (typeof url === "string" && /^https?:\/\//.test(url)) return shell.openExternal(url);
});
ipcMain.handle("dialog:openFile", async () => {
  const r = await dialog.showOpenDialog(win, {
    properties: ["openFile"],
    filters: [
      { name: "Image or video", extensions: ["jpg", "jpeg", "png", "webp", "mp4", "mov", "webm", "mkv", "m4v"] },
    ],
  });
  if (r.canceled || !r.filePaths[0]) return null;
  return r.filePaths[0];
});
