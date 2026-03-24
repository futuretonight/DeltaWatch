"""
╔══════════════════════════════════════════════════════════════════════╗
║                 DeltaWatch (Exam Monitor)                            ║
║         JEE Main  +  TG EAPCET  │  GM_xhr POST  │  CSP bypassed      ║
╚══════════════════════════════════════════════════════════════════════╝

# ----------------------------------------------------------------
# Project: deltawatch (Exam Monitor)
# Author:  Yajath Krushna (https://github.com/futuretonight)
# License: Apache License 2.0
# Copyright (c) 2026 Yajath Krushna
# ----------------------------------------------------------------

Install:
    pip install aiohttp rich plyer

Run:
    python server_monitor.py
    python server_monitor.py --port 8765
    python server_monitor.py --reset
    python server_monitor.py --no-notify
    python server_monitor.py --host 0.0.0.0   # all interfaces

Endpoints:
    POST http://localhost:8765/snapshot       — browser pushes DOM snapshot
    GET  http://localhost:8765/ping           — health check
    GET  http://localhost:8765/status         — cache summary (JSON)
    POST http://localhost:8765/reset          — wipe all caches
    POST http://localhost:8765/reset?site=jee — wipe one site's cache

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
from typing import Optional

__version__ = "2.0.0"

# file paths:- 

CACHE_FILE = Path("exam_cache.json")
LOG_FILE   = Path("exam_changes.log")

# CONSTANTS
MAX_BODY_BYTES  = 2 * 1024 * 1024   # 2 MB inbound cap
MAX_CACHE_ITEMS = 500               # per list — prevents unbounded growth
KNOWN_SITES     = frozenset({"jee", "eapcet"})

# Short label used in panel titles / notifications
SITE_SHORT: dict[str, str] = {
    "jee":    "JEE Main",
    "eapcet": "TG EAPCET",
}

# Long label used in status line
SITE_LABELS: dict[str, str] = {
    "jee":    "JEE Main  (jeemain.nta.nic.in)",
    "eapcet": "TG EAPCET (eapcet.tgche.ac.in)",
}

#╔══════════════════════════════════════════════════════════════════════╗
#║                  Hard dependency check                               ║ 
#╚══════════════════════════════════════════════════════════════════════╝

_MISSING: list[str] = []
for _pkg in ("aiohttp", "rich"):
    try:
        __import__(_pkg)
    except ImportError:
        _MISSING.append(_pkg)

if _MISSING:
    print(f"[ERROR] Required packages missing: {', '.join(_MISSING)}")
    print(f"        pip install {' '.join(_MISSING)}")
    sys.exit(1)

from aiohttp import web                             # noqa: E402
from rich.console import Console                    # noqa: E402
from rich.panel import Panel                        # noqa: E402
from rich.table import Table                        # noqa: E402
from rich.rule import Rule                          # noqa: E402
from rich.text import Text                          # noqa: E402
from rich import box as rich_box                    # noqa: E402

try:
    from plyer import notification as _plyer        # type: ignore[import]
    _PLYER_OK = True
except ImportError:
    _PLYER_OK = False
    _plyer = None
    
# console
console = Console(highlight=False)

# logging here
logging.basicConfig(level=logging.WARNING)
_log = logging.getLogger("exam_monitor")

# ── Global state ──────────────────────────────────────────────────────────────
# _connected_sites stores raw keys ("jee", "eapcet") — labels resolved at display
_cache: dict              = {}
_notify_enabled: bool     = True
_request_count: int       = 0
_connected_sites: set     = set()          # stores "jee" / "eapcet" only
_start_time: float        = 0.0
_cache_lock: Optional[asyncio.Lock] = None
_ticker_task: Optional[asyncio.Task] = None

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

def _empty_cache() -> dict:
    return {
        "jee":    _empty_site(),
        "eapcet": _empty_site(),
        "meta": {
            "created":      datetime.now().isoformat(),
            "last_save":    None,
            "total_alerts": 0,
        },
    }

def _backfill_hashes(items: list) -> list:
    """Add missing 'hash' fields to items loaded from older cache files."""
    out: list[dict] = []
    for raw in items:
        item = dict(raw)
        if "hash" not in item:
            item["hash"] = item_hash(item.get("text", ""), item.get("href", ""))
        out.append(item)
    return out

def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Ensure meta block exists
            if "meta" not in data or not isinstance(data["meta"], dict):
                data["meta"] = _empty_cache()["meta"]
            # Ensure site blocks exist and back-fill hashes
            for sk in KNOWN_SITES:
                if sk not in data or not isinstance(data[sk], dict):
                    data[sk] = _empty_site()
                else:
                    for list_key in (
                        "public_notices", "candidate_activity", "latest_news_jee",
                        "latest_updates", "full_text_blocks", "known_links",
                    ):
                        if isinstance(data[sk].get(list_key), list):
                            data[sk][list_key] = _backfill_hashes(data[sk][list_key])
            return data
        except Exception as exc:
            _log.warning("Cache file unreadable, starting fresh: %s", exc)
    return _empty_cache()

def _save_cache_sync(cache: dict) -> None:
    """Blocking write — always call via asyncio.to_thread()."""
    cache["meta"]["last_save"] = datetime.now().isoformat()
    tmp = CACHE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2, ensure_ascii=False)
    tmp.replace(CACHE_FILE)  # atomic on POSIX, near-atomic on Windows

async def save_cache(cache: dict) -> None:
    try:
        await asyncio.to_thread(_save_cache_sync, cache)
    except Exception as exc:
        _log.error("save_cache failed: %s", exc)

def _log_change_sync(site: str, section: str, items: list) -> None:
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
        _log.error("log_change failed: %s", exc)

#╔══════════════════════════════════════════════════════════════════════╗
#║                      item helpers                                    ║
#╚══════════════════════════════════════════════════════════════════════╝

def item_hash(text: str, href: str = "") -> str:
    return hashlib.sha1(
        f"{text.strip()}||{href.strip()}".encode()
    ).hexdigest()[:14]

def enrich(items: object) -> list:
    """Validate, normalise, and timestamp a raw items list from the browser."""
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
    try:
        known = {i["hash"] for i in cached if isinstance(i, dict)}
    except Exception:
        known = set()
    return [i for i in live if isinstance(i, dict) and i.get("hash") not in known]

def merge(cached: list, live: list, cap: int = MAX_CACHE_ITEMS) -> list:
    try:
        known = {i["hash"] for i in cached if isinstance(i, dict)}
    except Exception:
        known = set()
    combined = [i for i in live if isinstance(i, dict) and i.get("hash") not in known] + cached
    return combined[:cap]

#╔══════════════════════════════════════════════════════════════════════╗
#║        notification and sound module                                 ║
#╚══════════════════════════════════════════════════════════════════════╝

def notify(title: str, body: str) -> None:
    if not _notify_enabled or _plyer is None:
        return
    try:
        _plyer.notify(title=title, message=body[:256],
                      app_name="Exam Monitor", timeout=8)
    except Exception:
        pass

def beep() -> None:
    try:
        if platform.system() == "Windows":
            import winsound
            winsound.Beep(1000, 250)
            winsound.Beep(1300, 180)
        else:
            sys.stdout.write("\a\a")
            sys.stdout.flush()
    except Exception:
        pass

#╔══════════════════════════════════════════════════════════════════════╗
#║                            ui stuff                                  ║
#╚══════════════════════════════════════════════════════════════════════╝

def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")

def _uptime_str() -> str:
    total = int(time.monotonic() - _start_time)
    h, r  = divmod(total, 3600)
    m, s  = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def print_header(host: str, port: int) -> None:
    """Startup banner."""
    title = Text.assemble(
        ("DeltaWatch (website monitor)  ", "bold cyan"),
        (f"v{__version__}", "bold white"),
        ("  │  JEE Main + TG EAPCET", "dim cyan"),
    )
    body = Text()
    body.append(f"  Cache  : ", style="dim")
    body.append(str(CACHE_FILE.resolve()), style="cyan")
    body.append(f"\n  Log    : ", style="dim")
    body.append(str(LOG_FILE.resolve()), style="cyan")
    body.append(f"\n  Notify : ", style="dim")
    if _PLYER_OK:
        body.append("enabled", style="green")
    else:
        body.append("disabled  (pip install plyer)", style="yellow")
    body.append(f"\n\n  Server : ", style="dim")
    body.append(f"http://{host}:{port}", style="bold green")
    body.append(f"\n\n  POST  /snapshot          browser pushes DOM snapshot", style="dim")
    body.append(f"\n  GET   /ping              health check", style="dim")
    body.append(f"\n  GET   /status            cache summary (JSON)", style="dim")
    body.append(f"\n  POST  /reset[?site=jee]  wipe cache at runtime", style="dim")
    body.append(f"\n\n  ℹ  CSP on JEE blocks WebSocket → GM_xhr POST (CSP-exempt) used instead.", style="yellow")
    body.append(f"\n  put the js script in Tampermonkey so it can auto-run on JEE / EAPCET tabs.  Ctrl-C to stop.", style="dim")
    console.print(Panel(body, title=title, border_style="cyan", padding=(0, 1)))
    console.print()


def print_info(msg: str) -> None:
    console.print(f"  [dim][[{_now()}]][/dim]  {msg}")


def print_status() -> None:
    """Periodic status line — rendered cleanly by rich (no \\r tricks needed)."""
    alerts = _cache.get("meta", {}).get("total_alerts", 0)
    alert_style = "bold red" if alerts else "bold green"

    if _connected_sites:
        # Show short labels for connected sites
        labels = [SITE_LABELS.get(s, s) for s in sorted(_connected_sites)]
        sites_str = "  •  ".join(labels)
        sites_markup = f"[bold green]{sites_str}[/bold green]"
    else:
        sites_markup = "[dim]none[/dim]"

    console.print(
        f"  [dim][[{_now()}]][/dim]"
        f"  up [cyan]{_uptime_str()}[/cyan]"
        f"  │  active: {sites_markup}"
        f"  │  requests: [dim]{_request_count}[/dim]"
        f"  │  alerts: [{alert_style}]{alerts}[/{alert_style}]"
    )


def alert_box(site: str, section: str, items: list) -> None:
    """Print a rich alert panel for newly detected items."""
    short = SITE_SHORT.get(site, site.upper())

    # Build the items table
    tbl = Table(
        box=rich_box.SIMPLE,
        show_header=False,
        padding=(0, 1),
        expand=True,
    )
    tbl.add_column("icon",   style="bold magenta", no_wrap=True, width=3)
    tbl.add_column("text",   style="white")
    tbl.add_column("href",   style="dim cyan")

    for item in items:
        text = item.get("text", "").strip()
        href = item.get("href", "").strip()
        tbl.add_row("➕", text, href if href else "")

    title = Text.assemble(
        ("🔔 ", ""),
        (f"[{_now()}]  ", "dim white"),
        (short, "bold white"),
        ("  —  ", "dim white"),
        (section, "bold yellow"),
    )
    console.print(
        Panel(tbl, title=title, border_style="bold red", padding=(0, 1))
    )


def date_change_box(site: str, old: str, new: str) -> None:
    body = Text()
    body.append("  Was : ", style="dim")
    body.append(old, style="yellow")
    body.append("\n  Now : ", style="dim")
    body.append(new, style="bold green")

    title = Text.assemble(
        ("🗓  ", ""),
        (f"[{_now()}]  ", "dim white"),
        ("JEE Main — SITE DATE CHANGED", "bold red"),
    )
    console.print(Panel(body, title=title, border_style="bold red", padding=(0, 1)))


def baseline_box(site: str, counts: dict) -> None:
    short = SITE_SHORT.get(site, site.upper())
    tbl = Table(box=rich_box.SIMPLE, show_header=False, padding=(0, 1))
    tbl.add_column("key",   style="dim")
    tbl.add_column("count", style="bold cyan", justify="right")
    for k, v in counts.items():
        if isinstance(v, list):
            tbl.add_row(k, str(len(v)))
        elif v is not None:
            tbl.add_row(k, str(v))

    title = Text.assemble(
        ("📥  ", ""),
        (f"[{_now()}]  ", "dim white"),
        (f"{short} — baseline seeded", "bold cyan"),
    )
    console.print(Panel(tbl, title=title, border_style="cyan", padding=(0, 1)))


#╔══════════════════════════════════════════════════════════════════════╗
#║        difference checking engine                                    ║
#╚══════════════════════════════════════════════════════════════════════╝

async def diff_snapshot(site: str, snap: dict) -> bool:
    """
    Diff *snap* against cached state for *site*.  Returns True if any alert fired.
    Must be called while _cache_lock is held.
    """
    sc      = _cache.setdefault(site, _empty_site())
    short   = SITE_SHORT.get(site, site.upper())
    changed = False

    # ── Whole-page text blocks (catch-all) ────────────────────────────────────
    live_blocks = enrich(snap.get("fullTextBlocks", []))
    new_blocks  = find_new(sc.get("full_text_blocks", []), live_blocks)
    if new_blocks:
        meaningful = [b for b in new_blocks if len(b.get("text", "").strip()) > 20]
        if meaningful:
            alert_box(site, "⚠ New page content", meaningful)
            await log_change(site, "Whole-page content", meaningful)
            notify(
                f"{short} — Page updated",
                "\n".join(str(i.get("text", ""))[:80] for i in meaningful[:3]),
            )
            beep()
            changed = True
    sc["full_text_blocks"] = merge(sc.get("full_text_blocks", []), live_blocks)

    # ── New links ─────────────────────────────────────────────────────────────
    live_links = enrich(snap.get("allLinks", []))
    new_links  = find_new(sc.get("known_links", []), live_links)
    if new_links:
        real = [
            lnk for lnk in new_links
            if lnk.get("href", "").startswith("http") and len(str(lnk.get("text", ""))) > 5
        ]
        if real:
            alert_box(site, "🔗 New link(s)", real)
            await log_change(site, "New links", real)
            notify(
                f"{short} — New link",
                "\n".join(str(i.get("text", ""))[:80] for i in real[:3]),
            )
            beep()
            changed = True
    sc["known_links"] = merge(sc.get("known_links", []), live_links)

    # ── Update stored page hash ───────────────────────────────────────────────
    live_hash = snap.get("pageHash")
    if live_hash:
        sc["page_hash"] = live_hash

    # ── JEE-specific ──────────────────────────────────────────────────────────
    if site == "jee":
        live_date = snap.get("lastUpdated")
        if live_date and live_date != sc.get("last_updated_date"):
            old = sc.get("last_updated_date") or "—"
            if old != "—":   # only alert if we had a previous value
                date_change_box(site, old, live_date)
                await log_change(site, "Last Updated Date",
                                 [{"text": f"{old} → {live_date}", "href": ""}])
                notify("JEE — Site date changed", f"{old} → {live_date}")
                beep()
                changed = True
            sc["last_updated_date"] = live_date

        for snap_key, section_label, cache_key in (
            ("publicNotices",     "📋 Public Notices",     "public_notices"),
            ("candidateActivity", "🎓 Candidate Activity", "candidate_activity"),
            ("latestNews",        "📰 Latest News Ticker", "latest_news_jee"),
        ):
            live = enrich(snap.get(snap_key, []))
            new  = find_new(sc.get(cache_key, []), live)
            if new:
                alert_box(site, section_label, new)
                await log_change(site, section_label, new)
                notify(
                    f"JEE — {section_label}",
                    "\n".join(str(i.get("text", ""))[:80] for i in new[:3]),
                )
                beep()
                changed = True
            sc[cache_key] = merge(sc.get(cache_key, []), live)

    # ── EAPCET-specific ───────────────────────────────────────────────────────
    elif site == "eapcet":
        live = enrich(snap.get("latestUpdates", []))
        new  = find_new(sc.get("latest_updates", []), live)
        if new:
            alert_box(site, "📋 Latest Updates", new)
            await log_change(site, "Latest Updates", new)
            notify(
                "TG EAPCET — New Update",
                "\n".join(str(i.get("text", ""))[:80] for i in new[:3]),
            )
            beep()
            changed = True
        sc["latest_updates"] = merge(sc.get("latest_updates", []), live)

    return changed


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

_CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type":                 "application/json",
}


def _json(data: dict, status: int = 200) -> web.Response:
    return web.Response(
        status=status,
        headers=_CORS_HEADERS,
        text=json.dumps(data, ensure_ascii=False),
    )


# ── Middleware: cap inbound payload ───────────────────────────────────────────
@web.middleware
async def body_size_limit(request: web.Request, handler):
    cl = request.content_length
    if cl is not None and cl > MAX_BODY_BYTES:
        return _json({"status": "error", "reason": "payload_too_large"}, status=413)
    return await handler(request)


# ─────────────────────────────────────────────────────────────────────────────
#  Route handlers
# ─────────────────────────────────────────────────────────────────────────────

async def handle_options(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=_CORS_HEADERS)


async def handle_snapshot(request: web.Request) -> web.Response:
    global _request_count

    try:
        body = await request.json()
    except Exception:
        return _json({"status": "error", "reason": "invalid_json"}, status=400)

    if not isinstance(body, dict):
        return _json({"status": "error", "reason": "body_must_be_object"}, status=400)

    site = str(body.get("site", "")).strip().lower()
    kind = str(body.get("kind", "snapshot")).strip().lower()

    assert _cache_lock is not None
    async with _cache_lock:
        _request_count += 1

        # ── Ping (keepalive — no site validation required) ────────────────────
        if kind == "ping":
            if site in KNOWN_SITES:
                _connected_sites.add(site)   # ← store raw key, not label
            return _json({"status": "pong", "site": site})

        # ── Below this point, site must be known ──────────────────────────────
        if site not in KNOWN_SITES:
            return _json(
                {"status": "error", "reason": f"unknown site '{site}'"},
                status=400,
            )

        # handshake checking function
        if kind == "hello":
            _connected_sites.add(site)   # ← raw key
            sc = _cache.get(site, _empty_site())
            print_info(
                f"[bold green]Browser connected[/bold green]  →  {SITE_LABELS.get(site, site)}"
            )
            return _json({
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
        snap = body.get("data")
        if not isinstance(snap, dict):
            return _json(
                {"status": "error", "reason": "missing or invalid 'data' field"},
                status=400,
            )

        _connected_sites.add(site)   # ← raw key
        sc = _cache.setdefault(site, _empty_site())

        # First-ever snapshot → seed the baseline
        if sc.get("page_hash") is None:
            print_info(f"[yellow][{site.upper()}] Seeding baseline …[/yellow]")
            sc["page_hash"]          = snap.get("pageHash")
            sc["public_notices"]     = enrich(snap.get("publicNotices",     []))
            sc["candidate_activity"] = enrich(snap.get("candidateActivity", []))
            sc["latest_updates"]     = enrich(snap.get("latestUpdates",     []))
            sc["full_text_blocks"]   = enrich(snap.get("fullTextBlocks",    []))
            sc["known_links"]        = enrich(snap.get("allLinks",          []))
            sc["latest_news_jee"]    = enrich(snap.get("latestNews",        []))
            sc["last_updated_date"]  = snap.get("lastUpdated")
            await save_cache(_cache)
            baseline_box(site, sc)
            return _json({
                "status":  "baseline_saved",
                "counts": {k: len(v) if isinstance(v, list) else v for k, v in sc.items()},
            })

        # Diff against baseline
        changed = await diff_snapshot(site, snap)
        if changed:
            meta = _cache.setdefault("meta", _empty_cache()["meta"])
            meta["total_alerts"] = meta.get("total_alerts", 0) + 1
        await save_cache(_cache)

        return _json({
            "status":       "diffed",
            "changed":      changed,
            "total_alerts": _cache.get("meta", {}).get("total_alerts", 0),
        })


async def handle_ping(request: web.Request) -> web.Response:
    return _json({
        "status":       "ok",
        "version":      __version__,
        "uptime_s":     int(time.monotonic() - _start_time),
        "total_alerts": _cache.get("meta", {}).get("total_alerts", 0),
        # Resolve labels for external callers
        "sites_seen":   [SITE_LABELS.get(s, s) for s in sorted(_connected_sites)],
        "requests":     _request_count,
    })


async def handle_status(request: web.Request) -> web.Response:
    summary: dict = {}
    for sk in KNOWN_SITES:
        sc = _cache.get(sk, _empty_site())
        summary[sk] = {
            k: len(v) if isinstance(v, list) else v
            for k, v in sc.items()
        }
    return _json({
        "cache":    summary,
        "meta":     _cache.get("meta", {}),
        "uptime_s": int(time.monotonic() - _start_time),
        "version":  __version__,
        "active_sites": [SITE_LABELS.get(s, s) for s in sorted(_connected_sites)],
    })


async def handle_reset(request: web.Request) -> web.Response:
    """POST /reset  or  POST /reset?site=jee|eapcet"""
    assert _cache_lock is not None
    async with _cache_lock:
        site_param = request.rel_url.query.get("site", "").strip().lower()
        if site_param:
            if site_param not in KNOWN_SITES:
                return _json(
                    {"status": "error", "reason": f"unknown site '{site_param}'"},
                    status=400,
                )
            _cache[site_param] = _empty_site()
            _connected_sites.discard(site_param)
            await save_cache(_cache)
            print_info(f"[yellow]Cache reset for site: {site_param}[/yellow]")
            return _json({"status": "reset", "site": site_param})
        else:
            for sk in list(KNOWN_SITES):
                _cache[sk] = _empty_site()
            _cache.setdefault("meta", {})["total_alerts"] = 0
            _connected_sites.clear()
            await save_cache(_cache)
            print_info("[yellow]Full cache reset.[/yellow]")
            return _json({"status": "reset", "site": "all"})


# ─────────────────────────────────────────────────────────────────────────────
#  Background status ticker
# ─────────────────────────────────────────────────────────────────────────────

async def _status_ticker_loop() -> None:
    try:
        while True:
            await asyncio.sleep(30)
            print_status()
    except asyncio.CancelledError:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  Application wiring
# ─────────────────────────────────────────────────────────────────────────────

async def _run(host: str, port: int) -> None:
    global _ticker_task, _cache_lock

    _cache_lock = asyncio.Lock()

    app = web.Application(middlewares=[body_size_limit])
    app.router.add_post("/snapshot", handle_snapshot)
    app.router.add_post("/reset",    handle_reset)
    app.router.add_get("/ping",      handle_ping)
    app.router.add_get("/",          handle_ping)
    app.router.add_get("/status",    handle_status)
    for path in ("/snapshot", "/reset", "/ping", "/status", "/"):
        app.router.add_options(path, handle_options)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    tcp = web.TCPSite(runner, host, port)
    await tcp.start()

    print_info(f"[bold green]Listening on http://{host}:{port}[/bold green]")
    console.print(Rule(style="dim"))

    _ticker_task = asyncio.get_event_loop().create_task(_status_ticker_loop())
    try:
        await asyncio.Event().wait()      # park until KeyboardInterrupt
    finally:
        _ticker_task.cancel()
        await _ticker_task
        await runner.cleanup()            # release port properly


def main() -> None:
    global _cache, _notify_enabled, _start_time

    ap = argparse.ArgumentParser(
        description="Exam Monitor HTTP server (v7).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--host",      default="localhost",
                    help="Interface to bind.")
    ap.add_argument("--port",      type=int, default=8765)
    ap.add_argument("--reset",     action="store_true",
                    help="Wipe cache file and start fresh.")
    ap.add_argument("--no-notify", action="store_true",
                    help="Disable desktop notifications.")
    ap.add_argument("--version",   action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args()

    if args.reset and CACHE_FILE.exists():
        CACHE_FILE.unlink()
        console.print("  [yellow]Cache wiped.[/yellow]")

    _cache          = load_cache()
    _notify_enabled = not args.no_notify
    _start_time     = time.monotonic()

    print_header(args.host, args.port)

    try:
        asyncio.run(_run(args.host, args.port))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            _save_cache_sync(_cache)
        except Exception:
            pass
        console.print()
        console.print(f"  [yellow]Stopped.[/yellow]  Cache → [cyan]{CACHE_FILE}[/cyan]")
        console.print(f"  [dim]Changes → {LOG_FILE}[/dim]")
        console.print()


if __name__ == "__main__":
    main()
