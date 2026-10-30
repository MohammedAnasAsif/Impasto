// Electron shell for Windows: serves the shared store UI from app://impasto and does the OS work.
const { app, BrowserWindow, protocol, ipcMain, shell, clipboard, nativeImage, net, Tray, Menu, powerMonitor } = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');
const { execFile } = require('node:child_process');

const WWW = path.join(__dirname, 'www');
const ORIGIN = 'app://impasto';
const MAX_BYTES = 120 * 1024 * 1024;
const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
const saveDir = () => path.join(app.getPath('pictures'), 'Impasto');

protocol.registerSchemesAsPrivileged([{ scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } }]);
if (!app.requestSingleInstanceLock()) app.quit();

// Resolve app://impasto/<path> inside www, refusing anything that escapes it.
function localPath(url) {
  const u = new URL(url);
  if (u.protocol !== 'app:' || u.host !== 'impasto') return null;
  const p = path.normalize(path.join(WWW, decodeURIComponent(u.pathname)));
  return p.startsWith(WWW + path.sep) ? p : null;
}

// Wallpaper bytes from the bundle or an https catalog, checked to really be a PNG.
async function readWallpaper(url) {
  let buf;
  const local = localPath(url);
  if (local) buf = await fs.readFile(local);
  else {
    if (!/^https:\/\//i.test(url)) throw new Error('Only https sources are allowed');
    const res = await net.fetch(url);
    if (!res.ok) throw new Error(`Download failed (${res.status})`);
    if (Number(res.headers.get('content-length') || 0) > MAX_BYTES) throw new Error('File is too large');
    buf = Buffer.from(await res.arrayBuffer());
  }
  if (buf.length > MAX_BYTES) throw new Error('File is too large');
  if (!buf.subarray(0, 8).equals(PNG)) throw new Error("That file isn't a PNG");
  return buf;
}

const safeName = (n) => {
  let s = String(n || 'wallpaper').replace(/[^A-Za-z0-9._-]/g, '_').slice(-120);
  return s.endsWith('.png') ? s : s + '.png';
};

async function save(url, filename) {
  const buf = await readWallpaper(url);
  await fs.mkdir(saveDir(), { recursive: true });
  const file = path.join(saveDir(), safeName(filename));
  await fs.writeFile(file, buf);
  return { location: 'Pictures\\Impasto', path: file };
}

function setDesktopWallpaper(file) {
  if (process.platform !== 'win32') return Promise.reject(new Error('Setting the wallpaper is supported on Windows only'));
  // Path goes in through the environment, never spliced into the script.
  const ps = `
$p = $env:IMPASTO_WALLPAPER
Set-ItemProperty -Path 'HKCU:\\Control Panel\\Desktop' -Name WallpaperStyle -Value 10
Set-ItemProperty -Path 'HKCU:\\Control Panel\\Desktop' -Name TileWallpaper -Value 0
Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public class ImpastoW { [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] public static extern bool SystemParametersInfo(int a, int b, string c, int d); }'
if (-not [ImpastoW]::SystemParametersInfo(20, 0, $p, 3)) { exit 1 }`;
  return new Promise((resolve, reject) => {
    execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', ps],
      { env: { ...process.env, IMPASTO_WALLPAPER: file }, windowsHide: true, timeout: 30000 },
      (err) => (err ? reject(new Error("Windows didn't accept the wallpaper")) : resolve({})));
  });
}

// ---------- auto-change: a new wallpaper every minute, round robin, kept alive from the tray ----------
const EVERY = 60_000;
const rotFile = () => path.join(app.getPath('userData'), 'rotation.json');
let rot = { enabled: false, index: -1, list: [], flip: 0 };
let rotTimer = null, nextAt = 0, tray = null, win = null, quitting = false;

async function loadRotation() {
  try { rot = { ...rot, ...JSON.parse(await fs.readFile(rotFile(), 'utf8')) }; } catch { /* first run */ }
}
const saveRotation = () => fs.writeFile(rotFile(), JSON.stringify(rot)).catch(() => {});

async function rotTick() {
  const n = rot.list.length;
  if (!n || powerMonitor.getSystemIdleState(60) === 'locked') return; // nobody can see the desktop
  for (let t = 0; t < Math.min(n, 3); t++) {
    const i = (rot.index + 1 + t) % n; // after the last one, back to the first
    try {
      rot.flip ^= 1; // alternate two files so Windows always sees a changed path
      const file = path.join(app.getPath('userData'), `auto-${rot.flip}.png`);
      await fs.writeFile(file, await readWallpaper(rot.list[i].url));
      await setDesktopWallpaper(file);
      rot.index = i;
      break;
    } catch { /* offline or missing: try the next one */ }
  }
  saveRotation();
}

function rotSchedule() {
  clearTimeout(rotTimer);
  if (!rot.enabled) return;
  nextAt = Date.now() + EVERY;
  rotTimer = setTimeout(async () => { await rotTick(); rotSchedule(); }, EVERY);
}

function rotationStatus() {
  const cur = rot.list[rot.index];
  return { enabled: rot.enabled, index: rot.index, total: rot.list.length, title: cur ? cur.title : '', next: rot.enabled ? nextAt : 0, exact: true };
}

async function setRotation(on) {
  rot.enabled = !!on;
  await saveRotation();
  if (process.platform === 'win32') {
    // start with Windows only while auto-change is on, straight to the tray
    app.setLoginItemSettings({ openAtLogin: rot.enabled, path: process.env.PORTABLE_EXECUTABLE_FILE || process.execPath, args: ['--background'] });
  }
  if (rot.enabled) { showTray(); await rotTick(); rotSchedule(); }
  else { clearTimeout(rotTimer); if (tray) { tray.destroy(); tray = null; } }
  return rotationStatus();
}

function showTray() {
  if (tray) return;
  tray = new Tray(nativeImage.createFromPath(path.join(__dirname, 'build', 'icon.png')).resize({ width: 16, height: 16 }));
  tray.setToolTip('Impasto: changing your wallpaper every minute');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Open Impasto', click: showWindow },
    { label: 'Next wallpaper', click: async () => { await rotTick(); rotSchedule(); } },
    { label: 'Stop auto-change', click: () => setRotation(false) },
    { type: 'separator' },
    { label: 'Quit', click: () => { quitting = true; app.quit(); } },
  ]));
  tray.on('click', showWindow);
}

function showWindow() {
  if (!win || win.isDestroyed()) return createWindow();
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440, height: 920, minWidth: 380, minHeight: 600,
    title: 'Impasto',
    backgroundColor: '#090b11',
    autoHideMenuBar: true,
    icon: path.join(__dirname, 'build', 'icon.png'),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true, nodeIntegration: false, spellcheck: false },
  });
  win.setMenuBarVisibility(false);
  win.webContents.on('will-navigate', (e, url) => { if (!url.startsWith(ORIGIN)) { e.preventDefault(); if (/^https:\/\//i.test(url)) shell.openExternal(url); } });
  win.webContents.setWindowOpenHandler(({ url }) => { if (/^https:\/\//i.test(url)) shell.openExternal(url); return { action: 'deny' }; });
  win.on('close', (e) => { if (rot.enabled && !quitting) { e.preventDefault(); win.hide(); } }); // keep changing from the tray
  win.loadURL(ORIGIN + '/index.html');
}

app.on('second-instance', showWindow);
app.on('before-quit', () => { quitting = true; });

app.whenReady().then(async () => {
  protocol.handle('app', async (req) => {
    const p = localPath(req.url);
    if (!p) return new Response('Not found', { status: 404 });
    try {
      const body = await fs.readFile(p);
      return new Response(body, { headers: { 'content-type': MIME[path.extname(p)] || 'application/octet-stream' } });
    } catch {
      return new Response('Not found', { status: 404 });
    }
  });

  ipcMain.handle('save', (_e, url, filename) => save(url, filename));
  ipcMain.handle('set-wallpaper', async (_e, url, filename) => setDesktopWallpaper((await save(url, filename)).path));
  ipcMain.handle('copy-image', async (_e, url) => { clipboard.writeImage(nativeImage.createFromBuffer(await readWallpaper(url))); return {}; });
  ipcMain.handle('show-in-folder', (_e, file) => {
    const f = path.normalize(String(file || ''));
    if (f.startsWith(saveDir() + path.sep)) shell.showItemInFolder(f);
  });
  ipcMain.handle('rotation-get', () => rotationStatus());
  ipcMain.handle('rotation-set', (_e, on) => setRotation(on));
  ipcMain.handle('rotation-list', (_e, list) => {
    if (!Array.isArray(list)) return;
    rot.list = list.slice(0, 1000)
      .filter((x) => x && typeof x.url === 'string' && (localPath(x.url) || /^https:\/\//i.test(x.url)))
      .map((x) => ({ url: x.url, title: String(x.title || '').slice(0, 80) }));
    if (rot.index >= rot.list.length) rot.index = -1;
    saveRotation();
  });
  ipcMain.handle('open-external', (_e, url) => { if (/^https:\/\//i.test(String(url))) shell.openExternal(url); });

  await loadRotation();
  if (rot.enabled) { showTray(); rotSchedule(); }
  if (!(rot.enabled && process.argv.includes('--background'))) createWindow();
});

app.on('window-all-closed', () => { if (!rot.enabled) app.quit(); });
