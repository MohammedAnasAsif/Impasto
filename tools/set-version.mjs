// Sets the app version everywhere it lives, from a tag like v1.3.0.
//   node tools/set-version.mjs v1.3.0
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const m = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(process.argv[2] || '');
if (!m) { console.error('usage: node tools/set-version.mjs v1.3.0'); process.exit(1); }
const [, major, minor, patch] = m.map(Number);
const version = `${major}.${minor}.${patch}`;
const code = major * 10000 + minor * 100 + patch; // Android needs a number that only ever goes up

const edit = (file, from, to) => {
  const p = join(root, file);
  const s = readFileSync(p, 'utf8');
  if (!from.test(s)) throw new Error(`no version found in ${file}`);
  writeFileSync(p, s.replace(from, to));
};
edit('android/AndroidManifest.xml', /android:versionCode="\d+"/, `android:versionCode="${code}"`);
edit('android/AndroidManifest.xml', /android:versionName="[^"]*"/, `android:versionName="${version}"`);
edit('app/config.js', /version: '[^']*'/, `version: '${version}'`);
edit('desktop/package.json', /"version": "[^"]*"/, `"version": "${version}"`);
console.log(`version ${version} (Android versionCode ${code})`);
