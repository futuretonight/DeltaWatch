"""
╔══════════════════════════════════════════════════════════════════════╗
║                 DeltaWatch (Exam Monitor)                            ║
║         JEE Main  +  TG EAPCET  │  GM_xhr POST  │  CSP bypassed      ║
╚══════════════════════════════════════════════════════════════════════╝

Why HTTP instead of WebSocket:
  The JEE website sends a strict CSP response header:
    connect-src 'self' *.s3waas.gov.in *.google-analytics.com
  This blocks ALL ws:// connections at the browser level — even from
  Tampermonkey's sandbox. However GM_xmlhttpRequest is fully exempt
  from CSP (confirmed: server returned 426 in diagnostics).
  So we use GM_xhr POST instead — same push architecture, zero scraping.

Install:
    pip install aiohttp colorama plyer

Run:
    python deltawatch.py
    python deltawatch.py --port 8765
    python deltawatch.py --reset
    python deltawatch.py --no-notify
    python deltawatch.py --host 0.0.0.0   # listen on all interfaces

Endpoints:
    POST http://localhost:8765/snapshot  — browser pushes DOM snapshot
    GET  http://localhost:8765/ping      — health check
    GET  http://localhost:8765/status    — current cache summary
    POST http://localhost:8765/reset     — wipe cache at runtime (query: ?site=jee)

"""

import asyncio
import json
import hashlib
import argparse
import logging
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

__version__ = "6.0.0"

# ── Dependency guard ──────────────────────────────────────────────────────────
# Only aiohttp is truly required.  colorama and plyer degrade gracefully.

_HARD_MISSING: list[str] = []

try:
    from aiohttp import web
except ImportError:
    _HARD_MISSING.append("aiohttp")

if _HARD_MISSING:
    print(f"[ERROR] Required package(s) missing: {', '.join(_HARD_MISSING)}")
    print(f"        Run:  pip install {' '.join(_HARD_MISSING)}")
    sys.exit(1)

try:
    from colorama import Fore, Style, init as _cinit
    _cinit(autoreset=True)
    _COLORAMA_OK = True
except ImportError:
    _COLORAMA_OK = False
    class _Noop:                                # noqa: E302
        def __getattr__(self, _: str) -> str:
            return ""
    Fore = Style = _Noop()                      # type: ignore[assignment]

try:
    from plyer import notification as _plyer    # type: ignore[import]
    _PLYER_OK = True
except ImportError:
    _PLYER_OK = False

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
_log = logging.getLogger("exam_monitor")

# ── Terminal colour shortcuts ─────────────────────────────────────────────────
C = Fore.CYAN    + Style.BRIGHT
G = Fore.GREEN   + Style.BRIGHT
Y = Fore.YELLOW  + Style.BRIGHT
R = Fore.RED     + Style.BRIGHT
M = Fore.MAGENTA + Style.BRIGHT
D = Style.DIM
Z = Style.RESET_ALL

# ── Paths ─────────────────────────────────────────────────────────────────────
CACHE_FILE = Path("exam_cache.json")
LOG_FILE   = Path("exam_changes.log")

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_BODY_BYTES  = 2 * 1024 * 1024   # 2 MB — cap inbound payloads
MAX_CACHE_ITEMS = 500               # per list, prevents unbounded growth
KNOWN_SITES     = frozenset({"jee", "eapcet"})

SITE_LABELS: dict[str, str] = {
    "jee":    "JEE Main  (jeemain.nta.nic.in)",
    "eapcet": "TG EAPCET (eapcet.tgche.ac.in / eapcet.tsche.ac.in)",
}

# ── Global state ──────────────────────────────────────────────────────────────
_cache: dict              = {}
_notify_enabled: bool     = True
_request_count: int       = 0
_connected_sites: set     = set()
_start_time: float        = time.monotonic()
_cache_lock: asyncio.Lock            # initialised in main()
_ticker_task: asyncio.Task | None = None


# ─────────────────────────────────────────────────────────────────────────────
#  Cache helpers
# ─────────────────────────────────────────────────────────────────────────────

def _empty_site() -> dict:
    return {
        "page_hash":          None,
        "last_updated_date":  None,
        "public_notices":     [],
        "candidate_activity": [],
        "latest_news_jee":    [],
        "latest_updates":     [],
        "full_text_blocks":   [],
        "known_links":        [],
    }


def _ensure_hashes(items: list) -> list:
    """Back-fill 'hash' field on items loaded from an older cache file."""
    out = []
    for item in items:
        item = dict(item)
        if "hash" not in item:
            item["hash"] = item_hash(item.get("text", ""), item.get("href", ""))
        out.append(item)
    return out


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Back-fill hashes on old data so find_new / merge don't KeyError
            for site_key in KNOWN_SITES:
                site_data = data.get(site_key)
                if isinstance(site_data, dict):
                    for list_key in (
                        "public_notices", "candidate_activity", "latest_news_jee",
                        "latest_updates", "full_text_blocks", "known_links",
                    ):
                        if isinstance(site_data.get(list_key), list):
                            site_data[list_key] = _ensure_hashes(site_data[list_key])
            _log.info("Cache loaded from %s", CACHE_FILE)
            return data
        except Exception as exc:
            _log.warning("Cache file corrupt, starting fresh: %s", exc)

    return {
        "jee":    _empty_site(),
        "eapcet": _empty_site(),
        "meta": {
            "created":      datetime.now().isoformat(),
            "last_save":    None,
            "total_alerts": 0,
        },
    }


def _save_cache_sync(cache: dict) -> None:
    """Blocking write — always call via asyncio.to_thread()."""
    cache["meta"]["last_save"] = datetime.now().isoformat()
    tmp = CACHE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2, ensure_ascii=False)
    tmp.replace(CACHE_FILE)   # atomic on POSIX; near-atomic on Windows


async def save_cache(cache: dict) -> None:
    """Non-blocking cache save (runs in a thread pool)."""
    try:
        await asyncio.to_thread(_save_cache_sync, cache)
    except Exception as exc:
        _log.error("Failed to save cache: %s", exc)


def _log_change_sync(site: str, section: str, items: list) -> None:
    """Blocking file append — always call via asyncio.to_thread()."""
    ts = datetime.now().isoformat()
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"\n[{ts}]  {site.upper()}  —  {section}\n")
        for item in items:
            fh.write(f"  + {item.get('text', '')}\n")
            if item.get("href"):
                fh.write(f"    {item['href']}\n")
        fh.write("─" * 60 + "\n")


async def log_change(site: str, section: str, items: list) -> None:
    try:
        await asyncio.to_thread(_log_change_sync, site, section, items)
    except Exception as exc:
        _log.error("Failed to write log: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
#  Item helpers
# ─────────────────────────────────────────────────────────────────────────────

def item_hash(text: str, href: str = "") -> str:
    return hashlib.sha1(
        f"{text.strip()}||{href.strip()}".encode()
    ).hexdigest()[:14]


def enrich(items: object) -> list:
    """Normalise, validate, and stamp incoming items."""
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item["hash"]    = item_hash(item.get("text", ""), item.get("href", ""))
        item["seen_at"] = datetime.now().isoformat()
        out.append(item)
    return out


def find_new(cached: list, live: list) -> list:
    """Return items in *live* whose hash is not in *cached*."""
    try:
        known = {i["hash"] for i in cached}
    except (KeyError, TypeError):
        known = set()
    return [i for i in live if i.get("hash") not in known]


def merge(cached: list, live: list, cap: int = MAX_CACHE_ITEMS) -> list:
    """Prepend genuinely new live items to cache; respect cap."""
    try:
        known = {i["hash"] for i in cached}
    except (KeyError, TypeError):
        known = set()
    combined = [i for i in live if i.get("hash") not in known] + cached
    return combined[:cap]


# ─────────────────────────────────────────────────────────────────────────────
#  Notifications + sound
# ─────────────────────────────────────────────────────────────────────────────

def notify(title: str, body: str) -> None:
    if not _notify_enabled or not _PLYER_OK:
        return
    try:
        _plyer.notify(title=title, message=body[:256],
                      app_name="Exam Monitor", timeout=8)
    except Exception as exc:
        _log.debug("Notification failed: %s", exc)


def beep() -> None:
    try:
        if platform.system() == "Windows":
            import winsound                      # noqa: PLC0415
            winsound.Beep(1000, 250)
            winsound.Beep(1300, 180)
        else:
            sys.stdout.write("\a\a")
            sys.stdout.flush()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  Terminal output
# ─────────────────────────────────────────────────────────────────────────────

_ERASE_LINE = "\033[2K"   # ANSI: erase entire current line

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def alert_box(site: str, section: str, items: list) -> None:
    label = SITE_LABELS.get(site, site.upper())
    # Erase any status-ticker remnant before drawing the box
    print(f"\r{_ERASE_LINE}")
    print(f"{R}{'━'*70}")
    print(f"  🔔  [{_ts()}]  {label}")
    print(f"       Section : {section}")
    print(f"{'━'*70}{Z}")
    for item in items:
        print(f"  {M}  ➕  {item.get('text', '')}{Z}")
        if item.get("href"):
            print(f"       {D}↳  {item['href']}{Z}")
    print()


def info(msg: str) -> None:
    print(f"\r{_ERASE_LINE}  {D}[{_ts()}]{Z}  {msg}")


def print_status() -> None:
    sites  = ", ".join(sorted(_connected_sites)) if _connected_sites else "none"
    alerts = _cache.get("meta", {}).get("total_alerts", 0)
    uptime = int(time.monotonic() - _start_time)
    h, rem = divmod(uptime, 3600)
    m, s   = divmod(rem, 60)
    up_str = f"{h:02d}:{m:02d}:{s:02d}"
    alert_col = R if alerts else G
    print(
        f"\r{_ERASE_LINE}  {D}[{_ts()}]  "
        f"up {up_str}  │  active: {G}{sites}{Z}"
        f"  {D}│  requests: {_request_count}"
        f"  │  alerts: {Z}{alert_col}{alerts}{Z}",
        end="", flush=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Diff engine
# ─────────────────────────────────────────────────────────────────────────────

async def diff_snapshot(site: str, snap: dict) -> bool:
    """
    Compare *snap* against the cached state for *site*.
    Returns True if any alert was fired.
    Must be called while holding _cache_lock.
    """
    sc      = _cache.setdefault(site, _empty_site())
    changed = False

    # ── Whole-page text blocks (catch-all) ────────────────────────────────────
    live_blocks = enrich(snap.get("fullTextBlocks", []))
    new_blocks  = find_new(sc.get("full_text_blocks", []), live_blocks)
    if new_blocks:
        meaningful = [b for b in new_blocks
                      if len(b.get("text", "").strip()) > 20]
        if meaningful:
            alert_box(site, "⚠  New page content detected", meaningful)
            await log_change(site, "Whole-page content", meaningful)
            notify(
                f"{'JEE Main' if site == 'jee' else 'TG EAPCET'} — Page updated",
                "\n".join(i["text"][:80] for i in meaningful[:3]),
            )
            beep()
            changed = True
    # Always merge so known items accumulate correctly
    sc["full_text_blocks"] = merge(sc.get("full_text_blocks", []), live_blocks)

    # ── New links ─────────────────────────────────────────────────────────────
    live_links = enrich(snap.get("allLinks", []))
    new_links  = find_new(sc.get("known_links", []), live_links)
    if new_links:
        real = [lnk for lnk in new_links
                if lnk.get("href", "").startswith("http")
                and len(lnk.get("text", "")) > 5]
        if real:
            alert_box(site, "🔗  New link(s) on page", real)
            await log_change(site, "New links", real)
            notify(
                f"{'JEE Main' if site == 'jee' else 'TG EAPCET'} — New link",
                "\n".join(i["text"][:80] for i in real[:3]),
            )
            beep()
            changed = True
    sc["known_links"] = merge(sc.get("known_links", []), live_links)

    # ── Update stored page hash ───────────────────────────────────────────────
    live_hash = snap.get("pageHash")
    if live_hash and live_hash != sc.get("page_hash"):
        sc["page_hash"] = live_hash

    # ── JEE-specific ──────────────────────────────────────────────────────────
    if site == "jee":
        live_date = snap.get("lastUpdated")
        if live_date and live_date != sc.get("last_updated_date"):
            old = sc.get("last_updated_date") or "—"
            print(f"\r{_ERASE_LINE}")
            print(f"{R}{'━'*70}")
            print(f"  🗓  [{_ts()}]  JEE Main — SITE DATE CHANGED")
            print(f"{'━'*70}{Z}")
            print(f"  Was : {D}{old}{Z}")
            print(f"  Now : {G}{live_date}{Z}\n")
            await log_change(site, "Last Updated Date",
                             [{"text": f"{old} → {live_date}", "href": ""}])
            notify("JEE — Site date changed", f"{old} → {live_date}")
            beep()
            changed = True
            sc["last_updated_date"] = live_date

        for snap_key, label, cache_key in (
            ("publicNotices",     "📋  Public Notices",     "public_notices"),
            ("candidateActivity", "🎓  Candidate Activity", "candidate_activity"),
            ("latestNews",        "📰  Latest News Ticker", "latest_news_jee"),
        ):
            live  = enrich(snap.get(snap_key, []))
            new   = find_new(sc.get(cache_key, []), live)
            if new:
                alert_box(site, label, new)
                await log_change(site, label.strip(), new)
                notify(f"JEE — {label.strip()}",
                       "\n".join(i["text"][:80] for i in new[:3]))
                beep()
                changed = True
            sc[cache_key] = merge(sc.get(cache_key, []), live)

    # ── EAPCET-specific ───────────────────────────────────────────────────────
    elif site == "eapcet":
        live = enrich(snap.get("latestUpdates", []))
        new  = find_new(sc.get("latest_updates", []), live)
        if new:
            alert_box(site, "📋  Latest Updates", new)
            await log_change(site, "Latest Updates", new)
            notify("TG EAPCET — New Update",
                   "\n".join(i["text"][:80] for i in new[:3]))
            beep()
            changed = True
        sc["latest_updates"] = merge(sc.get("latest_updates", []), live)

    return changed


# ─────────────────────────────────────────────────────────────────────────────
#  CORS header factory
# ─────────────────────────────────────────────────────────────────────────────

def _cors(extra: dict | None = None) -> dict:
    h = {
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _json_resp(data: dict, status: int = 200) -> web.Response:
    return web.Response(
        status=status,
        headers=_cors(),
        text=json.dumps(data, ensure_ascii=False),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Middleware: body-size limiter
# ─────────────────────────────────────────────────────────────────────────────

@web.middleware
async def body_size_limit(request: web.Request, handler):
    if request.content_length and request.content_length > MAX_BODY_BYTES:
        return _json_resp(
            {"status": "error", "reason": "payload_too_large"},
            status=413,
        )
    return await handler(request)


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP route handlers
# ─────────────────────────────────────────────────────────────────────────────

async def handle_options(request: web.Request) -> web.Response:
    """Handle CORS pre-flight for any route."""
    return web.Response(status=204, headers=_cors())


async def handle_snapshot(request: web.Request) -> web.Response:
    global _request_count

    # ── Parse body ────────────────────────────────────────────────────────────
    try:
        body = await request.json()
    except Exception:
        return _json_resp({"status": "error", "reason": "invalid_json"}, status=400)

    if not isinstance(body, dict):
        return _json_resp({"status": "error", "reason": "body_must_be_object"}, status=400)

    site = body.get("site", "")
    kind = body.get("kind", "snapshot")

    async with _cache_lock:
        _request_count += 1

        # ── Ping (keepalive) ──────────────────────────────────────────────────
        if kind == "ping":
            _connected_sites.add(SITE_LABELS.get(site, site))
            print_status()
            return _json_resp({"status": "pong", "site": site})

        # ── Hello (first connect) ─────────────────────────────────────────────
        if kind == "hello":
            if site not in KNOWN_SITES:
                return _json_resp(
                    {"status": "error", "reason": f"unknown site '{site}'"},
                    status=400,
                )
            _connected_sites.add(SITE_LABELS.get(site, site))
            sc = _cache.get(site, _empty_site())
            info(f"{G}Browser connected  →  {SITE_LABELS.get(site, site)}{Z}")
            return _json_resp({
                "status":       "welcome",
                "site":         site,
                "is_first_run": sc.get("page_hash") is None,
                "cache_counts": {
                    "public_notices":     len(sc.get("public_notices",     [])),
                    "candidate_activity": len(sc.get("candidate_activity", [])),
                    "latest_updates":     len(sc.get("latest_updates",     [])),
                    "full_text_blocks":   len(sc.get("full_text_blocks",   [])),
                    "known_links":        len(sc.get("known_links",        [])),
                    "latest_news_jee":    len(sc.get("latest_news_jee",    [])),
                },
            })

        # ── Snapshot ──────────────────────────────────────────────────────────
        if site not in KNOWN_SITES:
            return _json_resp(
                {"status": "error", "reason": f"unknown site '{site}'"},
                status=400,
            )

        snap = body.get("data")
        if not isinstance(snap, dict):
            return _json_resp(
                {"status": "error", "reason": "missing or invalid 'data' field"},
                status=400,
            )

        sc = _cache.setdefault(site, _empty_site())

        # ── First-ever snapshot: seed the baseline ────────────────────────────
        if sc.get("page_hash") is None:
            info(f"{Y}[{site.upper()}] Seeding baseline …{Z}")
            sc["page_hash"]          = snap.get("pageHash")
            sc["public_notices"]     = enrich(snap.get("publicNotices",     []))
            sc["candidate_activity"] = enrich(snap.get("candidateActivity", []))
            sc["latest_updates"]     = enrich(snap.get("latestUpdates",     []))
            sc["full_text_blocks"]   = enrich(snap.get("fullTextBlocks",    []))
            sc["known_links"]        = enrich(snap.get("allLinks",          []))
            sc["latest_news_jee"]    = enrich(snap.get("latestNews",        []))
            sc["last_updated_date"]  = snap.get("lastUpdated")
            _connected_sites.add(SITE_LABELS.get(site, site))
            await save_cache(_cache)
            print_status()
            return _json_resp({
                "status":  "baseline_saved",
                "counts": {
                    k: len(v) if isinstance(v, list) else v
                    for k, v in sc.items()
                },
            })

        # ── Diff against baseline ─────────────────────────────────────────────
        changed = await diff_snapshot(site, snap)
        if changed:
            _cache["meta"]["total_alerts"] = (
                _cache["meta"].get("total_alerts", 0) + 1
            )
        _connected_sites.add(SITE_LABELS.get(site, site))
        await save_cache(_cache)
        print_status()

        return _json_resp({
            "status":       "diffed",
            "changed":      changed,
            "total_alerts": _cache["meta"]["total_alerts"],
        })


async def handle_ping(request: web.Request) -> web.Response:
    uptime = int(time.monotonic() - _start_time)
    return _json_resp({
        "status":       "ok",
        "version":      __version__,
        "uptime_s":     uptime,
        "total_alerts": _cache.get("meta", {}).get("total_alerts", 0),
        "sites_seen":   sorted(_connected_sites),
        "requests":     _request_count,
    })


async def handle_status(request: web.Request) -> web.Response:
    summary: dict = {}
    for site_key in KNOWN_SITES:
        sc = _cache.get(site_key, _empty_site())
        summary[site_key] = {
            k: len(v) if isinstance(v, list) else v
            for k, v in sc.items()
        }
    return _json_resp({
        "cache":    summary,
        "meta":     _cache.get("meta", {}),
        "uptime_s": int(time.monotonic() - _start_time),
        "version":  __version__,
    })


async def handle_reset(request: web.Request) -> web.Response:
    """
    POST /reset           — wipe entire cache
    POST /reset?site=jee  — wipe only the jee cache entry
    """
    async with _cache_lock:
        site_param = request.rel_url.query.get("site")
        if site_param:
            if site_param not in KNOWN_SITES:
                return _json_resp(
                    {"status": "error", "reason": f"unknown site '{site_param}'"},
                    status=400,
                )
            _cache[site_param] = _empty_site()
            await save_cache(_cache)
            info(f"{Y}Cache reset for site: {site_param}{Z}")
            return _json_resp({"status": "reset", "site": site_param})
        else:
            for sk in list(KNOWN_SITES):
                _cache[sk] = _empty_site()
            _cache["meta"]["total_alerts"] = 0
            await save_cache(_cache)
            _connected_sites.clear()
            info(f"{Y}Full cache reset.{Z}")
            return _json_resp({"status": "reset", "site": "all"})


# ─────────────────────────────────────────────────────────────────────────────
#  Background status ticker
# ─────────────────────────────────────────────────────────────────────────────

async def _status_ticker_loop() -> None:
    try:
        while True:
            await asyncio.sleep(30)
            print_status()
    except asyncio.CancelledError:
        pass   # clean exit — don't propagate


# ─────────────────────────────────────────────────────────────────────────────
#  Startup banner
# ─────────────────────────────────────────────────────────────────────────────

def print_header(host: str, port: int) -> None:
    if not _COLORAMA_OK:
        print("(colorama not installed — output will be monochrome)")
    print(C + f"""
╔══════════════════════════════════════════════════════════════════════╗
║         Exam Monitor — HTTP Server  v{__version__:<28}   ║
║         JEE Main  +  TG EAPCET  │  GM_xhr POST  │  CSP bypassed    ║
╚══════════════════════════════════════════════════════════════════════╝""" + Z)
    print(f"  Cache   : {D}{CACHE_FILE.resolve()}{Z}")
    print(f"  Log     : {D}{LOG_FILE.resolve()}{Z}")
    print(f"  Notify  : {G if _PLYER_OK else Y}{'enabled' if _PLYER_OK else 'disabled (plyer not installed)'}{Z}")
    print()
    print(f"  {G}HTTP server  →  http://{host}:{port}{Z}")
    print(f"  {D}POST http://{host}:{port}/snapshot  — snapshot endpoint")
    print(f"  GET  http://{host}:{port}/ping      — health check")
    print(f"  GET  http://{host}:{port}/status    — cache summary")
    print(f"  POST http://{host}:{port}/reset     — wipe cache (add ?site=jee|eapcet){Z}")
    print()
    print(f"  {Y}ℹ  CSP on JEE site blocks WebSocket — using GM_xhr POST instead.")
    print(f"     GM_xhr is fully exempt from CSP. No scraping. Browser still pushes.{Z}")
    print()
    print(f"  Tampermonkey will auto-run on JEE / EAPCET tabs.")
    print(f"  {D}Ctrl-C to stop.{Z}")
    print("  " + D + "─" * 68 + Z + "\n")


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────

async def _main_async(host: str, port: int) -> None:
    global _ticker_task

    app = web.Application(middlewares=[body_size_limit])

    # Route table
    app.router.add_post("/snapshot", handle_snapshot)
    app.router.add_post("/reset",    handle_reset)
    app.router.add_get("/ping",      handle_ping)
    app.router.add_get("/",          handle_ping)   # root = health-check alias
    app.router.add_get("/status",    handle_status)
    # Explicit OPTIONS handlers for CORS pre-flight on all routes
    for path in ("/snapshot", "/reset", "/ping", "/status", "/"):
        app.router.add_options(path, handle_options)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    tcp_site = web.TCPSite(runner, host, port)
    await tcp_site.start()

    info(f"{G}Listening on http://{host}:{port}{Z}")

    _ticker_task = asyncio.get_event_loop().create_task(_status_ticker_loop())
    try:
        # Park here until Ctrl-C cancels via KeyboardInterrupt → asyncio.run()
        await asyncio.Event().wait()
    finally:
        _ticker_task.cancel()
        await _ticker_task
        await runner.cleanup()          # ← properly releases the port


def main() -> None:
    global _cache, _notify_enabled, _cache_lock, _start_time

    ap = argparse.ArgumentParser(
        description="Exam Monitor HTTP server (v6).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--host",       default="localhost",
                    help="Interface to bind (use 0.0.0.0 for all interfaces).")
    ap.add_argument("--port",       type=int, default=8765)
    ap.add_argument("--reset",      action="store_true",
                    help="Wipe cache file and start fresh.")
    ap.add_argument("--no-notify",  action="store_true",
                    help="Disable desktop notifications.")
    ap.add_argument("--version",    action="version",
                    version=f"%(prog)s {__version__}")
    args = ap.parse_args()

    if args.reset and CACHE_FILE.exists():
        CACHE_FILE.unlink()
        print(f"  {Y}Cache wiped.{Z}")

    _cache          = load_cache()
    _notify_enabled = not args.no_notify
    _start_time     = time.monotonic()

    print_header(args.host, args.port)

    try:
        # asyncio.Lock must be created inside an event loop on Python 3.10+
        async def _run():
            global _cache_lock
            _cache_lock = asyncio.Lock()
            await _main_async(args.host, args.port)

        asyncio.run(_run())
    except KeyboardInterrupt:
        pass   # shutdown is handled in _main_async's finally block
    finally:
        # Best-effort synchronous save on exit (async loop may be gone)
        try:
            _save_cache_sync(_cache)
        except Exception:
            pass
        print(f"\n\n  {Y}Stopped.  Cache → {CACHE_FILE}{Z}")
        print(f"  {D}Changes  → {LOG_FILE}{Z}\n")


if __name__ == "__main__":
    main()
