const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("lensfxDesktop", {
  isDesktop: true,
  version: () => ipcRenderer.invoke("app:version"),
  openExternal: (url) => ipcRenderer.invoke("shell:open", url),
  pickFile: () => ipcRenderer.invoke("dialog:openFile"),
});
