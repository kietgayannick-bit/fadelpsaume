'use strict';
/* Compatibilité anciens navigateurs (Android WebView / Chrome < 90) */
(function () {
  var P = [Element.prototype, DocumentFragment.prototype];
  P.forEach(function (p) {
    if (!p.replaceChildren) {
      p.replaceChildren = function () {
        while (this.firstChild) this.removeChild(this.firstChild);
        this.append.apply(this, arguments);
      };
    }
  });
  if (!String.prototype.padStart) {
    String.prototype.padStart = function (n, s) { var r = String(this); s = s || ' '; while (r.length < n) r = s + r; return r; };
  }
  window.addEventListener('error', function (e) {
    var b = document.getElementById('errorMsg');
    if (b) { b.hidden = false; b.textContent = 'Erreur interface : ' + (e.message || e.error) + ' (ligne ' + (e.lineno || '?') + ')'; }
  });
  window.addEventListener('unhandledrejection', function (e) {
    var b = document.getElementById('errorMsg');
    if (b) { b.hidden = false; b.textContent = 'Erreur interface : ' + (e.reason && e.reason.message || e.reason); }
  });
})();
/* Fadelpsaume — interface. Aucune dépendance externe (fonctionne hors ligne). */

const $ = (s, r = document) => r.querySelector(s);

/* ------------------------------------------------------------------ icônes */
const ICONS = {
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  power: '<path d="M18.36 6.64a9 9 0 1 1-12.73 0M12 2v10"/>',
  arrowUp: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  arrowDown: '<path d="M12 5v14M19 12l-7 7-7-7"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  edit: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  share: '<path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8M16 6l-4-4-4 4M12 2v13"/>',
  trash: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  x: '<path d="M18 6L6 18M6 6l12 12"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6"/>',
  clipboard: '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/>',
  server: '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
  terminal: '<path d="M4 17l6-6-6-6M12 19h8"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  refresh: '<path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  alert: '<path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
};

function icon(name) {
  const t = document.createElement('template');
  t.innerHTML = '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">' + (ICONS[name] || '') + '</svg>';
  return t.content.firstChild;
}

/* ----------------------------------------------------------------- helpers */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'on') for (const [ev, fn] of Object.entries(v)) el.addEventListener(ev, fn);
    else if (k === 'value' || k === 'checked' || k === 'disabled') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  const add = (c) => {
    if (c == null || c === false) return;
    if (Array.isArray(c)) c.forEach(add);
    else el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  };
  kids.forEach(add);
  return el;
}

const PROTO = { vmess: 'VMess', vless: 'VLESS', trojan: 'Trojan', ss: 'Shadowsocks', sshdns: 'SSH SlowDNS' };

function fmtBytes(n) {
  n = Number(n) || 0;
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i === 0 ? n.toFixed(0) : n.toFixed(n >= 100 ? 0 : n >= 10 ? 1 : 2)) + ' ' + u[i];
}
const fmtSpeed = (n) => fmtBytes(n) + '/s';
function fmtTime(sec) {
  sec = Math.max(0, Math.floor(sec));
  const p = (x) => String(x).padStart(2, '0');
  return p(Math.floor(sec / 3600)) + ':' + p(Math.floor((sec % 3600) / 60)) + ':' + p(sec % 60);
}
function today(offsetDays = 0) {
  const d = new Date(); d.setDate(d.getDate() + offsetDays);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

async function api(path, opts = {}) {
  const r = await fetch('/api' + path, {
    method: opts.method || 'GET',
    headers: { 'X-FDLP': '1', 'Content-Type': 'application/json' },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  let data = null;
  try { data = await r.json(); } catch (e) { /* vide */ }
  if (!r.ok) throw new Error((data && data.error) || 'Erreur ' + r.status);
  return data;
}

function toast(msg, kind = 'ok', ms = 2800) {
  const t = h('div', { class: 'toast ' + kind }, icon(kind === 'err' ? 'alert' : 'check'), msg);
  $('#toasts').append(t);
  setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 300); }, ms);
}

const AND = window.FadelAndroid || null;   // pont Java quand l'application est un APK

async function copyText(text) {
  if (AND) { try { return !!AND.copy(String(text)); } catch (e) { /* repli */ } }
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
    const ta = h('textarea', { style: 'position:fixed;opacity:0;top:0' });
    ta.value = text;
    document.body.append(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (e2) { /* rien */ }
    ta.remove();
    return ok;
  }
}

function download(name, text, type = 'application/octet-stream') {
  if (AND) {
    let where = '';
    try { where = AND.saveFile(name, text); } catch (e) { where = ''; }
    return where || false;
  }
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = h('a', { href: url, download: name });
  document.body.append(a);
  a.click();
  setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 1500);
}

/* ------------------------------------------------------------------ feuilles */
const openSheets = [];

function openSheet(title, build, opts = {}) {
  const body = h('div', { class: 'sheet-body' });
  const overlay = h('div', { class: 'overlay' });
  let closed = false;
  const entry = { close };
  function close() {
    if (closed) return;
    closed = true;
    const i = openSheets.indexOf(entry);
    if (i >= 0) openSheets.splice(i, 1);
    if (opts.onClose) opts.onClose();
    const sh = overlay.firstChild;
    if (sh) sh.classList.add('closing');
    setTimeout(() => overlay.remove(), 190);
  }
  const sheet = h('div', { class: 'sheet', role: 'dialog', 'aria-label': title },
    h('div', { class: 'grab' }),
    h('div', { class: 'sheet-head' }, h('h3', {}, title),
      h('button', { class: 'icon-btn', 'aria-label': 'Fermer', on: { click: close } }, icon('x'))),
    body);
  overlay.append(sheet);
  overlay.addEventListener('mousedown', (e) => { if (e.target === overlay) close(); });
  $('#sheets').append(overlay);
  openSheets.push(entry);
  build(body, close);
  return entry;
}
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && openSheets.length) openSheets[openSheets.length - 1].close();
});

function menuItem(ic, color, title, desc, onclick) {
  return h('button', { class: 'menu-item', on: { click: onclick } },
    h('span', { class: 'mi ' + color }, icon(ic)),
    h('span', {}, h('div', { class: 't' }, title), desc ? h('div', { class: 'd' }, desc) : null));
}

function field(label, input, hint) {
  return h('div', { class: 'field' }, h('label', {}, label), input, hint ? h('div', { class: 'hint' }, hint) : null);
}

function confirmSheet(title, message, label, fn) {
  openSheet(title, (body, close) => {
    body.append(
      h('p', { style: 'margin:4px 2px 16px;color:var(--mut);line-height:1.5' }, message),
      h('button', { class: 'btn danger', on: { click: async () => { close(); await fn(); } } }, icon('trash'), label),
      h('button', { class: 'btn ghost', on: { click: close } }, 'Annuler'));
  });
}

/* --------------------------------------------------------------------- état */
let S = null;                // dernier état reçu
let clockOffset = 0;         // décalage horloge serveur - client
let pings = {};
let lastSig = '';
let lastError = false;

const STATE_LABEL = { idle: 'Déconnecté', connecting: 'Connexion…', connected: 'Connecté', error: 'Échec de connexion' };
const POWER_LABEL = { idle: 'Connecter', connecting: 'Annuler', connected: 'Déconnecter', error: 'Réessayer' };

async function refresh() {
  if (document.hidden) return;
  try {
    S = await api('/state');
    clockOffset = S.now - Date.now() / 1000;
    lastError = false;
    render();
  } catch (e) {
    if (!lastError) { lastError = true; toast(AND ? 'Le moteur interne ne répond plus. Ferme puis rouvre l\'application.' : 'Connexion au serveur local perdue. Relance « fadelpsaume » dans Termux.', 'err', 5000); }
  }
}

function activeServer() {
  const id = S.status.state !== 'idle' && S.status.server_id ? S.status.server_id : S.active;
  return S.servers.find((s) => s.id === id) || null;
}

function serverDesc(s) {
  if (s.locked) return 'Serveur verrouillé' + (s.expires ? ' · expire le ' + s.expires : '');
  let d;
  if (s.protocol === 'sshdns') {
    d = (s.ns_domain || s.address || '?') + (s.address && !s.ns_domain ? ':' + s.port : '') + ' · SlowDNS';
  } else {
    d = s.address + ':' + s.port;
    if (s.protocol !== 'ss') d += ' · ' + (s.network || 'tcp') + (s.security && s.security !== 'none' ? '+' + s.security : '');
  }
  if (s.expired) d += ' · EXPIRÉ';
  else if (s.expires) d += ' · expire le ' + s.expires;
  return d;
}

function render() {
  const st = S.status;
  document.body.className = st.state;
  $('#statusLabel').textContent = STATE_LABEL[st.state] || '';
  const pb = $('#powerBtn');
  pb.className = 'power ' + st.state;
  $('#powerLabel').textContent = POWER_LABEL[st.state];
  const em = $('#errorMsg');
  em.hidden = st.state !== 'error';
  em.textContent = st.message || '';

  const a = activeServer();
  $('#activeName').textContent = a ? a.name : 'Aucun serveur';
  $('#activeSub').textContent = a ? serverDesc(a) : 'Ajoute un serveur avec le bouton +';
  const b = $('#activeBadge');
  b.hidden = !a;
  if (a) { b.className = 'badge ' + a.protocol; b.textContent = PROTO[a.protocol]; }

  const live = st.state === 'connected';
  $('#sentBytes').textContent = fmtBytes(live ? st.up : 0);
  $('#recvBytes').textContent = fmtBytes(live ? st.down : 0);
  $('#speed').replaceChildren(h('div', {}, '↓ ' + fmtSpeed(live ? st.down_speed : 0)), h('div', {}, '↑ ' + fmtSpeed(live ? st.up_speed : 0)));
  tick();

  const fn = $('#footnote');
  fn.replaceChildren();
  if (!S.engine.xray) {
    fn.append(h('span', { style: 'color:var(--amber)' }, S.android ? '⚠ Moteur Xray introuvable : réinstalle l\'application.' : '⚠ Moteur Xray introuvable. Dans Termux, lance : fadelpsaume install-engine'));
  } else {
    fn.append('Proxy local : SOCKS5 127.0.0.1:' + S.ports.socks + ' · HTTP 127.0.0.1:' + S.ports.http);
  }

  const sig = JSON.stringify([S.servers, S.active, st.state, st.server_id, pings]);
  if (sig !== lastSig) { lastSig = sig; renderServers(); }
}

function tick() {
  if (!S) return;
  const st = S.status;
  $('#timer').textContent = st.state === 'connected' && st.since
    ? fmtTime(Date.now() / 1000 + clockOffset - st.since) : '00:00:00';
}

function pingEl(s) {
  if (!(s.id in pings)) return h('span', { class: 'ping none' }, '');
  const p = pings[s.id];
  if (p == null) return h('span', { class: 'ping none' }, s.address && !s.locked ? 'timeout' : '—');
  return h('span', { class: 'ping ' + (p < 200 ? 'good' : p < 500 ? 'mid' : 'bad') }, p + ' ms');
}

function renderServers() {
  const list = $('#serverList');
  $('#serverCount').textContent = S.servers.length ? '(' + S.servers.length + ')' : '';
  list.replaceChildren();
  if (!S.servers.length) {
    list.append(h('div', { class: 'empty' }, icon('server'), h('br'), h('b', {}, 'Aucun serveur'), h('br'),
      'Appuie sur ', h('b', {}, '+'), ' pour importer un lien (vless://, vmess://, trojan://, ss://) ou ajouter un serveur à la main.'));
    return;
  }
  const st = S.status;
  const curId = st.state !== 'idle' ? st.server_id : S.active;
  for (const s of S.servers) {
    const liveNow = st.state === 'connected' && st.server_id === s.id;
    list.append(h('div', {
      class: 'srv' + (curId === s.id ? ' sel' : '') + (liveNow ? ' live' : '') + (s.expired ? ' expired' : ''),
      on: { click: () => selectServer(s) },
    },
      h('div', { class: 'top' },
        h('div', { class: 'info' },
          h('div', { class: 'nm' }, s.locked ? icon('lock') : null, s.name),
          h('div', { class: 'ad' }, serverDesc(s))),
        h('div', { class: 'meta' },
          h('span', { class: 'badge ' + s.protocol }, PROTO[s.protocol]),
          pingEl(s))),
      h('div', { class: 'acts', on: { click: (e) => e.stopPropagation() } },
        h('button', { class: 'mini', 'aria-label': 'Modifier', on: { click: () => editServer(s) } }, icon('edit')),
        h('button', { class: 'mini', 'aria-label': 'Partager', on: { click: () => shareServer(s) } }, icon('share')),
        h('button', { class: 'mini del', 'aria-label': 'Supprimer', on: { click: () => deleteServer(s) } }, icon('trash')))));
  }
}

/* ------------------------------------------------------------------ actions */
async function onPower() {
  const st = S.status.state;
  try {
    if (st === 'connected' || st === 'connecting') {
      await api('/disconnect', { method: 'POST' });
    } else {
      const a = activeServer() || S.servers[0];
      if (!a) { toast('Ajoute d\'abord un serveur.', 'err'); openAddMenu(); return; }
      await api('/connect', { method: 'POST', body: { id: a.id } });
    }
  } catch (e) { toast(e.message, 'err', 4000); }
  refresh();
}

async function selectServer(s) {
  if (s.expired) { toast('Ce serveur a expiré.', 'err'); return; }
  const st = S.status;
  try {
    if (st.state === 'idle' || st.state === 'error') {
      if (S.active === s.id) return;
      await api('/active', { method: 'POST', body: { id: s.id } });
    } else if (st.server_id !== s.id) {
      await api('/connect', { method: 'POST', body: { id: s.id } });
      toast('Changement de serveur…');
    }
  } catch (e) { toast(e.message, 'err'); }
  refresh();
}

function editServer(s) {
  if (s.locked) { toast('Serveur verrouillé : modification impossible.', 'err'); return; }
  openServerForm(s);
}

function deleteServer(s) {
  confirmSheet('Supprimer le serveur', 'Supprimer « ' + s.name + ' » ? Cette action est définitive.', 'Supprimer', async () => {
    try { await api('/servers/' + s.id, { method: 'DELETE' }); toast('Serveur supprimé.'); } catch (e) { toast(e.message, 'err'); }
    refresh();
  });
}

function shareServer(s) {
  if (s.locked) { toast('Serveur verrouillé : partage impossible.', 'err'); return; }
  openExport([s.id]);
}

async function pingAll() {
  if (!S.servers.length) return;
  const btn = $('#btnPing');
  btn.classList.add('spin');
  try { pings = await api('/ping', { method: 'POST', body: { ids: S.servers.map((s) => s.id) } }); } catch (e) { toast(e.message, 'err'); }
  btn.classList.remove('spin');
  render();
}

/* ------------------------------------------------------------- menu « + » */
function openAddMenu() {
  openSheet('Ajouter', (body, close) => {
    const go = (fn) => () => { close(); setTimeout(fn, 200); };
    body.append(
      menuItem('download', 'c1', 'Importer', 'Fichier .fdlp ou presse-papier (vless://, vmess://, trojan://, ss://)', go(openImport)),
      menuItem('upload', 'c2', 'Exporter', 'Fichier .rmv ou presse-papier', go(() => openExport())),
      menuItem('plus', 'c3', 'Ajouter un serveur', 'VMess, VLESS, Trojan ou Shadowsocks — saisie manuelle', go(() => openServerForm(null))),
      menuItem('terminal', 'c4', 'Ajouter un serveur SSH SlowDNS', 'Nom, Name Server, DNS resolver, IP, port…', go(() => openServerForm(null, 'sshdns'))));
  });
}

/* ---------------------------------------------------------------- import */
async function doImport(text, close) {
  if (!text || !text.trim()) { toast('Rien à importer.', 'err'); return; }
  try {
    const r = await api('/import', { method: 'POST', body: { text } });
    const parts = [];
    if (r.added) parts.push(r.added + ' serveur' + (r.added > 1 ? 's importés' : ' importé'));
    if (r.duplicates) parts.push(r.duplicates + ' doublon' + (r.duplicates > 1 ? 's ignorés' : ' ignoré'));
    if (r.errors && r.errors.length && r.added) parts.push(r.errors.length + ' lien(s) invalide(s)');
    toast(parts.join(' · ') || 'Aucun nouveau serveur.', r.added ? 'ok' : 'err', 3500);
    if (r.note) setTimeout(() => toast('Message : ' + r.note, 'ok', 7000), 600);
    if (close) close();
    refresh();
  } catch (e) { toast(e.message, 'err', 4500); }
}

function openImport() {
  openSheet('Importer', (body, close) => {
    const ta = h('textarea', { class: 'inp', placeholder: 'vless://…\nvmess://…\ntrojan://…\nss://…', spellcheck: 'false', autocapitalize: 'off' });
    const fi = $('#fileInput');
    fi.onchange = async () => {
      const f = fi.files && fi.files[0];
      fi.value = '';
      if (!f) return;
      const name = f.name.toLowerCase();
      if (!/\.(fdlp|rmv|txt)$/.test(name)) toast('Extension inattendue : on essaie quand même.', 'ok');
      doImport(await f.text(), close);
    };
    body.append(
      menuItem('file', 'c1', 'Depuis un fichier', 'Choisis un fichier .fdlp (ou .rmv)', () => fi.click()),
      menuItem('clipboard', 'c3', 'Depuis le presse-papier', 'Colle automatiquement les liens copiés', async () => {
        try {
          const t = AND ? String(AND.paste() || '') : await navigator.clipboard.readText();
          if (!t.trim()) { toast('Le presse-papier est vide.', 'err'); return; }
          doImport(t, close);
        } catch (e) {
          toast('Accès au presse-papier refusé : colle les liens ci-dessous.', 'err', 4000);
          ta.focus();
        }
      }),
      h('div', { class: 'sep' }, 'ou colle ici'),
      ta,
      h('button', { class: 'btn primary', on: { click: () => doImport(ta.value, close) } }, icon('download'), 'Importer'));
  });
}

/* ---------------------------------------------------------------- export */
function openExport(preselect) {
  openSheet('Exporter', (body, close) => {
    const selected = new Set(preselect || []);
    if (!preselect) S.servers.filter((s) => !s.locked).forEach((s) => selected.add(s.id));
    let mode = 'file';

    const name = h('input', { class: 'inp', value: 'Fadelpsaume-' + today().replace(/-/g, ''), autocomplete: 'off', spellcheck: 'false' });
    const date = h('input', { class: 'inp', type: 'date', min: today() });
    const note = h('textarea', { class: 'inp', style: 'min-height:64px', placeholder: 'Ex : accès valable pour 1 mois', maxlength: '300' });
    const lockChk = h('input', { type: 'checkbox' });
    const chip = (label, days) => h('button', { type: 'button', on: { click: () => { date.value = days == null ? '' : today(days); } } }, label);

    const fileBox = h('div', {},
      field('Nom du fichier', h('div', { style: 'display:flex;gap:8px;align-items:center' }, name, h('span', { class: 'mono', style: 'color:var(--mut)' }, '.rmv'))),
      field('Date d\'expiration', date,
        'Après cette date, le fichier ne pourra plus être importé et les serveurs cessent de fonctionner.'),
      h('div', { class: 'chips', style: 'margin:-6px 0 14px' }, chip('7 jours', 7), chip('30 jours', 30), chip('90 jours', 90), chip('Sans limite', null)),
      field('Message pour le destinataire (facultatif)', note),
      h('label', { class: 'check' }, lockChk,
        h('span', {}, h('div', { class: 't' }, 'Verrouiller les serveurs'),
          h('div', { class: 'd' }, 'Le destinataire pourra les utiliser, mais ni les voir, ni les modifier, ni les ré-exporter.'))));

    const countEl = h('span');
    const rows = h('div');
    function drawRows() {
      rows.replaceChildren();
      for (const s of S.servers) {
        const off = !!s.locked;
        const cb = h('input', { type: 'checkbox', checked: selected.has(s.id) && !off, disabled: off,
          on: { change: () => { cb.checked ? selected.add(s.id) : selected.delete(s.id); upd(); } } });
        rows.append(h('label', { class: 'pick' + (off ? ' off' : '') }, cb,
          h('div', { class: 'info' }, h('div', { class: 'nm' }, s.name), h('div', { class: 'ad' }, off ? 'Verrouillé — export impossible' : serverDesc(s))),
          h('span', { class: 'badge ' + s.protocol }, PROTO[s.protocol])));
      }
    }
    function upd() { countEl.textContent = selected.size + ' sélectionné' + (selected.size > 1 ? 's' : ''); }

    const goBtn = h('button', { class: 'btn primary', on: { click: run } });
    const shareBtn = (navigator.share || AND) ? h('button', { class: 'btn ghost', on: { click: () => run(true) } }, icon('share'), 'Créer et partager…') : null;

    const segFile = h('button', { class: 'on', on: { click: () => setMode('file') } }, icon('file'), 'Fichier .rmv');
    const segClip = h('button', { on: { click: () => setMode('clip') } }, icon('clipboard'), 'Presse-papier');
    function setMode(m) {
      mode = m;
      segFile.classList.toggle('on', m === 'file');
      segClip.classList.toggle('on', m === 'clip');
      fileBox.hidden = m !== 'file';
      if (shareBtn) shareBtn.hidden = m !== 'file';
      goBtn.replaceChildren(icon(m === 'file' ? 'download' : 'copy'), m === 'file' ? 'Créer le fichier .rmv' : 'Copier les liens');
    }

    async function run(share) {
      const ids = S.servers.filter((s) => selected.has(s.id) && !s.locked).map((s) => s.id);
      if (!ids.length) { toast('Sélectionne au moins un serveur.', 'err'); return; }
      try {
        if (mode === 'clip') {
          const r = await api('/export', { method: 'POST', body: { ids, mode: 'clipboard' } });
          if (await copyText(r.text)) { toast(r.count + ' lien(s) copié(s).'); close(); }
          else toast('Copie impossible : autorise le presse-papier.', 'err');
          return;
        }
        const r = await api('/export', { method: 'POST', body: {
          ids, mode: 'file', filename: name.value, expires: date.value, note: note.value, locked: lockChk.checked } });
        if (share === true && AND) {
          AND.shareFile(r.filename, r.content);
          close();
          return;
        }
        if (share === true) {
          const file = new File([r.content], r.filename, { type: 'text/plain' });
          if (navigator.canShare && navigator.canShare({ files: [file] })) {
            try { await navigator.share({ files: [file], title: r.filename }); close(); return; }
            catch (e) { if (e.name === 'AbortError') return; }
          }
        }
        const saved = download(r.filename, r.content);
        if (AND && !saved) { toast('Impossible d\'enregistrer le fichier.', 'err'); return; }
        toast('Fichier « ' + r.filename + ' » créé' + (typeof saved === 'string' && saved ? ' dans ' + saved : '') + ' (' + r.count + ' serveur' + (r.count > 1 ? 's' : '') + ').', 'ok', 5000);
        close();
      } catch (e) { toast(e.message, 'err', 4000); }
    }

    drawRows(); upd();
    body.append(
      h('div', { class: 'seg' }, segFile, segClip),
      fileBox,
      h('div', { class: 'sep' }, 'Serveurs à exporter'),
      S.servers.length ? h('div', { class: 'pick-tools' }, countEl,
        h('span', {}, h('button', { on: { click: () => { S.servers.filter((s) => !s.locked).forEach((s) => selected.add(s.id)); drawRows(); upd(); } } }, 'Tout'),
          ' · ', h('button', { on: { click: () => { selected.clear(); drawRows(); upd(); } } }, 'Aucun'))) : null,
      S.servers.length ? rows : h('div', { class: 'empty' }, 'Aucun serveur à exporter.'),
      goBtn, shareBtn);
    setMode('file');
  });
}

/* ----------------------------------------------- formulaire serveur (modif) */
const NETWORKS = [['tcp', 'TCP'], ['ws', 'WebSocket'], ['grpc', 'gRPC'], ['h2', 'HTTP/2'], ['httpupgrade', 'HTTPUpgrade'], ['xhttp', 'XHTTP'], ['kcp', 'mKCP']];
const SECURITIES = [['none', 'Aucune'], ['tls', 'TLS'], ['reality', 'Reality']];
const SS_METHODS = ['aes-256-gcm', 'aes-128-gcm', 'chacha20-ietf-poly1305', 'xchacha20-ietf-poly1305',
  '2022-blake3-aes-128-gcm', '2022-blake3-aes-256-gcm', '2022-blake3-chacha20-poly1305', 'none'];
const FPS = [['', 'Par défaut'], ['chrome', 'Chrome'], ['firefox', 'Firefox'], ['safari', 'Safari'], ['ios', 'iOS'], ['android', 'Android'], ['edge', 'Edge'], ['randomized', 'Aléatoire']];

function openServerForm(existing, forceProto) {
  const editing = !!existing;
  const d = Object.assign({ protocol: forceProto || 'vless', network: 'tcp', security: 'none', port: 443, alterId: 0, method: 'aes-256-gcm', dns_type: 'udp' }, existing || {});
  if (!editing && forceProto === 'sshdns') d.port = 22;
  if (!editing) d.encryption = d.protocol === 'vmess' ? 'auto' : d.protocol === 'vless' ? 'none' : '';
  const isSSH = d.protocol === 'sshdns';
  const title = editing ? 'Modifier le serveur' : isSSH ? 'Serveur SSH SlowDNS' : 'Nouveau serveur';

  openSheet(title, (body, close) => {
    const dyn = h('div');

    const T = (label, key, o = {}) => field(label, h('input', {
      class: 'inp', type: o.type || 'text', value: d[key] == null ? '' : d[key], placeholder: o.ph || '',
      autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false', inputmode: o.mode,
      on: { input: (e) => { d[key] = o.num ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value; } },
    }), o.hint);
    const N = (label, key, o = {}) => T(label, key, Object.assign({ type: 'number', mode: 'numeric', num: true }, o));
    const SEL = (label, key, opts, rerender, hint) => {
      const s = h('select', { class: 'inp', on: { change: (e) => { d[key] = e.target.value; if (rerender) render(); } } },
        opts.map((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; return h('option', { value: v }, l); }));
      s.value = d[key] == null ? '' : d[key];
      return field(label, s, hint);
    };
    const CHK = (label, key, desc) => h('label', { class: 'check' },
      h('input', { type: 'checkbox', checked: !!d[key], on: { change: (e) => { d[key] = e.target.checked; } } }),
      h('span', {}, h('div', { class: 't' }, label), desc ? h('div', { class: 'd' }, desc) : null));
    const R2 = (a, b) => h('div', { class: 'row2' }, a, b);

    function render() {
      const p = d.protocol, parts = [];
      if (isSSH) {
        parts.push(
          T('Nom du serveur', 'name', { ph: 'Mon SSH SlowDNS' }),
          T('Name Server (NS)', 'ns_domain', { ph: 'ns.mondomaine.com', hint: 'Domaine NS du tunnel SlowDNS. Laisse vide pour un SSH direct (sans DNS).' }),
          T('DNS resolver', 'resolver', { ph: '8.8.8.8', hint: 'Résolveur DNS public utilisé pour le tunnel (IP, ou URL pour DoH).' }),
          SEL('Type de DNS', 'dns_type', [['udp', 'UDP (port 53)'], ['dot', 'DoT (TLS, port 853)'], ['doh', 'DoH (HTTPS)']]),
          R2(T('IP du serveur', 'address', { ph: '1.2.3.4', hint: 'Sert au SSH direct et au test de latence.' }), N('Port SSH', 'port')),
          R2(T('Utilisateur', 'user', { ph: 'root' }), T('Mot de passe', 'password', { type: 'password' })),
          T('Clé publique (dnstt)', 'pubkey', { ph: 'abcdef0123…', hint: 'Clé publique du serveur SlowDNS (hexadécimal).' }),
          T('Note (facultatif)', 'note'));
        dyn.replaceChildren(...parts);
        return;
      }
      parts.push(T('Nom du serveur', 'name', { ph: 'Mon serveur' }),
        R2(T('Adresse', 'address', { ph: 'exemple.com ou IP' }), N('Port', 'port')));
      if (p === 'vmess') parts.push(T('UUID', 'uuid', { ph: 'xxxxxxxx-xxxx-…' }),
        R2(N('Alter ID', 'alterId'), SEL('Chiffrement', 'encryption', ['auto', 'aes-128-gcm', 'chacha20-poly1305', 'none', 'zero'])));
      if (p === 'vless') parts.push(T('UUID', 'uuid', { ph: 'xxxxxxxx-xxxx-…' }),
        SEL('Flow', 'flow', [['', 'Aucun'], ['xtls-rprx-vision', 'xtls-rprx-vision']]));
      if (p === 'trojan') parts.push(T('Mot de passe', 'password', { type: 'password' }));
      if (p === 'ss') parts.push(SEL('Méthode de chiffrement', 'method', SS_METHODS), T('Mot de passe', 'password', { type: 'password' }));
      if (true) {
        parts.push(h('div', { class: 'sep' }, 'Transport'),
          R2(SEL('Réseau', 'network', NETWORKS, true), SEL('Sécurité', 'security', SECURITIES, true)));
        const net = d.network;
        if (net === 'tcp') parts.push(SEL('Type d\'en-tête', 'headerType', [['none', 'Aucun'], ['http', 'HTTP']], true));
        if (net === 'tcp' && d.headerType === 'http') parts.push(T('Host', 'host', { ph: 'cdn.exemple.com' }), T('Path', 'path', { ph: '/' }));
        if (['ws', 'h2', 'httpupgrade', 'xhttp'].includes(net)) parts.push(T('Host', 'host', { ph: 'cdn.exemple.com' }), T('Path', 'path', { ph: '/' }));
        if (net === 'grpc') parts.push(T('Nom du service (serviceName)', 'serviceName'), SEL('Mode gRPC', 'mode', [['', 'Gun (par défaut)'], ['multi', 'Multi']]));
        if (net === 'xhttp') parts.push(SEL('Mode XHTTP', 'mode', [['', 'Auto'], ['auto', 'auto'], ['packet-up', 'packet-up'], ['stream-up', 'stream-up'], ['stream-one', 'stream-one']]));
        if (net === 'kcp') parts.push(SEL('Type d\'en-tête', 'headerType', ['none', 'srtp', 'utp', 'wechat-video', 'dtls', 'wireguard']), T('Seed', 'path'));
        if (d.security === 'tls') parts.push(T('SNI', 'sni', { ph: 'exemple.com' }), T('ALPN', 'alpn', { ph: 'h2,http/1.1' }),
          SEL('Empreinte (fingerprint)', 'fingerprint', FPS), CHK('Autoriser les certificats invalides', 'allowInsecure', 'À éviter, sauf test.'));
        if (d.security === 'reality') parts.push(T('SNI', 'sni', { ph: 'www.microsoft.com' }), SEL('Empreinte (fingerprint)', 'fingerprint', FPS),
          T('Clé publique (pbk)', 'publicKey'), R2(T('Short ID (sid)', 'shortId'), T('Spider X', 'spiderX', { ph: '/' })));
      }
      parts.push(h('div', { class: 'sep' }, 'Proxy et payload (facultatif)'),
        T('Proxy (hôte:port)', 'proxy', { ph: 'ex : 192.168.1.10:8080  (vide = connexion directe)' }),
        T('SNI du proxy', 'proxySni', { ph: 'vide = proxy sans TLS' }),
        field('Payload (envoyé au proxy)', h('textarea', { class: 'inp', rows: 3, placeholder: '[method] [host_port] [protocol][crlf]Host: [host][crlf][crlf]', spellcheck: 'false', autocapitalize: 'off',
          on: { input: (e) => { d.payload = e.target.value; } } }, d.payload || ''),
          'Variables : [method] [host_port] [host] [port] [protocol] [crlf] [cr] [lf] [split] [ua] [netData]'));
      if (d.security !== 'tls') parts.push(CHK('Accepter un certificat non vérifié (proxy)', 'allowInsecure', 'Déconseillé.'));
      parts.push(T('Note affichée sous le serveur actif', 'note'));
      dyn.replaceChildren(...parts);
    }

    async function save() {
      if (!String(d.name || '').trim()) { toast('Donne un nom au serveur.', 'err'); return; }
      try {
        if (editing) await api('/servers/' + d.id, { method: 'PUT', body: { server: d } });
        else await api('/servers', { method: 'POST', body: { server: d } });
        toast(editing ? 'Serveur modifié.' : 'Serveur ajouté.');
        if (editing && S.status.state === 'connected' && S.status.server_id === d.id) toast('Reconnecte-toi pour appliquer les changements.', 'ok', 4500);
        close();
        refresh();
      } catch (e) { toast(e.message, 'err', 4500); }
    }

    if (!editing && !isSSH) {
      const ps = h('select', { class: 'inp', on: { change: (e) => {
        d.protocol = e.target.value;
        d.encryption = d.protocol === 'vmess' ? 'auto' : d.protocol === 'vless' ? 'none' : '';
        if (d.protocol === 'trojan' && d.security === 'none') d.security = 'tls';
        render();
      } } }, ['vless', 'vmess', 'trojan', 'ss'].map((p) => h('option', { value: p }, PROTO[p])));
      ps.value = d.protocol;
      body.append(field('Protocole', ps));
    } else {
      body.append(h('div', { style: 'margin:0 0 14px' }, h('span', { class: 'badge ' + d.protocol }, PROTO[d.protocol])));
    }
    render();
    body.append(dyn, h('button', { class: 'btn primary', on: { click: save } }, icon('check'), editing ? 'Enregistrer' : 'Ajouter le serveur'));
  });
}

/* --------------------------------------------------------------- paramètres */
function openSettings() {
  openSheet('Paramètres', (body, close) => {
    const go = (fn) => () => { close(); setTimeout(fn, 200); };
    const e = S.engine;
    const yes = (b, txt) => h('span', { class: b ? 'ok' : 'ko' }, b ? (txt || 'Installé') : 'Absent');
    body.append(
      menuItem('terminal', 'c1', 'Journal des logs', 'Voir ce que fait le moteur en temps réel', go(openLogs)),
      menuItem('share', 'c3', 'Partager l\'application', 'Envoie Fadelpsaume à un ami', go(shareApp)),
      h('div', { class: 'sep' }, 'État du moteur'),
      h('div', { class: 'kv' }, h('span', {}, 'Moteur Xray'), yes(e.xray, 'v' + (e.xray_version || '?'))),
      h('div', { class: 'kv' }, h('span', {}, 'Client SSH'), yes(e.ssh)),
      h('div', { class: 'kv' }, h('span', {}, 'SlowDNS (dnstt)'), yes(e.dnstt)),
      h('div', { class: 'kv' }, h('span', {}, 'Proxy SOCKS5'), h('span', { class: 'mono' }, '127.0.0.1:' + S.ports.socks)),
      h('div', { class: 'kv' }, h('span', {}, 'Proxy HTTP'), h('span', { class: 'mono' }, '127.0.0.1:' + S.ports.http)),
      h('div', { class: 'kv' }, h('span', {}, 'Version'), h('span', {}, 'Fadelpsaume ' + S.app)));
  });
}

function openLogs() {
  let since = 0, timer = null;
  openSheet('Journal des logs', (body) => {
    const box = h('div', { class: 'logbox' });
    async function poll() {
      try {
        const r = await api('/logs?since=' + since);
        if (r.n < since) { box.replaceChildren(); since = 0; return; }
        since = r.n;
        if (r.lines.length) {
          const bottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
          box.querySelectorAll('.none').forEach((x) => x.remove());
          for (const l of r.lines) {
            const m = l.match(/\[(INFO|WARN|ERROR)\]/);
            box.append(h('div', { class: 'l-' + (m ? m[1] : 'INFO') }, l));
          }
          if (bottom) box.scrollTop = box.scrollHeight;
        } else if (!box.children.length) {
          box.append(h('div', { class: 'none' }, 'Aucun événement pour le moment.'));
        }
      } catch (e) { /* ignoré */ }
    }
    poll().then(() => { box.scrollTop = box.scrollHeight; });
    timer = setInterval(poll, 1000);
    body.append(box, h('div', { class: 'logtools' },
      h('button', { class: 'btn ghost', on: { click: async () => {
        const txt = [...box.querySelectorAll('div:not(.none)')].map((x) => x.textContent).join('\n');
        toast(txt && await copyText(txt) ? 'Journal copié.' : 'Rien à copier.', txt ? 'ok' : 'err');
      } } }, icon('copy'), 'Copier'),
      h('button', { class: 'btn danger', on: { click: async () => { await api('/logs/clear', { method: 'POST' }); box.replaceChildren(); since = 0; toast('Journal effacé.'); } } }, icon('trash'), 'Effacer')));
  }, { onClose: () => clearInterval(timer) });
}

/* ------------------------------------------------------ partager l'appli */
const INSTALL_TEXT = 'Fadelpsaume — client VPN V2Ray (VMess, VLESS, Trojan, Shadowsocks, SSH SlowDNS)\n\n'
  + 'Installation dans Termux :\n'
  + 'tar -xzf Fadelpsaume.tar.gz\ncd fadelpsaume\nbash install.sh\nfadelpsaume';

async function shareApp() {
  if (AND) { AND.shareApp(); return; }
  let blob = null;
  try {
    const r = await fetch('/api/app-archive', { headers: { 'X-FDLP': '1' } });
    if (r.ok) blob = await r.blob();
  } catch (e) { /* pas d'archive */ }
  if (blob) {
    const file = new File([blob], 'Fadelpsaume.tar.gz', { type: 'application/gzip' });
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      try { await navigator.share({ files: [file], title: 'Fadelpsaume', text: INSTALL_TEXT }); return; }
      catch (e) { if (e.name === 'AbortError') return; }
    }
  }
  openSheet('Partager l\'application', (body) => {
    body.append(
      h('p', { style: 'margin:2px 2px 8px;color:var(--mut);line-height:1.5;font-size:14px' },
        blob ? 'Envoie l\'archive à ton ami, puis fais-lui suivre ces commandes dans Termux :'
          : 'Archive introuvable (relance install.sh pour la recréer). Instructions à transmettre :'),
      h('div', { class: 'codebox' }, INSTALL_TEXT.split('\n\n')[1]),
      blob ? h('button', { class: 'btn primary', on: { click: () => { const u = URL.createObjectURL(blob); const a = h('a', { href: u, download: 'Fadelpsaume.tar.gz' }); document.body.append(a); a.click(); setTimeout(() => { a.remove(); URL.revokeObjectURL(u); }, 1500); } } }, icon('download'), 'Télécharger l\'archive') : null,
      h('button', { class: 'btn ghost', on: { click: async () => toast(await copyText(INSTALL_TEXT) ? 'Instructions copiées.' : 'Copie impossible.', 'ok') } }, icon('copy'), 'Copier les instructions'),
      navigator.share ? h('button', { class: 'btn ghost', on: { click: () => navigator.share({ title: 'Fadelpsaume', text: INSTALL_TEXT }).catch(() => {}) } }, icon('share'), 'Partager le texte…') : null);
  });
}

/* --------------------------------------------------------------------- init */
function logo() {
  const t = document.createElement('template');
  t.innerHTML = '<svg viewBox="0 0 64 64" aria-hidden="true"><defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">'
    + '<stop offset="0" stop-color="#6fb7c9"/><stop offset="1" stop-color="#7fc8a0"/></linearGradient></defs>'
    + '<path d="M32 4l22 8v18c0 14-9.5 25.5-22 30C19.5 55.5 10 44 10 30V12z" fill="url(#lg)" fill-opacity=".16" stroke="url(#lg)" stroke-width="3" stroke-linejoin="round"/>'
    + '<path d="M24 44V20h17M24 31h12" fill="none" stroke="url(#lg)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  return t.content.firstChild;
}

document.querySelectorAll('[data-icon]').forEach((el) => el.replaceChildren(icon(el.dataset.icon)));
$('#logo').append(logo());
$('#speed').classList.add('sm');
$('#powerBtn').addEventListener('click', onPower);
$('#btnAdd').addEventListener('click', openAddMenu);
$('#btnSettings').addEventListener('click', () => (S ? openSettings() : toast('Chargement…')));
$('#btnPing').addEventListener('click', pingAll);

refresh().then(() => { if (S && S.servers.length) pingAll(); });
setInterval(refresh, 1000);
setInterval(tick, 500);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });

if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/sw.js').catch(function () { /* facultatif */ }); }

/* Bouton « retour » d'Android : ferme la feuille ouverte (retourne true si quelque chose a été fermé) */
window.fdlpBack = function () {
  if (openSheets.length) { openSheets[openSheets.length - 1].close(); return true; }
  return false;
};
