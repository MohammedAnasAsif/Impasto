(function () {
  'use strict';
  const cfg = window.IMPASTO_CONFIG;
  const N = window.Native;
  const CLASSIC = N.platform === 'android'; // the APK keeps the earlier layout (android/www/styles.css)
  const main = document.getElementById('main');
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const mb = (b) => (b / 1e6).toFixed(1) + ' MB';
  const abs = (u) => new URL(u, location.href).href;

  const COLLECTIONS = {
    Savage: 'Lines with no apology.',
    Delusional: 'Loud type for big plans.',
    Quiet: 'Serif type with room to breathe.',
    Painted: 'Scenes laid down in thick oil.',
    Fields: 'Colour you can almost touch.',
    Cinema: 'Film-still moods. No faces, no spoilers.',
  };

  // ---------- persisted state ----------
  const store = {
    get(k, d) { try { const v = localStorage.getItem('impasto.' + k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem('impasto.' + k, JSON.stringify(v)); } catch { /* private mode: state lives for this session */ } },
  };
  const state = {
    items: [],
    device: store.get('device', N.platform === 'android' ? 'phone' : N.platform === 'windows' ? 'desktop' : (innerWidth < 720 ? 'phone' : 'desktop')),
    saved: new Set(store.get('saved', [])),
    bag: store.get('bag', []), // [{id, v}]
    library: store.get('library', []), // [{id, v, location, path, at}]
    remote: store.get('remote', cfg.remoteBase || ''),
    filter: 'All',
    sort: 'featured',
  };
  const persist = () => {
    store.set('saved', [...state.saved]);
    store.set('bag', state.bag);
    store.set('library', state.library.slice(0, 200));
    store.set('device', state.device);
  };

  // ---------- catalog ----------
  function validItem(w) {
    return w && typeof w.id === 'string' && /^[\w-]{1,40}$/.test(w.id) && typeof w.title === 'string' && w.variants &&
      ['phone', 'desktop'].some((v) => w.variants[v] && typeof w.variants[v].file === 'string' && !/^[a-z]+:|\.\./i.test(w.variants[v].file));
  }
  async function loadCatalog() {
    const local = await (await fetch(cfg.localBase + 'catalog.json')).json();
    state.featured = local.featured;
    const items = local.wallpapers.filter(validItem).map((w) => ({ ...w, _base: cfg.localBase }));
    if (state.remote) {
      try {
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 7000);
        const remote = await (await fetch(state.remote + 'catalog.json', { signal: ctl.signal, cache: 'no-cache' })).json();
        if (typeof remote.featured === 'string') state.featured = remote.featured;
        clearTimeout(t);
        const have = new Set(items.map((w) => w.id));
        for (const w of remote.wallpapers || []) if (validItem(w) && !have.has(w.id)) items.push({ ...w, _base: state.remote, _remote: true });
      } catch { /* offline or bad source: the bundled pack still works */ }
    }
    state.items = items;
  }
  const byId = (id) => state.items.find((w) => w.id === id);
  const variantOf = (w, v) => w.variants[v] || w.variants[v === 'phone' ? 'desktop' : 'phone'];
  const vKey = (w, v) => (w.variants[v] ? v : v === 'phone' ? 'desktop' : 'phone');
  const previewUrl = (w, v) => w._base + variantOf(w, v).preview;
  function fileUrl(w, v) {
    const x = w.variants[v];
    if (!x) return null;
    if (!w._remote && x.bundled !== false) return abs(w._base + x.file);
    return state.remote ? abs((w._remote ? w._base : state.remote) + x.file) : null;
  }
  const fileName = (w, v) => `impasto-${w.id}-${w.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}-${w.variants[v].width}x${w.variants[v].height}.png`;
  const settable = (v) => (N.platform === 'android' && v === 'phone') || (N.platform === 'windows' && v === 'desktop');

  // ---------- small UI helpers ----------
  const icon = (n) => `<svg class="i" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  let toastTimer;
  function toast(msg, action) {
    const t = $('#toast');
    t.innerHTML = `<span>${esc(msg)}</span>` + (action ? `<button class="toast-act">${esc(action.label)}</button>` : '');
    if (action) $('.toast-act', t).onclick = () => { action.run(); t.classList.remove('show'); };
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), 3600);
  }
  function updateCounts() {
    for (const el of [$('#bagCount'), $('#bagCountTab')]) { el.textContent = state.bag.length; el.hidden = !state.bag.length; }
  }
  function updateDeviceSeg() {
    for (const b of $$('#deviceSeg button')) b.setAttribute('aria-checked', b.dataset.device === state.device);
    document.documentElement.dataset.device = state.device;
  }

  function card(w, i = 0) {
    const v = vKey(w, state.device);
    const x = w.variants[v];
    const on = state.saved.has(w.id);
    return `<article class="card ${v}" style="--d:${Math.min(i, 12) * 45}ms">
      <a class="card-media" href="#/w/${esc(w.id)}" style="--bg:${esc(x.color || '#888')}">
        <img src="${esc(previewUrl(w, v))}" alt="${esc(w.title)}, painted wallpaper" loading="lazy" decoding="async" width="${x.width}" height="${x.height}">
      </a>
      <button class="fav" data-fav="${esc(w.id)}" aria-pressed="${on}" aria-label="${on ? 'Remove' : 'Save'} ${esc(w.title)}">${icon('heart')}</button>
      <div class="card-meta"><a href="#/w/${esc(w.id)}">${esc(w.title)}</a><span class="price">Free</span></div>
      <p class="card-sub">${esc(w.collection || 'Community')} · ${x.width} × ${x.height}</p>
    </article>`;
  }
  const grid = (list) => `<div class="grid ${state.device}">${list.map(card).join('')}</div>`;
  function empty(title, body, href, label) {
    return `<div class="empty"><h2>${esc(title)}</h2><p class="muted">${esc(body)}</p>${href ? `<a class="btn primary" href="${href}">${esc(label)}</a>` : ''}</div>`;
  }

  // ---------- views ----------
  // three cards rising out of the hero: one from another collection, the featured one, one more
  function heroCards(feat) {
    const pick = (c) => state.items.find((w) => w.collection === c && w.id !== feat.id);
    const left = pick('Savage') || state.items.find((w) => w.id !== feat.id);
    const right = pick('Cinema') || state.items.find((w) => w.id !== feat.id && w !== left);
    return [[left.collection, left], ['Featured', feat], [right.collection, right]].filter(([, w]) => w);
  }

  function homeClassic(feat, cols, list) {
    const v = vKey(feat, state.device);
    return `
    <section class="hero ${v}">
      <div class="hero-copy">
        <h1>Thick paint for thin screens.</h1>
        <p class="lede">Original wallpapers in heavy oil texture, shipped as lossless PNG at your screen's native size. Free and open source.</p>
        <div class="row"><a class="btn primary" href="#/w/${esc(feat.id)}">${icon('brush')}See ${esc(feat.title)}</a><a class="btn" href="#all">Browse all ${state.items.length}</a></div>
      </div>
      <a class="hero-art" href="#/w/${esc(feat.id)}" style="--bg:${esc(feat.variants[v].color)}">
        <img src="${esc(previewUrl(feat, v))}" alt="${esc(feat.title)}, painted wallpaper" fetchpriority="high">
        <span class="hero-tag"><b>${esc(feat.title)}</b><span>Free</span></span>
      </a>
    </section>

    <section class="block">
      <h2>Collections</h2>
      <div class="shelves">${cols.map((c) => {
        const ws = state.items.filter((w) => w.collection === c);
        return `<a class="shelf" href="#/c/${encodeURIComponent(c)}">
          <span class="fan">${ws.slice(0, 3).map((w) => `<img src="${esc(previewUrl(w, 'phone'))}" alt="" loading="lazy">`).join('')}</span>
          <span class="shelf-text"><b>${esc(c)}</b><span>${esc(COLLECTIONS[c] || '')}</span><span class="muted">${ws.length} wallpapers</span></span>
        </a>`;
      }).join('')}</div>
    </section>

    <section class="block" id="all">
      <div class="block-head">
        <h2>All wallpapers</h2>
        <div class="filters">
          <div class="chips" role="group" aria-label="Filter by collection">${['All', ...cols].map((c) => `<button class="chip" data-filter="${esc(c)}" aria-pressed="${state.filter === c}">${esc(c)}</button>`).join('')}</div>
          <label class="select"><span class="sr">Sort</span><select id="sort">
            <option value="featured"${state.sort === 'featured' ? ' selected' : ''}>Featured</option>
            <option value="new"${state.sort === 'new' ? ' selected' : ''}>Newest</option>
            <option value="az"${state.sort === 'az' ? ' selected' : ''}>A to Z</option>
          </select></label>
        </div>
      </div>
      ${list.length ? grid(list) : empty('Nothing here yet', 'This collection is empty.', '', '')}
    </section>
    ${footer()}`;
  }

  function viewHome() {
    const feat = byId(state.featured) || state.items[0];
    // known collections first, then any new ones the catalog brings
    const cols = [...new Set([...Object.keys(COLLECTIONS), ...state.items.map((w) => w.collection)])].filter((c) => c && state.items.some((w) => w.collection === c));
    let list = state.items.filter((w) => state.filter === 'All' || w.collection === state.filter);
    if (state.sort === 'az') list = [...list].sort((a, b) => a.title.localeCompare(b.title));
    if (state.sort === 'new') list = [...list].reverse();
    if (CLASSIC) return homeClassic(feat, cols, list);
    return `
    <section class="hero" aria-labelledby="heroTitle">
      <div class="beam" aria-hidden="true"></div>
      <div class="hero-in">
        <h1 id="heroTitle">Thick paint for thin <em>screens.</em></h1>
        <p class="hero-sub">Painted wallpapers as lossless PNG, at your screen's exact size. Free and open source.</p>
        <dl class="stats stats-l">
          <div><dt>Wallpapers</dt><dd>${state.items.length}</dd></div>
          <div><dt>Compression</dt><dd>0%</dd></div>
        </dl>
        <dl class="stats stats-r">
          <div><dt>Desktop</dt><dd>4K</dd></div>
          <div><dt>Phone</dt><dd>QHD+</dd></div>
        </dl>
        <a class="orb" href="#all"><img class="mark" src="mark.svg" alt=""><span>Browse</span></a>
      </div>
      <div class="hero-cards">${heroCards(feat).map(([label, w], i) => {
        const hv = vKey(w, state.device);
        return `<a class="hcard ${hv} hc${i}" href="#/w/${esc(w.id)}">
          <span class="tag">${esc(label)}</span>
          <span class="hcard-frame"><img src="${esc(previewUrl(w, hv))}" alt="${esc(w.title)}" ${i === 1 ? 'fetchpriority="high"' : 'loading="lazy"'}></span>
          <span class="hcard-meta"><b>${esc(w.title)}</b><span>Free</span></span>
        </a>`;
      }).join('')}</div>
    </section>

    <section class="block">
      <h2>The <em>collections</em></h2>
      <div class="shelves">${cols.map((c) => {
        const ws = state.items.filter((w) => w.collection === c);
        return `<a class="shelf" href="#/c/${encodeURIComponent(c)}">
          <span class="fan">${ws.slice(0, 3).map((w) => `<img src="${esc(previewUrl(w, 'phone'))}" alt="" loading="lazy">`).join('')}</span>
          <span class="shelf-text"><b>${esc(c)}</b><span>${esc(COLLECTIONS[c] || '')}</span><span class="muted">${ws.length} wallpapers</span></span>
        </a>`;
      }).join('')}</div>
    </section>

    <section class="block" id="all">
      <div class="block-head">
        <h2>Every <em>wallpaper</em></h2>
        <div class="filters">
          <div class="chips" role="group" aria-label="Filter by collection">${['All', ...cols].map((c) => `<button class="chip" data-filter="${esc(c)}" aria-pressed="${state.filter === c}">${esc(c)}</button>`).join('')}</div>
          <label class="select"><span class="sr">Sort</span><select id="sort">
            <option value="featured"${state.sort === 'featured' ? ' selected' : ''}>Featured</option>
            <option value="new"${state.sort === 'new' ? ' selected' : ''}>Newest</option>
            <option value="az"${state.sort === 'az' ? ' selected' : ''}>A to Z</option>
          </select></label>
        </div>
      </div>
      ${list.length ? grid(list) : empty('Nothing here yet', 'This collection is empty.', '', '')}
    </section>
    ${footer()}`;
  }

  function footer() {
    return `<footer class="foot">
      <p class="foot-name">${CLASSIC ? 'Impasto' : 'Imp<em>asto</em>'}</p>
      <p class="muted">Open source under MIT. Wallpapers in the starter pack are CC0, painted by code in <code>tools/paint.py</code>. ${N.platform === 'web' ? '' : `You are on the ${N.platform === 'android' ? 'Android' : 'Windows'} app, v${esc(cfg.version)}.`}</p>
      <div class="row"><a class="btn" href="#/about">About and sources</a></div>
    </footer>`;
  }

  function viewCollection(name) {
    const list = state.items.filter((w) => w.collection === name);
    return `<section class="block page-top">
      <a class="back" href="#/">${icon('back')}Shop</a>
      <div class="col-head"><h1>${esc(name)}</h1><p class="lede">${esc(COLLECTIONS[name] || '')} ${list.length} wallpapers, all free.</p></div>
      ${list.length ? grid(list) : empty('No wallpapers', 'Nothing in this collection yet.', '#/', 'Back to shop')}
    </section>`;
  }

  function clock() {
    const d = new Date();
    return { time: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }), date: d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' }) };
  }
  function mockup(w, v) {
    const c = clock();
    if (v === 'phone') return `<div class="mock phone"><div class="screen"><img src="${esc(previewUrl(w, 'phone'))}" alt="${esc(w.title)} on a phone lock screen"><div class="lock"><span class="ldate">${esc(c.date)}</span><span class="ltime">${esc(c.time)}</span></div></div></div>`;
    return `<div class="mock monitor"><div class="screen"><img src="${esc(previewUrl(w, 'desktop'))}" alt="${esc(w.title)} on a desktop"><div class="taskbar"><i></i><i></i><i></i><i></i><span>${esc(c.time)}</span></div></div><div class="stand"></div></div>`;
  }

  let currentV = null;
  function viewProduct(id) {
    const w = byId(id);
    if (!w) return empty('Wallpaper not found', 'It may have been removed from the catalog.', '#/', 'Back to shop');
    const v = currentV && w.variants[currentV] ? currentV : vKey(w, state.device);
    const x = w.variants[v];
    const url = fileUrl(w, v);
    const inBag = state.bag.some((b) => b.id === w.id && b.v === v);
    const on = state.saved.has(w.id);
    const more = state.items.filter((o) => o.collection === w.collection && o.id !== w.id);
    const primary = url && settable(v)
      ? `<button class="btn primary big" data-act="set">${icon('brush')}Set as wallpaper</button><button class="btn big" data-act="download">${icon('download')}Download PNG</button>`
      : `<button class="btn primary big" data-act="download" ${url ? '' : 'disabled'}>${icon('download')}Download PNG · ${mb(x.bytes)}</button>`;
    return `<section class="product page-top">
      <a class="back" href="#/">${icon('back')}Shop</a>
      <div class="product-grid">
        <div class="stage ${v}">${mockup(w, v)}
          <button class="btn ghost small" data-act="zoom" ${url ? '' : 'disabled'}>${icon('zoom')}Inspect the paint at 100%</button>
        </div>
        <div class="buy">
          <p class="muted"><a href="#/c/${encodeURIComponent(w.collection || '')}">${esc(w.collection || 'Community')}</a></p>
          <h1>${esc(w.title)}</h1>
          <p class="price-big">Free</p>
          <fieldset class="variants"><legend>Size</legend>
            ${['phone', 'desktop'].filter((k) => w.variants[k]).map((k) => `<label class="variant"><input type="radio" name="v" value="${k}"${k === v ? ' checked' : ''}><span>${icon(k === 'phone' ? 'phone' : 'monitor')}<b>${k === 'phone' ? 'Phone' : 'Desktop'}</b><small>${w.variants[k].width} × ${w.variants[k].height} · ${mb(w.variants[k].bytes)}</small></span></label>`).join('')}
          </fieldset>
          ${url ? '' : `<p class="note">This size isn't bundled in this app. Add a catalog source in <a href="#/about">About</a> to fetch it.</p>`}
          <div class="actions">${primary}</div>
          <div class="row tight">
            <button class="btn" data-act="bag" aria-pressed="${inBag}">${icon(inBag ? 'check' : 'bag')}${inBag ? 'In bag' : 'Add to bag'}</button>
            <button class="btn" data-act="save" aria-pressed="${on}">${icon('heart')}${on ? 'Saved' : 'Save'}</button>
            <button class="btn" data-act="share" ${url ? '' : 'disabled'}>${icon(N.platform === 'windows' ? 'copy' : 'share')}${N.platform === 'windows' ? 'Copy image' : 'Share'}</button>
          </div>
          <dl class="specs">
            <div><dt>Resolution</dt><dd>${x.width} × ${x.height}</dd></div>
            <div><dt>Format</dt><dd>${esc(w.format || 'PNG (lossless)')}</dd></div>
            <div><dt>File size</dt><dd>${mb(x.bytes)}</dd></div>
            <div><dt>Average colour</dt><dd><i class="sw" style="--c:${esc(x.color)}"></i>${esc(x.color)}</dd></div>
            <div><dt>Artist</dt><dd>${esc(w.artist || 'Unknown')}</dd></div>
            <div><dt>License</dt><dd>${esc(w.license || 'See source')}</dd></div>
            <div><dt>SHA-256</dt><dd class="hash" title="${esc(x.sha256)}">${esc((x.sha256 || '').slice(0, 16))}…</dd></div>
          </dl>
          <p class="tags">${(w.tags || []).map((t) => `<a class="chip" href="#/search?q=${encodeURIComponent(t)}">${esc(t)}</a>`).join('')}</p>
        </div>
      </div>
    </section>
    ${more.length ? `<section class="block"><h2>More from ${esc(w.collection)}</h2>${grid(more)}</section>` : ''}`;
  }

  function viewBag() {
    const rows = state.bag.map((b) => ({ b, w: byId(b.id) })).filter((r) => r.w && r.w.variants[r.b.v]);
    if (!rows.length) return `<section class="block page-top"><h1>Bag</h1>${empty('Your bag is empty', 'Add a few wallpapers and download them in one go.', '#/', 'Go shopping')}</section>`;
    const total = rows.reduce((s, r) => s + r.w.variants[r.b.v].bytes, 0);
    return `<section class="block page-top bag">
      <h1>Bag</h1>
      <div class="bag-grid">
        <ul class="lines">${rows.map(({ b, w }) => `<li class="line" data-id="${esc(w.id)}" data-v="${b.v}">
          <a class="thumb ${b.v}" href="#/w/${esc(w.id)}"><img src="${esc(previewUrl(w, b.v))}" alt=""></a>
          <div class="line-text"><a href="#/w/${esc(w.id)}"><b>${esc(w.title)}</b></a><span class="muted">${b.v === 'phone' ? 'Phone' : 'Desktop'} · ${w.variants[b.v].width} × ${w.variants[b.v].height} · ${mb(w.variants[b.v].bytes)}</span>${fileUrl(w, b.v) ? '' : '<span class="note">Not available offline</span>'}</div>
          <span class="line-state" aria-live="polite"></span>
          <button class="icon-btn" data-remove aria-label="Remove ${esc(w.title)}">${icon('trash')}</button>
        </li>`).join('')}</ul>
        <aside class="summary">
          <h2>Summary</h2>
          <dl>
            <div><dt>Wallpapers</dt><dd>${rows.length}</dd></div>
            <div><dt>Download size</dt><dd>${mb(total)}</dd></div>
            <div class="total"><dt>Total</dt><dd>Free</dd></div>
          </dl>
          <button class="btn primary big wide" id="checkout">${icon('download')}Download all</button>
          <p class="muted small">Files save to ${N.platform === 'android' ? 'Pictures/Impasto' : N.platform === 'windows' ? 'Pictures\\Impasto' : 'your Downloads folder'}.</p>
        </aside>
      </div>
    </section>`;
  }

  function receipt(lines, failed) {
    const d = new Date();
    const total = lines.reduce((s, l) => s + l.bytes, 0);
    return `<section class="block page-top receipt-wrap">
      <h1>All yours.</h1>
      <p class="lede">${lines.length} wallpaper${lines.length === 1 ? '' : 's'} downloaded${failed ? `, ${failed} failed` : ''}.</p>
      <div class="receipt" role="table" aria-label="Receipt">
        <p class="r-head">IMPASTO<br><span>${esc(d.toLocaleDateString())} ${esc(d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))}</span></p>
        ${lines.map((l) => `<p class="r-line" role="row"><span role="cell">${esc(l.title)} <small>${l.w}×${l.h}</small></span><span role="cell">${mb(l.bytes)}</span></p>`).join('')}
        <p class="r-line r-sum" role="row"><span role="cell">Data</span><span role="cell">${mb(total)}</span></p>
        <p class="r-line r-sum" role="row"><span role="cell">Paid</span><span role="cell">0.00</span></p>
        <p class="r-foot">No compression was harmed.<br>Thank you.</p>
      </div>
      <div class="row center"><a class="btn primary" href="#/library">${icon('stack')}Open library</a><a class="btn" href="#/">Keep shopping</a></div>
    </section>`;
  }

  function viewSaved() {
    const list = state.items.filter((w) => state.saved.has(w.id));
    return `<section class="block page-top"><h1>Saved</h1>${list.length ? grid(list) : empty('Nothing saved yet', 'Tap the heart on any wallpaper to keep it here.', '#/', 'Browse wallpapers')}</section>`;
  }

  function viewLibrary() {
    const rows = state.library.map((l) => ({ l, w: byId(l.id) })).filter((r) => r.w && r.w.variants[r.l.v]);
    if (!rows.length) return `<section class="block page-top"><h1>Library</h1>${empty('No downloads yet', 'Everything you download lands here, ready to set again.', '#/', 'Find a wallpaper')}</section>`;
    return `<section class="block page-top"><h1>Library</h1><p class="lede">${rows.length} download${rows.length === 1 ? '' : 's'} on this device.</p>
      <ul class="lines lib">${rows.map(({ l, w }, i) => `<li class="line" data-i="${i}">
        <a class="thumb ${l.v}" href="#/w/${esc(w.id)}"><img src="${esc(previewUrl(w, l.v))}" alt=""></a>
        <div class="line-text"><b>${esc(w.title)}</b><span class="muted">${l.v === 'phone' ? 'Phone' : 'Desktop'} · ${esc(new Date(l.at).toLocaleDateString())} · ${esc(l.location || '')}</span></div>
        <div class="row tight">
          ${settable(l.v) ? `<button class="btn small" data-lib-set="${i}">${icon('brush')}Set</button>` : ''}
          ${N.platform === 'windows' && l.path ? `<button class="btn small" data-lib-folder="${i}">${icon('folder')}Show</button>` : ''}
        </div>
      </li>`).join('')}</ul></section>`;
  }

  function viewSearch(q) {
    const t = q.trim().toLowerCase();
    const list = t ? state.items.filter((w) => [w.title, w.collection, ...(w.tags || [])].join(' ').toLowerCase().includes(t)) : [];
    const tags = [...new Set(state.items.flatMap((w) => w.tags || []))].slice(0, 14);
    return `<section class="block page-top">
      <h1>Search</h1>
      <form class="search big" role="search" id="searchForm2">${icon('search')}<input id="q2" type="search" value="${esc(q)}" placeholder="Try red, sunset or serif" aria-label="Search wallpapers" autocomplete="off"></form>
      ${t ? (list.length ? `<p class="lede">${list.length} result${list.length === 1 ? '' : 's'} for “${esc(q)}”</p>${grid(list)}` : empty('No matches', `Nothing matches “${q}”. Try a colour or a mood.`, '', '')) : `<p class="tags">${tags.map((x) => `<a class="chip" href="#/search?q=${encodeURIComponent(x)}">${esc(x)}</a>`).join('')}</p>`}
    </section>`;
  }

  function viewAbout() {
    const local = state.items.filter((w) => !w._remote).length;
    return `<section class="block page-top about">
      <h1>About Impasto</h1>
      <div class="about-grid">
        <div>
          <p class="lede">An open-source wallpaper store. No accounts, no ads, no tracking, no compression.</p>
          <p>Every file is a PNG at the exact pixel size of the screen it's made for, so nothing gets resized or re-encoded on the way to your device. ${local} wallpapers ship inside this app.</p>
          <p>Anyone can add wallpapers: put the PNGs in <code>catalog/wallpapers</code>, list them in <code>catalog/catalog.json</code> and open a pull request. Once merged, they appear here for everyone.</p>
          ${cfg.repoUrl ? `<div class="row"><button class="btn" data-ext="${esc(cfg.repoUrl)}">Source code</button></div>` : ''}
        </div>
        <form class="source" id="sourceForm">
          <h2>Catalog source</h2>
          <p class="muted">A public folder that holds a <code>catalog.json</code>. Leave empty to use only the bundled pack.</p>
          <label for="remote">Source URL</label>
          <input id="remote" type="url" inputmode="url" placeholder="https://raw.githubusercontent.com/you/impasto/main/catalog/" value="${esc(state.remote)}">
          <p class="field-error" id="remoteErr" hidden></p>
          <div class="row tight"><button class="btn primary">Save source</button>${state.remote ? '<button class="btn" type="button" id="clearRemote">Remove</button>' : ''}</div>
          <p class="muted small">${state.items.filter((w) => w._remote).length} wallpapers loaded from this source.</p>
        </form>
      </div>
    </section>${footer()}`;
  }

  // ---------- actions ----------
  async function doDownload(w, v, quiet) {
    const url = fileUrl(w, v);
    if (!url) throw new Error('Not available here');
    const r = await N.save(url, fileName(w, v));
    state.library = [{ id: w.id, v, location: r.location || '', path: r.path || r.uri || '', at: Date.now() }, ...state.library.filter((l) => !(l.id === w.id && l.v === v))];
    persist();
    if (!quiet) toast(`Saved to ${r.location || 'your device'}`, N.platform === 'windows' && r.path ? { label: 'Show', run: () => N.showInFolder(r.path) } : null);
    return r;
  }
  function askWhich() {
    if (N.platform !== 'android') return Promise.resolve('desktop');
    const d = $('#setSheet');
    return new Promise((res) => {
      d.returnValue = '';
      d.addEventListener('close', () => res(d.returnValue === 'cancel' ? '' : d.returnValue), { once: true });
      d.showModal();
    });
  }
  async function doSet(w, v) {
    const which = await askWhich();
    if (!which) return;
    toast('Setting wallpaper…');
    await N.setWallpaper(fileUrl(w, v), fileName(w, v), which);
    toast(which === 'lock' ? 'Lock screen updated' : which === 'home' ? 'Home screen updated' : 'Wallpaper set');
  }
  const fail = (e) => toast(e && e.message ? e.message : 'Something went wrong. Try again.');
  function toggleSave(id) {
    state.saved.has(id) ? state.saved.delete(id) : state.saved.add(id);
    persist();
    return state.saved.has(id);
  }
  function openZoom(w, v) {
    const z = $('#zoom');
    $('#zoomTitle').textContent = `${w.title} · ${w.variants[v].width} × ${w.variants[v].height} · actual pixels`;
    const img = $('#zoomImg');
    img.alt = `${w.title} at full resolution`;
    img.src = fileUrl(w, v);
    z.showModal();
    img.onload = () => { const s = $('#zoomStage'); s.scrollLeft = (img.naturalWidth - s.clientWidth) / 2; s.scrollTop = (img.naturalHeight - s.clientHeight) / 2; };
  }

  async function checkout() {
    const btn = $('#checkout');
    btn.disabled = true;
    btn.innerHTML = `${icon('download')}Downloading…`;
    const done = [];
    let failed = 0;
    for (const li of $$('.line')) {
      const w = byId(li.dataset.id), v = li.dataset.v;
      const st = $('.line-state', li);
      li.classList.add('busy');
      st.textContent = 'Saving';
      try {
        await doDownload(w, v, true);
        li.classList.replace('busy', 'ok');
        st.innerHTML = icon('check') + '<span class="sr">Saved</span>';
        done.push({ title: w.title, w: w.variants[v].width, h: w.variants[v].height, bytes: w.variants[v].bytes });
        state.bag = state.bag.filter((b) => !(b.id === w.id && b.v === v));
      } catch (e) {
        failed++;
        li.classList.replace('busy', 'err');
        st.textContent = 'Failed';
      }
    }
    persist();
    updateCounts();
    if (done.length) { main.innerHTML = receipt(done, failed); main.focus(); }
    else { btn.disabled = false; btn.innerHTML = `${icon('download')}Try again`; toast('Downloads failed. Check your connection or the catalog source.'); }
  }

  // ---------- router ----------
  function route() {
    const h = location.hash.slice(1) || '/';
    const [path, qs] = h.split('?');
    const parts = path.split('/').filter(Boolean);
    const q = new URLSearchParams(qs || '').get('q') || '';
    let html, nav = parts[0] || 'shop';
    if (path === '/' || !parts.length) html = viewHome();
    else if (parts[0] === 'w') { if (route.lastId !== parts[1]) currentV = null; route.lastId = parts[1]; html = viewProduct(decodeURIComponent(parts[1] || '')); nav = 'shop'; }
    else if (parts[0] === 'c') { html = viewCollection(decodeURIComponent(parts[1] || '')); nav = 'shop'; }
    else if (parts[0] === 'bag') html = viewBag();
    else if (parts[0] === 'saved') html = viewSaved();
    else if (parts[0] === 'library') html = viewLibrary();
    else if (parts[0] === 'search') html = viewSearch(q);
    else if (parts[0] === 'about') html = viewAbout();
    else { if (h === 'all') return; html = empty('Page not found', 'That link goes nowhere.', '#/', 'Back to shop'); }
    main.innerHTML = html;
    main.dataset.view = parts[0] || 'home';
    for (const a of $$('[data-nav]')) a.dataset.nav === nav ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current');
    if (!route.keepScroll) window.scrollTo(0, 0);
    route.keepScroll = false;
    if (parts[0] === 'search') { const i = $('#q2'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }
  }
  const rerender = () => { route.keepScroll = true; route(); };

  // ---------- events (delegated) ----------
  document.addEventListener('click', async (e) => {
    const t = e.target.closest('button, a');
    if (!t) return;
    if (t.matches('a[href="#all"]')) { e.preventDefault(); $('#all')?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }); return; }
    if (t.dataset.fav) { const on = toggleSave(t.dataset.fav); t.setAttribute('aria-pressed', on); t.setAttribute('aria-label', (on ? 'Remove ' : 'Save ') + byId(t.dataset.fav).title); if (main.dataset.view === 'saved') rerender(); return; }
    if (t.dataset.device) { state.device = t.dataset.device; persist(); updateDeviceSeg(); currentV = null; rerender(); return; }
    if (t.dataset.filter) { state.filter = t.dataset.filter; rerender(); return; }
    if (t.dataset.ext) { N.openExternal(t.dataset.ext); return; }
    if (t.hasAttribute('data-remove')) { const li = t.closest('.line'); state.bag = state.bag.filter((b) => !(b.id === li.dataset.id && b.v === li.dataset.v)); persist(); updateCounts(); rerender(); return; }
    if (t.id === 'checkout') return checkout();
    if (t.id === 'clearRemote') { state.remote = ''; store.set('remote', ''); await loadCatalog(); rerender(); toast('Source removed'); return; }
    if (t.dataset.libSet) { const l = state.library[+t.dataset.libSet]; doSet(byId(l.id), l.v).catch(fail); return; }
    if (t.dataset.libFolder) { N.showInFolder(state.library[+t.dataset.libFolder].path); return; }
    const act = t.dataset.act;
    if (act && main.dataset.view === 'w') {
      const w = byId(route.lastId);
      const v = $('input[name="v"]:checked').value;
      try {
        if (act === 'download') { t.disabled = true; await doDownload(w, v); t.disabled = false; }
        if (act === 'set') { await doSet(w, v); }
        if (act === 'bag') { const i = state.bag.findIndex((b) => b.id === w.id && b.v === v); i >= 0 ? state.bag.splice(i, 1) : state.bag.push({ id: w.id, v }); persist(); updateCounts(); currentV = v; rerender(); if (i < 0) toast('Added to bag', { label: 'View bag', run: () => (location.hash = '#/bag') }); }
        if (act === 'save') { toggleSave(w.id); currentV = v; rerender(); }
        if (act === 'share') { const r = await N.share(fileUrl(w, v), fileName(w, v), w.title, location.href); if (r && r.copied) toast('Image copied. Paste it anywhere.'); if (r && r.linkCopied) toast('Link copied'); }
        if (act === 'zoom') openZoom(w, v);
      } catch (err) { t.disabled = false; fail(err); }
    }
  });
  document.addEventListener('change', (e) => {
    if (e.target.name === 'v') { currentV = e.target.value; rerender(); }
    if (e.target.id === 'sort') { state.sort = e.target.value; rerender(); }
  });
  document.addEventListener('submit', async (e) => {
    if (e.target.id === 'searchForm' || e.target.id === 'searchForm2') {
      e.preventDefault();
      const q = (e.target.querySelector('input').value || '').trim();
      location.hash = '#/search?q=' + encodeURIComponent(q);
    }
    if (e.target.id === 'sourceForm') {
      e.preventDefault();
      let u = $('#remote').value.trim();
      const err = $('#remoteErr');
      if (u && !/^https:\/\/[^\s]+$/i.test(u)) { err.hidden = false; err.textContent = 'Use a full https:// address.'; return; }
      if (u && !u.endsWith('/')) u += '/';
      state.remote = u;
      store.set('remote', u);
      await loadCatalog();
      rerender();
      toast(u ? `Source saved. ${state.items.filter((w) => w._remote).length} wallpapers added.` : 'Source cleared');
    }
  });
  let qTimer;
  document.addEventListener('input', (e) => {
    if (e.target.id === 'q2') { clearTimeout(qTimer); const v = e.target.value; qTimer = setTimeout(() => history.replaceState(null, '', '#/search?q=' + encodeURIComponent(v)) || rerender(), 160); }
  });
  window.addEventListener('hashchange', route);
  setInterval(() => { for (const el of $$('.ltime, .taskbar span')) el.textContent = clock().time; }, 15000);

  // ---------- boot ----------
  (async function boot() {
    updateDeviceSeg();
    updateCounts();
    document.documentElement.dataset.platform = N.platform;
    N.setChrome(getComputedStyle(document.body).backgroundColor, false); // dark ground: light status-bar icons
    try {
      await loadCatalog();
      route();
    } catch (e) {
      main.innerHTML = empty('The catalog didn\'t load', 'Restart the app. If it keeps happening, reinstall it.', '', '');
    }
  })();
})();
