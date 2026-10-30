const { contextBridge, ipcRenderer } = require('electron');

// Errors thrown in the main process arrive prefixed with "Error invoking remote method"; keep the human part.
const call = (ch, ...a) => ipcRenderer.invoke(ch, ...a).catch((e) => {
  throw new Error(String(e && e.message || e).replace(/^Error invoking remote method '[^']+': (Error: )?/, ''));
});

contextBridge.exposeInMainWorld('impastoDesktop', {
  save: (url, filename) => call('save', url, filename),
  setWallpaper: (url, filename) => call('set-wallpaper', url, filename),
  copyImage: (url, filename) => call('copy-image', url, filename),
  showInFolder: (file) => call('show-in-folder', file),
  openExternal: (url) => call('open-external', url),
  rotationGet: () => call('rotation-get'),
  rotationSet: (on) => call('rotation-set', on),
  rotationList: (list) => call('rotation-list', list),
});
