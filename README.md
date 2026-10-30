# Impasto

An open-source wallpaper store for **Android** and **Windows**. Thick oil-paint wallpapers, shipped as
**lossless PNG at each screen's native size**: 1440 × 3200 for phones, 3840 × 2160 for desktops.
Browse it like a shop, add to bag, check out for free, set it as your wallpaper in one tap.

No accounts, no ads, no tracking, no compression.

| | Android | Windows |
|---|---|---|
| File | `Impasto-1.0.0.apk` | `Impasto-Setup-1.0.0.exe` (installer) · `Impasto-1.0.0-portable.exe` |
| Needs | Android 10 or newer | Windows 10 or 11, 64-bit |
| Set wallpaper | Home, lock or both | Desktop (Fill) |
| Saves to | `Pictures/Impasto` | `Pictures\Impasto` |
| Share | System share sheet | Copies the image to the clipboard |

## What's inside

```
app/        The store UI. One HTML/CSS/JS app, no framework, no build step. Shared by both shells.
catalog/    catalog.json + wallpapers/<id>/{phone,desktop}.png and their previews.
android/    A WebView shell in plain Java (~300 lines). Built with aapt + dx, no Gradle.
desktop/    An Electron shell (~120 lines) packaged with electron-builder.
tools/      paint.py paints the starter pack; stage.mjs assembles what each app bundles.
```

Each app bundles the UI, every preview, and the full PNGs for its own screen type. The other size is
fetched from the **catalog source** when you ask for it.

## The catalog source (important)

The apps can read a remote `catalog.json`, so new wallpapers reach every installed copy without an app
update. After you push this repo to GitHub, set the source in `app/config.js`:

```js
remoteBase: 'https://raw.githubusercontent.com/<you>/impasto/main/catalog/',
repoUrl: 'https://github.com/<you>/impasto',
```

Users can also change it in **About → Catalog source**. Until a source is set, the Android app offers
desktop sizes as "not bundled" and the Windows app does the same for phone sizes.

## Adding wallpapers

1. Put `phone.png` (1440 × 3200) and/or `desktop.png` (3840 × 2160) in `catalog/wallpapers/<id>/`.
   PNG only; the apps reject anything else.
2. Add a `phone-preview.webp` (≤720 px) and `desktop-preview.webp` (≤1280 px) for the grid.
3. Add an entry to `catalog/catalog.json` (copy an existing one; `bytes`, `sha256` and `color` must
   match the file). Set `artist` and `license` honestly.
4. Run `node tools/check-catalog.mjs`, then open a pull request. Only submit work you made or have the right to share.

To repaint or extend the starter pack: `pip install numpy scipy pillow && python3 tools/paint.py`.

## Building

**Android APK** (Linux, or WSL on Windows):

```bash
sudo apt-get install aapt zipalign apksigner dalvik-exchange android-sdk-platform-23 openjdk-17-jdk nodejs
bash android/build.sh                 # → dist/Impasto-1.0.0.apk
```

Without signing variables the script creates `android/keystore/impasto-local.jks`. **Back it up**:
Android only installs updates signed with the same key. For releases, set `KEYSTORE`,
`KEYSTORE_PASS` and `KEY_ALIAS`.

**Windows .exe** (on Windows; on Linux it also works with Wine installed):

```bash
cd desktop
npm ci
npm start           # run it
npm run dist:win    # → dist/Impasto-Setup-1.0.0.exe and dist/Impasto-1.0.0-portable.exe
```

**Both, automatically:** push a tag like `v1.0.1`. `.github/workflows/release.yml` builds the APK on
Ubuntu and the installers on Windows and attaches them to a GitHub release. Add the repository
secrets `ANDROID_KEYSTORE_B64` (base64 of your .jks), `ANDROID_KEYSTORE_PASS` and `ANDROID_KEY_ALIAS`
so every release is signed with the same key.

**Try the UI in a browser:** `node tools/stage.mjs build/web && python3 -m http.server -d build/web`.

## Notes

- The installers are not code-signed. Windows SmartScreen will warn on first run ("More info → Run
  anyway") until you sign them with a certificate. Android will ask to allow installs from this source.
- The APK compiles against API 23 and calls newer APIs (`WallpaperManager.setStream` with flags,
  scoped `MediaStore` paths) through reflection or string keys, so it builds from Ubuntu packages alone.
  It targets API 34; Google Play will require a newer target, which needs the full Android SDK.

## License

Code: [MIT](LICENSE). Starter-pack wallpapers: [CC0](catalog/LICENSE.md). Interface typeface:
Bricolage Grotesque, SIL OFL 1.1.
