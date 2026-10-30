// One API over three hosts: the Android shell, the Windows (Electron) shell, and a plain browser.
(function () {
  const android = window.ImpastoAndroid;
  const desktop = window.impastoDesktop;
  const platform = android ? 'android' : desktop ? 'windows' : 'web';

  // Android answers asynchronously through window.__impastoNative.done(id, ok, json)
  const pending = new Map();
  let seq = 0;
  window.__impastoNative = {
    done(id, ok, json) {
      const p = pending.get(id);
      if (!p) return;
      pending.delete(id);
      let data = null;
      try { data = json ? JSON.parse(json) : null; } catch { data = json; }
      ok ? p.resolve(data) : p.reject(new Error((data && data.error) || String(json || 'Failed')));
    },
    progress(id, done, total) {
      const p = pending.get(id);
      if (p && p.onProgress) p.onProgress(done, total);
    },
  };
  function callAndroid(method, args, onProgress) {
    return new Promise((resolve, reject) => {
      const id = 'r' + ++seq;
      pending.set(id, { resolve, reject, onProgress });
      try { android[method](id, ...args); } catch (e) { pending.delete(id); reject(e); }
    });
  }

  async function webDownload(url, filename) {
    const res = await fetch(url);
    if (!res.ok) throw new Error('Download failed (' + res.status + ')');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    return { location: 'your Downloads folder' };
  }

  window.Native = {
    platform,
    canSetWallpaper: platform !== 'web',
    // Returns { location, path? , uri? }
    save(url, filename, onProgress) {
      if (platform === 'android') return callAndroid('save', [url, filename], onProgress);
      if (platform === 'windows') return desktop.save(url, filename);
      return webDownload(url, filename);
    },
    // which: 'home' | 'lock' | 'both' (Android). Windows sets the desktop.
    setWallpaper(url, filename, which) {
      if (platform === 'android') return callAndroid('setWallpaper', [url, filename, which || 'both']);
      if (platform === 'windows') return desktop.setWallpaper(url, filename);
      return Promise.reject(new Error('Download the file, then set it from your system settings.'));
    },
    async share(url, filename, title, pageUrl) {
      if (platform === 'android') return callAndroid('share', [url, filename, title]);
      if (platform === 'windows') { await desktop.copyImage(url, filename); return { copied: true }; }
      if (navigator.canShare) {
        const blob = await (await fetch(url)).blob();
        const file = new File([blob], filename, { type: 'image/png' });
        if (navigator.canShare({ files: [file] })) { await navigator.share({ files: [file], title }); return {}; }
      }
      await navigator.clipboard.writeText(pageUrl || location.href);
      return { linkCopied: true };
    },
    showInFolder(path) { if (platform === 'windows') desktop.showInFolder(path); },
    openExternal(url) {
      if (platform === 'windows') return desktop.openExternal(url);
      if (platform === 'android') return android.openExternal(url);
      window.open(url, '_blank', 'noopener');
    },
    // auto-change: Android and Windows only. Status: { enabled, which, index, total, title, next, exact }
    rotation: {
      supported: platform !== 'web',
      async get() {
        if (platform === 'android') return JSON.parse(android.rotationGet() || '{}');
        if (platform === 'windows') return desktop.rotationGet();
        return { enabled: false };
      },
      async set(on, which) {
        if (platform === 'android') return JSON.parse(android.rotationSet(!!on, which || 'home') || '{}');
        if (platform === 'windows') return desktop.rotationSet(!!on);
        return { enabled: false };
      },
      list(items) {
        if (platform === 'android') android.rotationList(JSON.stringify(items));
        if (platform === 'windows') desktop.rotationList(items);
      },
      allowExact() { if (platform === 'android') android.openAlarmSettings(); },
    },
    setChrome(color, light) { if (platform === 'android' && android.setChrome) android.setChrome(color, !!light); },
  };
})();
