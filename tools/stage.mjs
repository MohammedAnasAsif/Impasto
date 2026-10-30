// Assemble the web bundle a shell ships: the shared UI, the catalog, every preview, and the
// full-resolution files for the variants listed (the rest stay online-only).
//
//   node tools/stage.mjs <out_dir> phone            # Android
//   node tools/stage.mjs <out_dir> desktop          # Windows
//   node tools/stage.mjs <out_dir> phone desktop    # web / everything
import { cpSync, rmSync, readFileSync, writeFileSync, mkdirSync, statSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const [out, ...variants] = process.argv.slice(2);
const bundle = new Set(variants.length ? variants : ['phone', 'desktop']);
if (!out || [...bundle].some((v) => v !== 'phone' && v !== 'desktop')) {
  console.error('usage: node tools/stage.mjs <out_dir> [phone] [desktop]');
  process.exit(1);
}
rmSync(out, { recursive: true, force: true });
cpSync(join(root, 'app'), out, { recursive: true });
const cat = JSON.parse(readFileSync(join(root, 'catalog', 'catalog.json'), 'utf8'));
for (const w of cat.wallpapers) {
  for (const [v, x] of Object.entries(w.variants)) {
    const full = bundle.has(v) && w.bundle !== false; // bundle:false = online-only full file
    for (const key of full ? ['preview', 'file'] : ['preview']) {
      const dst = join(out, 'catalog', x[key]);
      mkdirSync(dirname(dst), { recursive: true });
      cpSync(join(root, 'catalog', x[key]), dst);
    }
    x.bundled = full;
  }
}
writeFileSync(join(out, 'catalog', 'catalog.json'), JSON.stringify(cat, null, 1));
const size = (d) => readdirSync(d, { withFileTypes: true }).reduce((s, e) => s + (e.isDirectory() ? size(join(d, e.name)) : statSync(join(d, e.name)).size), 0);
console.log(`staged ${out} (${[...bundle].sort().join(', ')}) ${(size(out) / 1e6).toFixed(1)} MB`);
