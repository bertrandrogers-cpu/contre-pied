"""Le tableau de bord : une page HTML autonome, régénérée à chaque passe."""
from __future__ import annotations

import datetime as dt
import json
import os

from .data import ROOT

OUT_FILE = os.path.join(ROOT, "out", "index.html")
PICK_KEYS = ("match", "match_id", "league", "ko", "time_tbc", "key", "label", "p", "fair", "min_odds", "odds",
             "odds_max", "edge", "stake_pct", "tags", "breaks", "lift")
MATCH_KEYS = ("id", "sport", "league", "ko", "home", "away", "ref", "xg", "shots", "sot", "games", "probs", "p_mkt",
              "scores", "tags", "info", "round", "surface", "best_of", "tennis", "elo", "rank", "form", "time_tbc")


def _default(o):
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    raise TypeError(type(o))


def _pick(s: dict) -> dict:
    return {k: s.get(k) for k in PICK_KEYS}


def write(rep: dict) -> str:
    payload = dict(
        {k: rep[k] for k in ("generated", "bankroll", "leagues", "chatte", "tracking", "history",
                             "backtest", "tag_status", "tag_info", "tennis_tags")},
        contre_pieds=[_pick(s) for s in rep["contre_pieds"]],
        solides=[_pick(s) for s in rep["solides"]],
        stats=[_pick(s) for s in rep["stats"]],
        combos=[dict(c, legs=[_pick(x) for x in c["legs"]]) for c in rep["combos"]],
        matches=[{k: m.get(k) for k in MATCH_KEYS} for m in rep["matches"]],
    )
    blob = json.dumps(payload, default=_default, ensure_ascii=False).replace("</", "<\\/")
    out_dir = os.path.dirname(OUT_FILE)
    os.makedirs(out_dir, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        fh.write(TEMPLATE.replace("/*__DATA__*/null", blob))
    _write_app_files(out_dir)
    return OUT_FILE


MANIFEST = {"name": "Contre-Pied", "short_name": "Contre-Pied", "start_url": ".", "display": "standalone",
            "background_color": "#0a0e0c", "theme_color": "#0a0e0c",
            "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                      {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"}]}


def _icon_png(size: int) -> bytes:
    """Icône de l'appli : un ballon vert citron barré d'une diagonale (le contre-pied), sur fond sombre."""
    import struct
    import zlib
    bg, lime = bytes((10, 14, 12)), bytes((198, 240, 77))
    c, r, half = size / 2, size * 0.34, size * 0.045
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            dx, dy = x + 0.5 - c, y + 0.5 - c
            ball = dx * dx + dy * dy <= r * r and abs(dx + dy) / 1.4142 > half
            raw += lime if ball else bg

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def _write_app_files(out_dir: str):
    """Ce qu'il faut pour « Ajouter à l'écran d'accueil » sur téléphone."""
    with open(os.path.join(out_dir, "manifest.webmanifest"), "w") as fh:
        json.dump(MANIFEST, fh, ensure_ascii=False)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        path = os.path.join(out_dir, name)
        if not os.path.exists(path):
            with open(path, "wb") as fh:
                fh.write(_icon_png(size))


TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contre-Pied</title>
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#0a0e0c">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Contre-Pied">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:ital,wght@0,700;0,800;1,800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#f3f5f1; --surface:#ffffff; --surface-2:#eef1ec; --line:#dde3dc; --text:#121a15; --muted:#5a6a60;
  --lime:#4d7c0f; --lime-bg:#eaf5d3; --gold:#9a5b00; --gold-bg:#fbf0d4; --sky:#0b6fae; --sky-bg:#e1effa;
  --rose:#be123c; --rose-bg:#fde4ea; --mint:#15803d; --mint-bg:#ddf3e5;
  --seg-n:#b9c3bc; --shadow:0 1px 2px rgba(16,24,20,.05),0 6px 20px rgba(16,24,20,.05);
  --display:"Barlow Condensed","Arial Narrow",system-ui,sans-serif;
  --body:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  color-scheme:light;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0a0e0c; --surface:#111813; --surface-2:#18211b; --line:#253029; --text:#e8f1ea; --muted:#8fa196;
    --lime:#c6f04d; --lime-bg:rgba(198,240,77,.10); --gold:#ffc94d; --gold-bg:rgba(255,201,77,.10);
    --sky:#6cc6ff; --sky-bg:rgba(108,198,255,.10); --rose:#ff6b8b; --rose-bg:rgba(255,107,139,.12);
    --mint:#4fe0a0; --mint-bg:rgba(79,224,160,.10); --seg-n:#3a463e; --shadow:none; color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --bg:#0a0e0c; --surface:#111813; --surface-2:#18211b; --line:#253029; --text:#e8f1ea; --muted:#8fa196;
  --lime:#c6f04d; --lime-bg:rgba(198,240,77,.10); --gold:#ffc94d; --gold-bg:rgba(255,201,77,.10);
  --sky:#6cc6ff; --sky-bg:rgba(108,198,255,.10); --rose:#ff6b8b; --rose-bg:rgba(255,107,139,.12);
  --mint:#4fe0a0; --mint-bg:rgba(79,224,160,.10); --seg-n:#3a463e; --shadow:none; color-scheme:dark;
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--text);font:15px/1.5 var(--body);-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px}
b,.num{font-variant-numeric:tabular-nums}
.muted{color:var(--muted)}
header.top{padding:28px 0 6px;display:flex;justify-content:space-between;gap:16px;align-items:flex-start}
.brand{font:800 46px/0.95 var(--display);text-transform:uppercase;letter-spacing:.5px;margin:0}
.brand em{color:var(--lime);font-style:italic}
.tagline{margin:8px 0 0;color:var(--muted)}
.theme{background:var(--surface);border:1px solid var(--line);color:var(--text);border-radius:999px;padding:6px 12px;font:inherit;font-size:13px;cursor:pointer}
.meta{font-size:13px;color:var(--muted);margin:10px 0 18px}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:18px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:12px 14px;box-shadow:var(--shadow)}
.kpi b{display:block;font:800 30px/1.05 var(--display)}
.kpi span{font-size:12.5px;color:var(--muted)}
nav.tabs{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);margin-bottom:18px}
nav.tabs .wrap{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none}
nav.tabs button{flex:none;background:none;border:0;border-bottom:3px solid transparent;color:var(--muted);font:600 14px var(--body);padding:12px 10px;cursor:pointer}
nav.tabs button[aria-selected="true"]{color:var(--text);border-bottom-color:var(--lime)}
section[hidden]{display:none}
h2{font:800 28px/1.1 var(--display);text-transform:uppercase;margin:6px 0 4px;letter-spacing:.3px}
h3{font:700 22px/1.15 var(--display);margin:0;letter-spacing:.2px}
.lead{color:var(--muted);margin:0 0 14px;max-width:760px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,330px),1fr));gap:14px;margin-bottom:30px}
.grid--2{grid-template-columns:repeat(auto-fill,minmax(min(100%,460px),1fr))}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:16px;box-shadow:var(--shadow);min-width:0}
.pick{border-left:4px solid var(--accent)}
.pick--cp{--accent:var(--lime);--accent-bg:var(--lime-bg)}
.pick--sol{--accent:var(--sky);--accent-bg:var(--sky-bg)}
.pick--stat{--accent:var(--gold);--accent-bg:var(--gold-bg)}
.pick__top{display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap}
.kicker{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px;font-weight:600}
.badge{font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;padding:3px 8px;border-radius:999px;background:var(--accent-bg,var(--surface-2));color:var(--accent,var(--muted))}
.pick__match{margin-top:8px;font-weight:600;color:var(--muted)}
.pick__sel{font:800 26px/1.1 var(--display);margin:2px 0 12px}
.nums{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}
.nums--3{grid-template-columns:repeat(3,minmax(0,1fr))}
.nums>div{background:var(--surface-2);border-radius:10px;padding:8px 8px 7px;min-width:0}
.nums b{display:block;font:700 19px/1.1 var(--display)}
.nums span{font-size:11.5px;color:var(--muted)}
.nums .hl{background:var(--accent-bg,var(--lime-bg))}
.nums .hl b{color:var(--accent,var(--lime))}
.pick__odds{font-size:13px;margin-top:10px}
.tags{list-style:none;margin:12px 0 0;padding:0;display:grid;gap:6px}
.tag details{background:var(--surface-2);border-radius:10px;padding:7px 10px}
.tag summary{cursor:pointer;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline;list-style:none}
.tag summary::-webkit-details-marker{display:none}
.tag__t{font-weight:600;font-size:14px}
.tag p{margin:6px 0 2px;font-size:13.5px;color:var(--muted)}
.st{font-size:11.5px;color:var(--muted)}
.st--ok{color:var(--mint)}
.st--ko{color:var(--rose)}
.tag--ko .tag__t{text-decoration:line-through;text-decoration-color:var(--rose);opacity:.75}
.combo--chatte{border-color:color-mix(in srgb,var(--gold) 45%,var(--line))}
.combo--enfer{border-color:color-mix(in srgb,var(--rose) 55%,var(--line))}
.combo--mille{border-color:color-mix(in srgb,var(--gold) 70%,var(--line))}
.combo__head{display:flex;justify-content:space-between;align-items:center;gap:8px}
.combo p{margin:6px 0 10px}
.legs{list-style:none;padding:0;margin:0 0 14px;display:grid;gap:6px;counter-reset:leg}
.legs li{display:flex;justify-content:space-between;gap:10px;align-items:center;background:var(--surface-2);border-radius:10px;padding:8px 10px}
.leg__sel{font-weight:600}
.leg__match{font-size:12.5px;color:var(--muted)}
.leg__odds{font:700 18px var(--display);white-space:nowrap}
.meter{height:10px;border-radius:999px;background:var(--surface-2);overflow:hidden;border:1px solid var(--line)}
.meter__fill{height:100%;background:linear-gradient(90deg,var(--mint),var(--gold),var(--rose));border-radius:999px}
.combo__chance{margin:8px 0 12px;font-size:14px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 14px}
.chip{border:1px solid var(--line);background:var(--surface);color:var(--text);border-radius:999px;padding:5px 12px;font:600 13px var(--body);cursor:pointer}
.chip[aria-pressed="true"]{background:var(--text);color:var(--bg);border-color:var(--text)}
.teams{display:grid;gap:2px;margin:8px 0 10px;font:700 21px/1.2 var(--display)}
.teams>div{display:flex;justify-content:space-between;gap:8px;align-items:center}
.teams small{font:500 12px var(--body);color:var(--muted);margin-left:6px}
.form{display:inline-flex;gap:2px}
.f{font:600 10.5px/16px var(--body);font-style:normal;width:16px;text-align:center;border-radius:4px;background:var(--surface-2);color:var(--muted)}
.f--V{background:var(--mint-bg);color:var(--mint)}
.f--D{background:var(--rose-bg);color:var(--rose)}
.bar{display:flex;height:26px;border-radius:8px;overflow:hidden;gap:2px}
.seg{display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;min-width:2px}
.seg--h{background:var(--sky)}
.seg--n{background:var(--seg-n);color:var(--text)}
.seg--a{background:var(--gold)}
:root[data-theme="dark"] .seg--h,:root[data-theme="dark"] .seg--a{color:#0a0e0c}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .seg--h,:root:not([data-theme="light"]) .seg--a{color:#0a0e0c}}
.sub{font-size:12.5px;color:var(--muted);margin:6px 0 8px}
.facts{display:flex;flex-wrap:wrap;gap:6px}
.facts span{font-size:12.5px;background:var(--surface-2);border-radius:8px;padding:3px 8px}
.board{list-style:none;padding:0;margin:10px 0 0;display:grid;gap:10px}
.board__row{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.board__team{font-weight:600}
.board__team small{color:var(--muted);font-weight:400;margin-left:6px}
.board__bar{height:6px;background:var(--surface-2);border-radius:999px;margin:4px 0 2px;overflow:hidden}
.board__bar i{display:block;height:100%;border-radius:999px}
.up{color:var(--gold)} i.up{background:var(--gold)}
.down{color:var(--sky)} i.down{background:var(--sky)}
.callout{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--lime);border-radius:16px;padding:18px;margin-bottom:18px}
.callout p{margin:8px 0 0;max-width:820px}
.kpis--bilan{margin:14px 0 4px}
.tbl{overflow-x:auto;margin-bottom:24px;border:1px solid var(--line);border-radius:14px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600}
tr:last-child td{border-bottom:0}
td.r,th.r{text-align:right}
.pill{font-size:11.5px;font-weight:700;padding:2px 8px;border-radius:999px;background:var(--surface-2);color:var(--muted)}
.pill--ok{background:var(--mint-bg);color:var(--mint)}
.pill--ko{background:var(--rose-bg);color:var(--rose)}
.empty{background:var(--surface);border:1px dashed var(--line);border-radius:16px;padding:22px;color:var(--muted);margin-bottom:28px}
footer{border-top:1px solid var(--line);margin-top:30px;padding:18px 0 40px;font-size:13px;color:var(--muted)}
footer code{background:var(--surface-2);padding:1px 6px;border-radius:6px}
@media (max-width:720px){
  .brand{font-size:36px}
  .kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  .nums{grid-template-columns:repeat(2,minmax(0,1fr))}
  .nums--3{grid-template-columns:repeat(3,minmax(0,1fr))}
  .pick__sel{font-size:23px}
}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div>
      <h1 class="brand">Contre-<em>Pied</em></h1>
      <p class="tagline">L'IA qui défie les stats. Foot et tennis, critères testés, facteur chatte inclus.</p>
    </div>
    <button class="theme" id="theme" type="button">Thème</button>
  </header>
  <div class="meta" id="meta"></div>
  <div class="kpis" id="kpis"></div>
</div>
<nav class="tabs"><div class="wrap" role="tablist" id="tabs"></div></nav>
<main class="wrap">
  <section id="t-jouer"></section>
  <section id="t-combos" hidden></section>
  <section id="t-stats" hidden></section>
  <section id="t-matchs" hidden></section>
  <section id="t-chatte" hidden></section>
  <section id="t-bilan" hidden></section>
</main>
<div class="wrap"><footer id="foot"></footer></div>
<script id="data" type="application/json">/*__DATA__*/null</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
// Un match commencé disparaît de partout : liste des matchs, pronos, stats, et combinés qui l'incluent.
function prune() {
  const upcoming = iso => new Date(iso).getTime() > Date.now();
  const before = D.matches.length + D.combos.length;
  D.matches = D.matches.filter(m => upcoming(m.ko));
  for (const k of ['contre_pieds', 'solides', 'stats']) D[k] = D[k].filter(s => upcoming(s.ko));
  D.combos = D.combos.filter(c => c.legs.every(l => upcoming(l.ko)));
  return D.matches.length + D.combos.length !== before;
}
prune();
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nf = (x, d) => x == null ? '—' : Number(x).toLocaleString('fr-FR', {minimumFractionDigits: d, maximumFractionDigits: d});
const fr2 = x => nf(x, 2), fr1 = x => nf(x, 1);
const pct = (p, d = 0) => p == null ? '—' : nf(p * 100, d) + ' %';
const sgn = (p, d = 1) => p == null ? '—' : (p >= 0 ? '+' : '−') + nf(Math.abs(p) * 100, d) + ' %';
const eur = x => nf(x, 2) + ' €';
const when = iso => new Date(iso).toLocaleString('fr-FR', {weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Paris'});
const byId = Object.fromEntries(D.matches.map(m => [m.id, m]));
// Heure d'un match, d'un prono ou d'une sélection ; « horaire à venir » tant que le programme n'est pas publié.
const whenOf = o => o.time_tbc
  ? new Date(o.ko).toLocaleDateString('fr-FR', {weekday: 'short', day: '2-digit', month: '2-digit', timeZone: 'Europe/Paris'}) + ' · horaire à venir'
  : when(o.ko);
const sportIcon = id => byId[id] && byId[id].sport === 'tennis' ? '🎾' : '⚽';
const TENNIS_TAGS = new Set(D.tennis_tags || []);

function tagItem(t) {
  const r = t.record;
  const st = t.status === 'ok' ? `<span class="st st--ok">✔ validé : ${pct(r.hit)} réussi pour ${pct(r.expected_hit)} prévu</span>`
    : t.status === 'ko' ? `<span class="st st--ko">✖ démenti par les stats : ${pct(r.hit)} pour ${pct(r.expected_hit)} prévu</span>`
    : `<span class="st">${r ? '≈ effet pas prouvé' : 'info'}</span>`;
  return `<li class="tag tag--${t.status}"><details><summary><span class="tag__t">${t.icon} ${esc(t.title)}</span>${st}</summary>
    <p>${esc(t.text)}${t.effect ? ` <em>(${esc(t.effect)})</em>` : ''}</p></details></li>`;
}

function pickCard(s, kind) {
  const m = byId[s.match_id];
  const tags = m ? m.tags.filter(t => s.tags.includes(t.id) && t.status !== 'ko') : [];
  const badge = {cp: 'Contre-pied', sol: 'Solide', stat: 'Stat à jouer'}[kind] + (s.breaks ? ' · casse la série' : '');
  const odds = s.odds
    ? `<div class="pick__odds">Cote moyenne relevée <b>${fr2(s.odds)}</b>${s.odds_max ? ` · meilleure <b>${fr2(s.odds_max)}</b>` : ''} · value <b>${sgn(s.edge)}</b></div>`
    : `<div class="pick__odds muted">Cote non relevée : vérifie chez ton bookmaker qu'elle est au moins à ${fr2(s.min_odds)}.</div>`;
  return `<article class="card pick pick--${kind}">
    <div class="pick__top"><span class="kicker">${sportIcon(s.match_id)} ${esc(s.league)} · ${whenOf(s)}</span><span class="badge">${badge}</span></div>
    <div class="pick__match">${esc(s.match)}</div>
    <div class="pick__sel">${esc(s.label)}</div>
    <div class="nums">
      <div><b>${pct(s.p)}</b><span>vraie proba</span></div>
      <div><b>${fr2(s.fair)}</b><span>cote juste</span></div>
      <div class="hl"><b>≥ ${fr2(s.min_odds)}</b><span>joue à partir de</span></div>
      <div><b>${eur(D.bankroll * s.stake_pct)}</b><span>mise conseillée</span></div>
    </div>
    ${odds}
    ${tags.length ? `<ul class="tags">${tags.map(tagItem).join('')}</ul>` : ''}
  </article>`;
}

function comboCard(c) {
  const w = Math.max(4, Math.min(100, Math.log10(Math.max(c.one_in, 1)) / Math.log10(1000) * 100));
  return `<article class="card combo combo--${c.kind}">
    <div class="combo__head"><h3>${({chatte: '🍀', enfer: '🔥', mille: '🎰'})[c.kind] || '🧱'} ${esc(c.name)}</h3><span class="badge">${c.legs.length} sélections</span></div>
    <p class="muted">${esc(c.blurb)}</p>
    <ol class="legs">${c.legs.map(l => `<li><div><div class="leg__sel">${esc(l.label)}</div>
      <div class="leg__match">${sportIcon(l.match_id)} ${esc(l.match)} · ${esc(l.league)} · ${whenOf(l)}</div></div>
      <div class="leg__odds">${l.odds ? fr2(l.odds) : '≥ ' + fr2(l.min_odds)}</div></li>`).join('')}</ol>
    <div class="meter" role="img" aria-label="Facteur chatte"><div class="meter__fill" style="width:${w}%"></div></div>
    <div class="combo__chance"><b>Facteur chatte : 1 chance sur ${Math.round(c.one_in)}</b>, ${esc(c.chance_text.toLowerCase())}</div>
    <div class="nums nums--3">
      <div><b>${c.kind === 'enfer' || c.kind === 'mille' ? '≈ ' : c.priced ? '' : '≥ '}${fr2(c.odds)}</b><span>${c.kind === 'enfer' || c.kind === 'mille' ? 'cote juste (ton site paiera moins)' : 'cote totale' + (c.priced ? '' : ' à viser')}</span></div>
      <div><b>${pct(c.p, 1)}</b><span>proba de passer</span></div>
      <div class="hl"><b>${eur(D.bankroll * c.stake_pct)}</b><span>mise conseillée</span></div>
    </div>
  </article>`;
}

function tennisCard(m) {
  const t = m.tennis, rank = r => r ? `n°${r}` : 'non classé';
  const form = f => f ? `<span class="form" title="5 derniers matchs">${f.split('').map(c => `<i class="f f--${c}">${c}</i>`).join('')}</span>` : '';
  const seg = (v, cls) => `<div class="seg seg--${cls}" style="width:${v * 100}%">${v >= 0.13 ? pct(v) : ''}</div>`;
  return `<article class="card match">
    <div class="pick__top"><span class="kicker">🎾 ${esc(m.league)} · ${esc(m.round)} · ${whenOf(m)}</span><span class="kicker">${esc(m.surface)}</span></div>
    <div class="teams">
      <div><span>${esc(m.home)}<small>${rank(m.rank[0])} · Elo ${m.elo[0]}</small></span>${form(m.form[0])}</div>
      <div><span>${esc(m.away)}<small>${rank(m.rank[1])} · Elo ${m.elo[1]}</small></span>${form(m.form[1])}</div>
    </div>
    <div class="bar">${seg(t.w1, 'h')}${seg(t.w2, 'a')}</div>
    <div class="sub">Nos probas de victoire : ${esc(m.home)} ${pct(t.w1)} · ${esc(m.away)} ${pct(t.w2)}</div>
    <div class="facts">
      <span>Au moins un set : ${pct(t.s1)} / ${pct(t.s2)}</span><span>Sans perdre de set : ${pct(t.st1)} / ${pct(t.st2)}</span><span>🎾 ≈ ${fr1(m.games)} jeux dans le match</span>
      <span>${m.best_of === 5 ? 'Au moins 4 sets' : 'Match en 3 sets'} : ${pct(t.dec)}</span>
    </div>
    ${m.tags.length ? `<ul class="tags">${m.tags.map(tagItem).join('')}</ul>` : ''}
  </article>`;
}

function matchCard(m) {
  if (m.sport === 'tennis') return tennisCard(m);
  const p = m.probs, mk = m.p_mkt, info = m.info || {};
  const seg = (v, cls, lab) => `<div class="seg seg--${cls}" style="width:${v * 100}%">${v >= 0.13 ? lab + ' ' + pct(v) : ''}</div>`;
  const form = s => info[s] ? `<span class="form" title="5 derniers matchs">${info[s].form.split('').map(c => `<i class="f f--${c}">${c}</i>`).join('')}</span>` : '';
  const w = info.weather ? `<span>🌡️ ${fr1(info.weather.temp)} °C · 💧 ${fr1(info.weather.rain)} mm/h · 💨 ${Math.round(info.weather.wind)} km/h</span>` : '';
  return `<article class="card match">
    <div class="pick__top"><span class="kicker">⚽ ${esc(m.league)} · ${when(m.ko)}</span>${m.ref ? `<span class="kicker">Arbitre : ${esc(m.ref)}</span>` : ''}</div>
    <div class="teams"><div><span>${esc(m.home)}</span>${form('h')}</div><div><span>${esc(m.away)}</span>${form('a')}</div></div>
    <div class="bar">${seg(p['1'], 'h', '1')}${seg(p['N'], 'n', 'N')}${seg(p['2'], 'a', '2')}</div>
    <div class="sub">Nos probas ${pct(p['1'])} / ${pct(p['N'])} / ${pct(p['2'])}${mk ? ` · marché ${pct(mk[0])} / ${pct(mk[1])} / ${pct(mk[2])}` : ''}</div>
    <div class="facts">
      <span>⚽ xG ${fr2(m.xg[0])} – ${fr2(m.xg[1])}</span><span>+2,5 buts ${pct(p.o25)}</span><span>Les 2 marquent ${pct(p.btts)}</span>
      ${m.shots ? `<span>🎯 ${fr1(m.shots)} tirs</span><span>🥅 ${fr1(m.sot)} tirs cadrés</span>` : ''}
      <span>Scores : ${m.scores.map(s => `${s[0]} (${pct(s[1])})`).join(', ')}</span>${w}
    </div>
    ${m.tags.length ? `<ul class="tags">${m.tags.map(tagItem).join('')}</ul>` : ''}
  </article>`;
}

const empty = txt => `<div class="empty">${txt}</div>`;
const grid = (items, fn, cls = '') => items.length ? `<div class="grid ${cls}">${items.map(fn).join('')}</div>` : '';

function renderJouer() {
  return `<h2>🎯 Les contre-pieds</h2>
    <p class="lead">Les paris qui vont contre ce que la série en cours fait croire. Chacun s'appuie sur un critère qui a visé plus juste que le modèle sur deux saisons.</p>
    ${grid(D.contre_pieds, s => pickCard(s, 'cp')) || empty("Aucun contre-pied validé sur les prochains jours. Ça arrive : mieux vaut rien que n'importe quoi.")}
    <h2>🔒 Les Solides</h2>
    <p class="lead">L'objectif des 80 %. Ils passent souvent, mais à petite cote : ne les joue que si ta cote est au moins à « joue à partir de ».</p>
    ${grid(D.solides, s => pickCard(s, 'sol')) || empty('Aucun Solide pour le moment.')}`;
}

function renderCombos() {
  return `<h2>🍀 Les combinés</h2>
    <p class="lead">Plus il y a de sélections, plus la marge du bookmaker se multiplie. Le facteur chatte te dit franchement combien de chances tu as : mise en conséquence.</p>
    ${grid(D.combos, comboCard, 'grid--2') || empty('Pas assez de sélections fiables pour bâtir un combiné.')}`;
}

function renderStats() {
  return `<h2>📊 Stats à jouer</h2>
    <p class="lead">Tirs et tirs cadrés en foot, nombre de jeux en tennis : des marchés que les bookmakers soignent moins. Le modèle donne la cote juste. Si ton site paie plus que « joue à partir de », c'est là que se cache la value.</p>
    ${grid(D.stats, s => pickCard(s, 'stat')) || empty('Aucune ligne intéressante pour le moment.')}`;
}

let leagueFilter = 'Tous';
function renderMatchs() {
  const sportOf = m => m.sport === 'tennis' ? '🎾 Tennis' : '⚽ Foot';
  const leagues = ['Tous', '⚽ Foot', '🎾 Tennis', ...new Set(D.matches.map(m => m.league))];
  const list = D.matches.filter(m => leagueFilter === 'Tous' || m.league === leagueFilter || sportOf(m) === leagueFilter);
  return `<h2>📅 Tous les matchs</h2>
    <p class="lead">Nos probas, les buts attendus ou les sets, et tous les critères qui se déclenchent, avec leur bilan réel.</p>
    <div class="chips">${leagues.map(l => `<button class="chip" aria-pressed="${l === leagueFilter}" data-league="${esc(l)}">${esc(l)}</button>`).join('')}</div>
    ${grid(list, matchCard, 'grid--2') || empty('Aucun match dans les prochains jours.')}`;
}

function boardCol(rows, title, sub, cls) {
  const max = Math.max(1, ...rows.map(r => Math.abs(r.luck)));
  return `<div class="card"><h3>${title}</h3><p class="muted">${sub}</p><ol class="board">${rows.map(r => `<li>
    <div class="board__row"><span class="board__team">${esc(r.team)}<small>${esc(r.league)}</small></span><b class="${cls}">${r.luck > 0 ? '+' : '−'}${fr1(Math.abs(r.luck))} pts</b></div>
    <div class="board__bar"><i class="${cls}" style="width:${Math.abs(r.luck) / max * 100}%"></i></div>
    <small class="muted">${r.pts} pts pris pour ${fr1(r.xpts)} mérités sur ${r.n} matchs</small></li>`).join('')}</ol></div>`;
}

function renderChatte() {
  return `<h2>🍀 L'indice de chatte</h2>
    <p class="lead">Points pris moins points « mérités » d'après les occasions (xG) sur les 6 derniers matchs. Les veinards finissent par redescendre, les chats noirs par remonter. Le marché, lui, regarde surtout les résultats.</p>
    <div class="grid grid--2">
      ${boardCol(D.chatte.lucky, '🍀 Bénis des dieux', 'Plus de points que leur jeu ne vaut : méfiance.', 'up')}
      ${boardCol(D.chatte.unlucky, '🐈‍⬛ Chats noirs', 'Moins de points que leur jeu ne vaut : ça va tourner.', 'down')}
    </div>`;
}

const KIND = {contre_pied: 'Contre-pieds', solide: 'Solides', stat: 'Stats à jouer', combo: 'Combinés'};
function renderBilan() {
  const b = D.backtest;
  let html = '<h2>🧪 Le bilan</h2>';
  if (!b) return html + empty('Lance <code>python3 prono.py backtest</code> pour mesurer le modèle.');
  const c = b.categories, vb = b.value_bets['0.35'] || {};
  const tile = (v, lab) => `<div class="kpi"><b>${v}</b><span>${lab}</span></div>`;
  html += `<div class="callout"><h3>Ce que valent vraiment ces pronos</h3>
    <p class="muted">Critères validés sur ${esc(b.calibration_season)}, puis pronos rejoués semaine par semaine sur ${esc(b.season)} (${b.matches} matchs) sans jamais voir le futur.</p>
    <div class="kpis kpis--bilan">
      ${tile(pct(c.solides?.hit, 1), `Solides réussis (${pct(c.solides?.expected_hit, 1)} prévu, ${c.solides?.n} pronos)`)}
      ${tile(pct(c.contre_pieds_casse_series?.hit, 1), `Contre-pieds casse-série (${pct(c.contre_pieds_casse_series?.expected_hit, 1)} prévu), rentabilité ${sgn(c.contre_pieds_casse_series?.roi)}`)}
      ${tile(pct(c.stats?.hit, 1), `Stats à jouer réussies (${pct(c.stats?.expected_hit, 1)} prévu)`)}
      ${tile(sgn(vb.roi), `Value bets classiques 1N2/±2,5 (${vb.bets} paris) : battus par le marché, donc pas proposés`)}
    </div>
    <p><b>La vérité :</b> le modèle voit juste aussi souvent qu'il l'annonce, et ses 80 % sont tenus. Mais les bookmakers voient juste aussi, et ils se gardent une marge. Le gain se joue donc sur la cote : ne joue un prono que si ton site paie au moins « joue à partir de ». Comparer les sites rapporte plus que n'importe quel critère.</p>
  </div>`;
  const n = b.naive00;
  if (n && n.n) html += `<div class="callout" style="border-left-color:var(--gold)"><h3>🪤 Ton exemple : « 2 équipes qui ne marquent plus = 0-0 »</h3>
    <p>Sur ${n.n} matchs de ${esc(b.season)} entre deux équipes en panne, le 0-0 est tombé <b>${pct(n.nil_nil / n.n, 1)}</b> du temps (le modèle prévoyait ${pct(n.p00 / n.n, 1)}) et le nul ${pct(n.draws / n.n, 0)}.
    La série a donc un petit fond de vérité, mais un 0-0 reste une chance sur ${Math.round(n.n / Math.max(n.nil_nil, 1))} : à une cote autour de 9, c'est le juste prix, pas une affaire.
    Le « piège à 0-0 » (deux équipes en panne qui se créent pourtant des occasions) a vu +1,5 buts dans ${pct(n.piege_o15 / Math.max(n.piege_n, 1))} des cas.</p></div>`;
  const tb = b.tennis;
  if (tb) {
    const tc = tb.categories || {}, rel = tb.reliability || {};
    html += `<div class="callout" style="border-left-color:var(--sky)"><h3>🎾 Tennis : ce que valent les pronos</h3>
      <p class="muted">Modèle (Elo par surface + classement) calé sur ${esc(tb.calibration_season)}, puis pronos joués sur ${esc(tb.season)} (${tb.matches} matchs) sans rien retoucher.</p>
      <div class="kpis kpis--bilan">
        ${tile(pct(tc.solides?.hit, 1), `Solides réussis (${pct(tc.solides?.expected_hit, 1)} prévu, ${tc.solides?.n} pronos)`)}
        ${tile(pct(tc.contre_pieds?.hit, 1), `Contre-pieds réussis (${pct(tc.contre_pieds?.expected_hit, 1)} prévu, ${tc.contre_pieds?.n} pronos)`)}
        ${tile(pct(rel.w_fav?.hit, 1), `Favoris vainqueurs (${pct(rel.w_fav?.expected_hit, 1)} annoncé) : le modèle dit vrai`)}
        ${tile(sgn(tb.value_bets?.roi), 'Parier le vainqueur à la cote moyenne : le marché tennis est très affûté')}
      </div>
      <p>Les probabilités tennis sont fiables, mais les bookmakers le savent aussi. Pas de cotes tennis en direct pour l'instant : la cote « joue à partir de » est ton seul garde-fou, ne joue jamais en dessous.</p></div>`;
  }
  const cb = [...Object.entries(b.combos || {}).map(([k, v]) => ['⚽ ' + k, v, b.season]),
    ...Object.entries(tb?.combos || {}).map(([k, v]) => ['🎾 ' + k, v, tb.season])];
  if (cb.length) html += `<h3 style="margin:8px 0 10px">Combinés rejoués</h3><div class="tbl"><table><thead><tr><th>Combiné</th><th>Saison</th><th class="r">Joués</th><th class="r">Passés</th><th class="r">Prévu</th><th class="r">Chance moyenne</th></tr></thead><tbody>
    ${cb.map(([k, v, s]) => `<tr><td>${esc(k)}</td><td>${esc(s)}</td><td class="r">${v.n}</td><td class="r">${v.won}</td><td class="r">${fr1(v.expected_won)}</td><td class="r">1 sur ${Math.round(v.avg_one_in)}</td></tr>`).join('')}</tbody></table></div>`;
  const tags = Object.entries(D.tag_status || {}).sort((a, b2) => b2[1].lift - a[1].lift);
  html += `<h3 style="margin:8px 0 4px">Les critères à l'épreuve (2 saisons)</h3>
    <p class="lead">« Apport » : ce que le critère voit en plus du modèle. Seuls les critères validés (au moins ${80} cas et +1,5 pt d'apport) déclenchent des contre-pieds.</p>
    <div class="tbl"><table><thead><tr><th>Critère</th><th class="r">Cas</th><th class="r">Réussite</th><th class="r">Prévu</th><th class="r">Apport</th><th>Statut</th></tr></thead><tbody>
    ${tags.map(([id, s]) => { const i = (D.tag_info[id] || ['•', id]).slice(); i[0] = (TENNIS_TAGS.has(id) ? '🎾 ' : '⚽ ') + i[0];
      const pill = s.status === 'ok' ? '<span class="pill pill--ok">validé</span>' : s.status === 'ko' ? '<span class="pill pill--ko">démenti</span>' : '<span class="pill">pas prouvé</span>';
      return `<tr><td>${i[0]} ${esc(i[1])}</td><td class="r">${s.n}</td><td class="r">${pct(s.hit, 1)}</td><td class="r">${pct(s.expected_hit, 1)}</td><td class="r">${(s.lift >= 0 ? '+' : '−') + nf(Math.abs(s.lift) * 100, 1)} pt</td><td>${pill}</td></tr>`; }).join('')}
    </tbody></table></div>`;
  const tr = Object.entries(D.tracking || {});
  html += `<h3 style="margin:8px 0 10px">Suivi en direct de tes pronos</h3>`;
  html += tr.length ? `<div class="tbl"><table><thead><tr><th>Catégorie</th><th class="r">Réglés</th><th class="r">Réussite</th><th class="r">Prévu</th><th class="r">Rentabilité*</th></tr></thead><tbody>
    ${tr.map(([k, v]) => `<tr><td>${KIND[k] || k}</td><td class="r">${v.n}</td><td class="r">${pct(v.hit, 1)}</td><td class="r">${pct(v.expected_hit, 1)}</td><td class="r">${sgn(v.roi)}</td></tr>`).join('')}</tbody></table></div>
    <p class="muted" style="font-size:12.5px;margin-top:-14px">* à la cote relevée, ou à la cote « joue à partir de » quand on ne la connaît pas.</p>`
    : empty("Les premiers pronos se régleront après les matchs de ce week-end.");
  const hist = (D.history || []).slice().reverse().slice(0, 30);
  if (hist.length) html += `<div class="tbl"><table><thead><tr><th></th><th>Prono</th><th>Match</th><th class="r">Proba</th><th class="r">Cote</th></tr></thead><tbody>
    ${hist.map(h => `<tr><td>${h.result === 'won' ? '✅' : h.result === 'lost' ? '❌' : '⏳'}</td><td>${esc(h.kind === 'combo' ? h.name : h.label)}</td><td class="muted">${esc(h.kind === 'combo' ? h.legs.length + ' sélections' : h.match)}</td><td class="r">${pct(h.p, h.kind === 'combo' ? 1 : 0)}</td><td class="r">${fr2(h.odds || h.min_odds)}</td></tr>`).join('')}</tbody></table></div>`;
  return html;
}

const TABS = [['jouer', 'À jouer', renderJouer], ['combos', 'Combinés', renderCombos], ['stats', 'Stats à jouer', renderStats],
  ['matchs', 'Matchs', renderMatchs], ['chatte', 'Indice de chatte', renderChatte], ['bilan', 'Bilan', renderBilan]];

let currentTab = 'jouer';
function show(id) {
  currentTab = id;
  TABS.forEach(([k, , fn]) => {
    const sec = document.getElementById('t-' + k);
    sec.hidden = k !== id;
    if (k === id) sec.innerHTML = fn();
    document.querySelector(`[data-tab="${k}"]`).setAttribute('aria-selected', String(k === id));
  });
  try { localStorage.setItem('cp-tab', id); } catch (e) {}
}

document.getElementById('tabs').innerHTML = TABS.map(([k, label]) => `<button role="tab" data-tab="${k}" aria-selected="false">${label}</button>`).join('');
document.getElementById('tabs').addEventListener('click', e => { const b = e.target.closest('[data-tab]'); if (b) show(b.dataset.tab); });
document.getElementById('t-matchs').addEventListener('click', e => {
  const b = e.target.closest('[data-league]'); if (b && b.tagName === 'BUTTON') { leagueFilter = b.dataset.league; show('matchs'); }
});

function header() {
  const next = D.matches[0];
  document.getElementById('meta').textContent = `Mis à jour ${when(D.generated)} · ${D.matches.length} matchs à venir (${D.leagues.length} championnats, coupes d'Europe, tennis) · bankroll ${eur(D.bankroll)}`;
  document.getElementById('kpis').innerHTML = [
    [D.contre_pieds.length, 'contre-pieds validés'], [D.solides.length, 'Solides (objectif 80 %)'],
    [D.combos.length, 'combinés dont la chatte'], [next ? when(next.ko) : '—', next ? `prochain : ${next.home} – ${next.away}` : 'aucun match à venir'],
  ].map(([v, l]) => `<div class="kpi"><b>${esc(v)}</b><span>${esc(l)}</span></div>`).join('');
}
header();
// La page reste ouverte ? Toutes les minutes, on retire ce qui vient de commencer.
setInterval(() => { if (prune()) { header(); show(currentTab); } }, 60000);
document.getElementById('foot').innerHTML = `Notifications : appli gratuite <b>ntfy</b>, sur ton canal privé. Sur téléphone, « Ajouter à l'écran d'accueil » transforme cette page en appli.<br>
  Données : football-data.co.uk (résultats, xG, cotes), Open-Meteo (météo), tennis-data.co.uk et ESPN (tennis). Aucun prono n'est une certitude. Mise uniquement ce que tu peux perdre. Joueurs Info Service : 09 74 75 13 13.`;

const root = document.documentElement;
document.getElementById('theme').addEventListener('click', () => {
  const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = dark ? 'light' : 'dark';
  try { localStorage.setItem('cp-theme', root.dataset.theme); } catch (e) {}
});
try { const t = localStorage.getItem('cp-theme'); if (t) root.dataset.theme = t; } catch (e) {}
let first = 'jouer';
try { first = localStorage.getItem('cp-tab') || 'jouer'; } catch (e) {}
show(TABS.some(t => t[0] === first) ? first : 'jouer');
</script>
</body>
</html>
"""
