// Checks catalog.json against the files: every listed PNG exists, is a real PNG of the stated size,
// and matches its byte count and SHA-256. Run before opening a pull request: node tools/check-catalog.mjs
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = join(resolve(dirname(fileURLToPath(import.meta.url)), '..'), 'catalog');
const cat = JSON.parse(readFileSync(join(dir, 'catalog.json'), 'utf8'));
const SIZES = { phone: [1440, 3200], desktop: [3840, 2160] };
const errors = [];
const ids = new Set();

for (const w of cat.wallpapers) {
  const at = `${w.id || '?'}:`;
  if (!/^[\w-]{1,40}$/.test(w.id || '')) errors.push(`${at} bad id`);
  if (ids.has(w.id)) errors.push(`${at} duplicate id`);
  ids.add(w.id);
  for (const k of ['title', 'artist', 'license']) if (!w[k]) errors.push(`${at} missing ${k}`);
  for (const [v, x] of Object.entries(w.variants || {})) {
    if (!SIZES[v]) { errors.push(`${at} unknown variant ${v}`); continue; }
    for (const k of ['file', 'preview']) {
      if (/^[a-z]+:|\.\./i.test(x[k] || '')) errors.push(`${at} ${v}.${k} must be a relative path inside catalog/`);
      else if (!existsSync(join(dir, x[k] || '-'))) errors.push(`${at} ${v}.${k} not found: ${x[k]}`);
    }
    if (!existsSync(join(dir, x.file || '-'))) continue;
    const buf = readFileSync(join(dir, x.file));
    if (buf.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') { errors.push(`${at} ${v} is not a PNG`); continue; }
    const wpx = buf.readUInt32BE(16), hpx = buf.readUInt32BE(20);
    if (wpx !== x.width || hpx !== x.height) errors.push(`${at} ${v} is ${wpx}×${hpx}, catalog says ${x.width}×${x.height}`);
    if (wpx !== SIZES[v][0] || hpx !== SIZES[v][1]) errors.push(`${at} ${v} must be ${SIZES[v].join('×')}`);
    if (buf.length !== x.bytes) errors.push(`${at} ${v} bytes ${buf.length} ≠ ${x.bytes}`);
    if (createHash('sha256').update(buf).digest('hex') !== x.sha256) errors.push(`${at} ${v} sha256 mismatch`);
  }
}
if (errors.length) { console.error(errors.join('\n')); process.exit(1); }
console.log(`catalog ok: ${cat.wallpapers.length} wallpapers`);
