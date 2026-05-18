"""
AnimU Addon - Stremio Addon per anime sub/dub ITA
Cerca su Nyaa, AnimeToSho, TokyoTosho, AniDex, NekoBT, SeaDex
Supporta Real-Debrid e TorBox
Configurazione via browser su /configure — nessun .env da editare
"""

import asyncio
import logging
import os
from typing import Optional

from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from dotenv import load_dotenv

from scrapers.nyaa import NyaaScraper
from scrapers.animetosho import AnimeToshoScraper
from scrapers.tokyotosho import TokyoToshoScraper
from scrapers.anidex import AniDexScraper
from scrapers.nekobt import NekoBTScraper
from scrapers.seadex import SeaDexScraper
from debrid.realdebrid import RealDebridClient
from debrid.torbox import TorBoxClient
from utils.metadata import MetadataResolver
from utils.formatter import StreamFormatter
from utils.cache import SimpleCache
from utils.config_store import load as cfg_load, save as cfg_save, is_configured

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="AnimU Addon")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Manifest ────────────────────────────────────────────────────────────────

MANIFEST = {
    "id": "it.animu.stremio.addon",
    "version": "1.0.0",
    "name": "AnimU ITA",
    "description": "Cerca anime sub/dub ITA su Nyaa, AnimeToSho, TokyoTosho, AniDex, NekoBT, SeaDex. Supporta Real-Debrid e TorBox.",
    "logo": "https://i.imgur.com/YxoZHZm.png",
    "resources": ["stream"],
    "types": ["series", "movie"],
    "catalogs": [],
    "idPrefixes": ["kitsu", "tt", "tmdb"],
    "behaviorHints": {
        "configurable": True,
        "configurationRequired": False,
    },
}

# ─── Globals ─────────────────────────────────────────────────────────────────

_cache    = SimpleCache(ttl=300)
_metadata = MetadataResolver()
_formatter = StreamFormatter()

SCRAPER_MAP = {
    "nyaa":       NyaaScraper(),
    "animetosho": AnimeToshoScraper(),
    "tokyotosho": TokyoToshoScraper(),
    "anidex":     AniDexScraper(),
    "nekobt":     NekoBTScraper(),
    "seadex":     SeaDexScraper(),
}

QUALITY_RANK = {"144":0,"360":1,"480":2,"720":3,"1080":4,"2160":5,"4K":5}

def _qrank(q: str) -> int:
    return QUALITY_RANK.get(q.replace("p",""), 3)

def _debrid_clients(cfg: dict):
    clients = []
    if cfg.get("rd"):
        clients.append(RealDebridClient(cfg["rd"]))
    if cfg.get("tb"):
        clients.append(TorBoxClient(cfg["tb"]))
    return clients

# ─── Pagina /configure ────────────────────────────────────────────────────────

CONFIGURE_HTML = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AnimU ITA — Configurazione</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f0f17;--surface:#1a1a2e;--surface2:#16213e;
  --accent:#e94560;--text:#eee;--muted:#888;--border:#2a2a3e;
  --sub:#1a3a5c;--sub-t:#4db8ff;--dub:#1a3a1a;--dub-t:#4dff88;
}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:2rem 1rem}
.wrap{max-width:520px;margin:0 auto}
.hero{text-align:center;margin-bottom:2rem}
.hero .logo{font-size:3rem;margin-bottom:.4rem}
.hero h1{font-size:1.6rem;font-weight:600;margin-bottom:.3rem}
.hero p{color:var(--muted);font-size:.9rem;line-height:1.6}
.section{margin-bottom:1.5rem}
.slabel{font-size:.7rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;margin-bottom:.6rem;padding-left:2px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.25rem}
.field{margin-bottom:1rem}.field:last-child{margin-bottom:0}
.field label{display:block;font-size:.85rem;color:var(--muted);margin-bottom:.4rem}
.hint{font-size:.75rem;color:#555;margin-top:.35rem}
.kw{position:relative}
.kw input{padding-right:40px;font-family:monospace;font-size:.85rem}
.kw .eye{position:absolute;right:10px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:var(--muted);font-size:1.1rem;padding:4px}
input[type=text],input[type=password]{width:100%;padding:10px 12px;background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:8px;font-size:.9rem;outline:none;transition:border-color .2s}
input:focus{border-color:var(--accent)}
.tg{display:flex;gap:8px;flex-wrap:wrap}
.t{flex:1;min-width:90px;padding:10px 8px;border:1px solid var(--border);border-radius:8px;background:var(--surface2);color:var(--muted);cursor:pointer;font-size:.85rem;text-align:center;font-family:inherit;transition:all .15s}
.t:hover:not(.on){border-color:#444;color:var(--text)}
.t.on{border-color:var(--accent);background:#2a0f1e;color:var(--text)}
.qg{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}
.qb{padding:8px 4px;border:1px solid var(--border);border-radius:8px;background:var(--surface2);color:var(--muted);cursor:pointer;font-size:.8rem;text-align:center;font-family:inherit;transition:all .15s}
.qb:hover:not(.on){border-color:#444;color:var(--text)}
.qb.on{border-color:#4dff88;background:#0a200a;color:#4dff88}
.sg{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.sb{padding:10px 6px;border:1px solid var(--border);border-radius:8px;background:var(--surface2);color:var(--muted);cursor:pointer;font-size:.82rem;text-align:center;font-family:inherit;transition:all .15s}
.sb:hover:not(.on){border-color:#444;color:var(--text)}
.sb.on{border-color:var(--accent);background:#2a0f1e;color:var(--text)}
.divider{height:1px;background:var(--border);margin:1.5rem 0}
.pbox{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:1rem;font-family:monospace;font-size:.82rem;line-height:1.9;white-space:pre-wrap;word-break:break-all;color:#ccc}
.plabel{font-size:.75rem;color:var(--muted);margin-bottom:.4rem}
.brow{display:flex;gap:6px;flex-wrap:wrap;margin-top:.75rem}
.badge{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:99px;font-size:.75rem}
.bsub{background:var(--sub);color:var(--sub-t)}
.bdub{background:var(--dub);color:var(--dub-t)}
.bq{background:var(--surface2);color:var(--muted);border:1px solid var(--border)}
.save-btn{width:100%;padding:14px;background:linear-gradient(135deg,var(--accent),#c0392b);border:none;color:#fff;border-radius:10px;font-size:1rem;font-weight:600;cursor:pointer;font-family:inherit;transition:opacity .15s;margin-top:.5rem}
.save-btn:hover{opacity:.88}
.save-btn:disabled{opacity:.4;cursor:not-allowed}
.install-row{display:flex;gap:8px;margin-top:.75rem}
.copy-btn,.stremio-btn{flex:1;padding:10px;border-radius:8px;cursor:pointer;font-size:.88rem;font-family:inherit;transition:all .15s}
.copy-btn{background:var(--surface2);border:1px solid var(--border);color:var(--text)}
.stremio-btn{background:var(--accent);border:none;color:#fff;font-weight:600}
.stremio-btn:hover{opacity:.88}
.status{font-size:.82rem;margin-top:.75rem;padding:.6rem .9rem;border-radius:8px;display:none}
.ok{background:#0a200a;color:#4dff88;border:1px solid #1a4a1a;display:block}
.err{background:#200a0a;color:#ff6666;border:1px solid #4a1a1a;display:block}
.url-box{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:.85rem 1rem;font-family:monospace;font-size:.78rem;color:var(--muted);word-break:break-all;display:none;margin-top:1rem;line-height:1.5}
.configured-banner{background:#0a200a;border:1px solid #1a4a1a;border-radius:10px;padding:1rem 1.25rem;margin-bottom:1.5rem;font-size:.88rem;color:#4dff88;display:none}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div class="logo">🎌</div>
    <h1>AnimU ITA</h1>
    <p>Stremio addon per anime sub/dub italiano<br>Configurazione salvata sul server — nessun file da modificare</p>
  </div>

  <div class="configured-banner" id="banner">
    ✅ Addon già configurato e attivo. Puoi modificare le impostazioni qui sotto e salvare di nuovo.
  </div>

  <div class="section">
    <div class="slabel">Servizi debrid</div>
    <div class="card">
      <div class="field">
        <label>⚡ Real-Debrid API key</label>
        <div class="kw">
          <input type="password" id="rd" placeholder="Incolla la tua API key...">
          <button class="eye" onclick="toggleVis('rd',this)">👁</button>
        </div>
        <div class="hint">real-debrid.com/apitoken</div>
      </div>
      <div class="field">
        <label>📦 TorBox API key</label>
        <div class="kw">
          <input type="password" id="tb" placeholder="Incolla la tua API key...">
          <button class="eye" onclick="toggleVis('tb',this)">👁</button>
        </div>
        <div class="hint">torbox.app/settings</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="slabel">Lingua / audio</div>
    <div class="card">
      <div class="tg">
        <button class="t on" data-v="both" onclick="setT(this,'audio')">📝🎙️ Sub + Dub</button>
        <button class="t" data-v="sub" onclick="setT(this,'audio')">📝 Solo SUB ITA</button>
        <button class="t" data-v="dub" onclick="setT(this,'audio')">🎙️ Solo DUB ITA</button>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="slabel">Qualità minima</div>
    <div class="card">
      <div class="qg">
        <button class="qb" data-v="144" onclick="setQ(this)">144p</button>
        <button class="qb" data-v="360" onclick="setQ(this)">360p</button>
        <button class="qb" data-v="480" onclick="setQ(this)">480p</button>
        <button class="qb on" data-v="720" onclick="setQ(this)">720p ✓</button>
        <button class="qb" data-v="1080" onclick="setQ(this)">1080p</button>
        <button class="qb" data-v="2160" onclick="setQ(this)">4K</button>
      </div>
      <div class="hint" style="margin-top:.6rem">Release sotto questa soglia non appaiono</div>
    </div>
  </div>

  <div class="section">
    <div class="slabel">Fonti di ricerca</div>
    <div class="card">
      <div class="sg">
        <button class="sb on" data-v="nyaa" onclick="toggleSrc(this)">🐱 Nyaa</button>
        <button class="sb on" data-v="animetosho" onclick="toggleSrc(this)">🗃️ AnimeTosho</button>
        <button class="sb on" data-v="tokyotosho" onclick="toggleSrc(this)">🗼 TokyoTosho</button>
        <button class="sb on" data-v="anidex" onclick="toggleSrc(this)">📚 AniDex</button>
        <button class="sb on" data-v="nekobt" onclick="toggleSrc(this)">🐾 NekoBT</button>
        <button class="sb on" data-v="seadex" onclick="toggleSrc(this)">🌊 SeaDex</button>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="slabel">Ordine stream</div>
    <div class="card">
      <div class="tg">
        <button class="t on" data-v="quality" onclick="setT(this,'sort')">⬆️ Qualità</button>
        <button class="t" data-v="seeds" onclick="setT(this,'sort')">👥 Seeders</button>
        <button class="t" data-v="size" onclick="setT(this,'sort')">📦 Dimensione</button>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="slabel">Anteprima stream</div>
    <div class="card">
      <div class="plabel">Nome (colonna sinistra Stremio):</div>
      <div class="pbox" id="pname"></div>
      <div class="plabel" style="margin-top:.75rem">Descrizione (colonna destra):</div>
      <div class="pbox" id="pdesc"></div>
      <div class="brow" id="badges"></div>
    </div>
  </div>

  <div class="divider"></div>

  <div class="section">
    <div class="slabel">Salva e installa</div>
    <div class="card">
      <div id="msg" class="status"></div>
      <button class="save-btn" onclick="save()">💾 Salva configurazione</button>
      <div class="url-box" id="urlbox"></div>
      <div class="install-row" id="installrow" style="display:none">
        <button class="copy-btn" onclick="copyUrl()">📋 Copia URL</button>
        <button class="stremio-btn" onclick="openStremio()">📺 Apri in Stremio</button>
      </div>
      <p class="hint" style="margin-top:.75rem">Le API key vengono salvate sul server in modo sicuro.</p>
    </div>
  </div>
</div>

<script>
var S={audio:'both',minQ:720,sort:'quality',sources:['nyaa','animetosho','tokyotosho','anidex','nekobt','seadex']};
var addonUrl='';

// Carica config esistente dal server
fetch('/configure/load').then(r=>r.json()).then(function(cfg){
  if(cfg.configured){
    document.getElementById('banner').style.display='block';
  }
  if(cfg.rd){document.getElementById('rd').value=cfg.rd}
  if(cfg.tb){document.getElementById('tb').value=cfg.tb}
  if(cfg.audio){
    S.audio=cfg.audio;
    document.querySelectorAll('[data-v]').forEach(function(b){
      if(b.dataset.v===cfg.audio&&b.closest('.tg')&&!b.closest('.sg'))b.classList.add('on');
      else if(b.dataset.v!==cfg.audio&&b.closest('.tg')&&!b.closest('.sg'))b.classList.remove('on');
    });
  }
  if(cfg.minQ){
    S.minQ=cfg.minQ;
    document.querySelectorAll('.qb').forEach(function(b){
      b.classList.remove('on');
      b.textContent=b.dataset.v==='2160'?'4K':b.dataset.v+'p';
      if(parseInt(b.dataset.v)===cfg.minQ){
        b.classList.add('on');
        b.textContent=(b.dataset.v==='2160'?'4K':b.dataset.v+'p')+' ✓';
      }
    });
  }
  if(cfg.sources){
    S.sources=cfg.sources;
    document.querySelectorAll('.sb').forEach(function(b){
      if(cfg.sources.includes(b.dataset.v))b.classList.add('on');
      else b.classList.remove('on');
    });
  }
  if(cfg.sort){
    S.sort=cfg.sort;
    document.querySelectorAll('.t').forEach(function(b){
      if(b.closest('.tg')&&!b.closest('.sg')){
        // gestito sopra per audio
      }
    });
  }
  render();
}).catch(function(){render()});

function toggleVis(id,btn){
  var i=document.getElementById(id);
  i.type=i.type==='text'?'password':'text';
  btn.textContent=i.type==='text'?'🙈':'👁';
}
function setT(btn,grp){
  btn.closest('.tg').querySelectorAll('.t').forEach(function(b){b.classList.remove('on')});
  btn.classList.add('on');
  if(grp==='audio')S.audio=btn.dataset.v;
  if(grp==='sort')S.sort=btn.dataset.v;
  render();
}
function setQ(btn){
  document.querySelectorAll('.qb').forEach(function(b){
    b.classList.remove('on');
    b.textContent=b.dataset.v==='2160'?'4K':b.dataset.v+'p';
  });
  btn.classList.add('on');
  btn.textContent=(btn.dataset.v==='2160'?'4K':btn.dataset.v+'p')+' ✓';
  S.minQ=parseInt(btn.dataset.v);
  render();
}
function toggleSrc(btn){
  var active=document.querySelectorAll('.sb.on');
  if(btn.classList.contains('on')&&active.length<=1)return;
  btn.classList.toggle('on');
  S.sources=Array.from(document.querySelectorAll('.sb.on')).map(function(b){return b.dataset.v});
  render();
}
function render(){
  var q=S.minQ>=1080?'FHD🚀1080p':'HD💿720p';
  var db='[Debrid⚡️☁️]';
  var ai=S.audio==='dub'?'🎙️ DUB ITA':'📝 SUB ITA';
  document.getElementById('pname').textContent=q+'\n\n\n'+db+'\n\n[AnimU ITA]\n\n'+ai;
  var aud=S.audio==='dub'?'🗣️ 🇮🇹 🎤 DUB':'🗣️ 🇮🇹\n📝 🇮🇹 SUB';
  document.getElementById('pdesc').textContent='💎 1080p\n'+aud+'\n📦 1.4 GB | 🏷️ SubsPlease | ↑234\n🌐 🐱 Nyaa\n📄 ▶️ʙʟᴇᴀᴄʜ ꜱ𝟢𝟣ᴇ𝟣𝟤 ʜᴇᴠᴄ ɪᴛᴀ 𝟣𝟢𝟪𝟢ᴘ◀️';
  var qmap={144:'144p',360:'360p',480:'480p',720:'720p',1080:'1080p',2160:'4K'};
  document.getElementById('badges').innerHTML=
    (S.audio!=='dub'?'<span class="badge bsub">📝 SUB ITA</span>':'')+
    (S.audio!=='sub'?'<span class="badge bdub">🎙️ DUB ITA</span>':'')+
    '<span class="badge bq">min '+qmap[S.minQ]+'</span>'+
    '<span class="badge bq">'+S.sources.length+' fonti</span>';
}

function save(){
  var rd=document.getElementById('rd').value.trim();
  var tb=document.getElementById('tb').value.trim();
  var msg=document.getElementById('msg');
  if(!rd&&!tb){
    msg.className='status err';
    msg.textContent='⚠️ Inserisci almeno una API key (Real-Debrid o TorBox).';
    return;
  }
  var payload={rd:rd,tb:tb,audio:S.audio,minQ:S.minQ,sort:S.sort,sources:S.sources};
  fetch('/configure/save',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)
  }).then(function(r){return r.json()}).then(function(data){
    if(data.ok){
      addonUrl=data.manifest_url;
      msg.className='status ok';
      msg.textContent='✅ Configurazione salvata! Ora installa l\'addon in Stremio.';
      document.getElementById('urlbox').textContent=addonUrl;
      document.getElementById('urlbox').style.display='block';
      document.getElementById('installrow').style.display='flex';
      document.getElementById('banner').style.display='block';
    }else{
      msg.className='status err';
      msg.textContent='❌ Errore nel salvataggio: '+(data.error||'sconosciuto');
    }
  }).catch(function(e){
    msg.className='status err';
    msg.textContent='❌ Errore di rete: '+e;
  });
}

function copyUrl(){
  if(!addonUrl)return;
  navigator.clipboard.writeText(addonUrl).then(function(){
    var b=document.querySelector('.copy-btn');
    b.textContent='✅ Copiato!';
    setTimeout(function(){b.textContent='📋 Copia URL'},2000);
  });
}
function openStremio(){
  if(!addonUrl)return;
  window.location.href='stremio://'+addonUrl.replace('https://','').replace('http://','');
}
render();
</script>
</body>
</html>"""

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return RedirectResponse("/configure")

@app.get("/manifest.json")
async def manifest():
    return JSONResponse(MANIFEST)

@app.get("/configure")
async def configure():
    return HTMLResponse(CONFIGURE_HTML)

@app.get("/configure/load")
async def configure_load():
    """Restituisce la config corrente (con chiavi mascherate per sicurezza)"""
    cfg = cfg_load()
    return JSONResponse({
        "configured": is_configured(),
        "rd":  cfg.get("rd", ""),
        "tb":  cfg.get("tb", ""),
        "audio":   cfg.get("audio", "both"),
        "minQ":    cfg.get("minQ", 720),
        "sort":    cfg.get("sort", "quality"),
        "sources": cfg.get("sources", list(SCRAPER_MAP.keys())),
    })

@app.post("/configure/save")
async def configure_save(request: Request):
    """Salva la configurazione sul server"""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "JSON non valido"}, status_code=400)

    if not data.get("rd") and not data.get("tb"):
        return JSONResponse({"ok": False, "error": "Almeno una API key è necessaria"}, status_code=400)

    ok = cfg_save(data)
    if not ok:
        return JSONResponse({"ok": False, "error": "Errore di scrittura sul server"}, status_code=500)

    # Costruisce l'URL del manifest
    base_url = str(request.base_url).rstrip("/")
    manifest_url = f"{base_url}/manifest.json"

    return JSONResponse({
        "ok": True,
        "manifest_url": manifest_url,
    })

@app.get("/manifest.json")
async def manifest_final():
    return JSONResponse(MANIFEST)

@app.get("/{config}/manifest.json")
async def manifest_configured(config: str):
    return JSONResponse(MANIFEST)

# ─── Quality helpers ──────────────────────────────────────────────────────────

@app.get("/{config}/stream/{type}/{id}.json")
async def stream_configured(config: str, type: str, id: str, request: Request):
    """Stream con config nell'URL (legacy, per compatibilità)"""
    import base64, json as _json
    try:
        cfg = _json.loads(base64.b64decode(config + "==").decode())
    except Exception:
        cfg = cfg_load()
    return await _handle_stream(cfg, type, id, request)

@app.get("/stream/{type}/{id}.json")
async def stream(type: str, id: str, request: Request):
    """Stream con config salvata sul server"""
    cfg = cfg_load()
    return await _handle_stream(cfg, type, id, request)

async def _handle_stream(cfg: dict, type: str, id: str, request: Request):
    rd_key  = cfg.get("rd")  or os.getenv("RD_API_KEY", "")
    tb_key  = cfg.get("tb")  or os.getenv("TB_API_KEY", "")
    audio   = cfg.get("audio", "both")
    min_q   = int(cfg.get("minQ", 0))
    sort_by = cfg.get("sort", "quality")
    sources = cfg.get("sources") or list(SCRAPER_MAP.keys())

    log.info(f"Stream → type={type} id={id} audio={audio} minQ={min_q}")

    cache_key = f"{type}:{id}:{audio}:{min_q}:{sort_by}:{','.join(sorted(sources))}"
    cached = _cache.get(cache_key)
    if cached:
        return JSONResponse({"streams": cached})

    # 1. Metadata
    try:
        meta = await _metadata.resolve(type, id)
    except Exception as e:
        log.error(f"Metadata error: {e}")
        meta = {"title_en": "", "title_it": "", "season": 1, "episode": 1}

    season     = meta.get("season", 1)
    episode    = meta.get("episode", 1)
    title_en   = meta.get("title_en", "")
    title_it   = meta.get("title_it", "")
    title_jp   = meta.get("title_jp", "")
    titles_all = meta.get("titles_all") or [t for t in [title_en, title_jp, title_it] if t]
    mal_id     = meta.get("mal_id")

    log.info(f"Titoli: {titles_all} | MAL ID: {mal_id}")

    # 2. Scraping
    active = [SCRAPER_MAP[s] for s in sources if s in SCRAPER_MAP]
    results = await asyncio.gather(
        *[sc.search(
            title_en=title_en, title_it=title_it,
            season=season, episode=episode,
            titles_all=titles_all, mal_id=mal_id, title_jp=title_jp,
          ) for sc in active],
        return_exceptions=True
    )

    torrents = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            log.warning(f"Scraper {active[i].name} error: {res}")
        else:
            torrents.extend(res)

    log.info(f"Trovati {len(torrents)} torrent")

    # 3. Filtri audio
    # Per "sub" o "dub" mostriamo anche "unknown" (verifica sub ITA fatta da debrid)
    if audio == "dub":
        torrents = [t for t in torrents if t.audio_type == "dub"]
    elif audio == "sub":
        # Includi sub espliciti e unknown (potrebbero avere sub ITA non dichiarati nel titolo)
        torrents = [t for t in torrents if t.audio_type in ("sub", "unknown")]
    # "both" = tutti

    if min_q > 0:
        torrents = [t for t in torrents if _qrank(t.quality) >= _qrank(str(min_q))]

    if not torrents:
        return JSONResponse({"streams": []})

    # 4. Ordina
    if sort_by == "seeds":
        torrents.sort(key=lambda t: t.seeders, reverse=True)
    elif sort_by == "size":
        torrents.sort(key=lambda t: t.size_bytes, reverse=True)
    else:
        torrents.sort(key=lambda t: _qrank(t.quality), reverse=True)

    # 5. Debrid
    clients = _debrid_clients(cfg)
    if not clients:
        streams = _formatter.format_magnet_streams(torrents)
        return JSONResponse({"streams": streams})

    stream_results = []
    for client in clients:
        try:
            resolved = await client.resolve_torrents(torrents)
            stream_results.extend(resolved)
        except Exception as e:
            log.error(f"Debrid {client.name} error: {e}")

    streams = _formatter.format_streams(stream_results, torrents)
    _cache.set(cache_key, streams)
    return JSONResponse({"streams": streams})


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 7000))
    uvicorn.run("main:app", host=host, port=port, reload=False)
