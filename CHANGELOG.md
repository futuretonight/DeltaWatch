Changes from v1:
  [BUG]  dependency guard now only hard-exits for aiohttp; colorama/plyer
         are truly optional with working fallbacks
  [BUG]  added asyncio.Lock to guard all shared-state mutations —
         concurrent requests could corrupt the cache
  [BUG]  save_cache / log_change now run in a thread (asyncio.to_thread)
         to avoid blocking the event loop on disk I/O
  [BUG]  graceful shutdown now properly calls runner.cleanup() so sockets
         are released; previously the port stayed occupied after Ctrl-C
  [BUG]  diff_snapshot now updates page_hash after each diff cycle so
         repeated identical snapshots don't keep re-alerting on a hash mismatch
  [BUG]  status ticker no longer clobbers alert-box output; prints on a
         fresh line with ANSI erase-to-EOL instead of bare \\r
  [BUG]  unknown / untrusted "site" values are rejected with 400 before
         touching the cache (prevents cache key pollution)
  [BUG]  request body is now capped at MAX_BODY_BYTES (default 2 MB) via
         aiohttp middleware — prevents DoS from huge payloads
  [BUG]  status_ticker is stored as a Task and cancelled on shutdown so the
         server exits cleanly without CancelledError noise
  [FEAT] /reset endpoint accepts optional ?site=jee|eapcet to wipe one site
  [FEAT] --version flag
  [FEAT] uptime reported in /status and /ping responses
  [FEAT] cache lists are capped at MAX_CACHE_ITEMS (default 500) to prevent
         unbounded memory growth over long runs
  [FEAT] full_text_blocks merge now always runs (not only when new_blocks
         is truthy) so the cache stays current even on unchanged pages
		 
  [FIX]  Connected-sites tracking: was storing full label strings in the set
         so any key mismatch silently showed nothing. Now stores raw site keys
         ("jee", "eapcet") and resolves labels only at display time.
  [FIX]  Replaced all manual ANSI / colorama / \\r tricks with the `rich`
         library — no more terminal corruption or overwritten alert boxes.
  [FIX]  Status ticker now uses rich markup and prints on a fresh line every
         time, so it never clobbers alert panels.
  [FIX]  Ping requests no longer require site to be in KNOWN_SITES — browser
         keepalives work even before the first hello handshake.
  [FIX]  `handle_snapshot` now handles the case where `_cache["meta"]` key
         is missing (corrupted cache) without KeyError.	
         
         	 
Pyright issues addressed:-

`_plyer` now defined as `None` on ImportError and `notify()` checks `_plyer is not None`.

All `join(...)` calls now build strings via `str(i.get("text",""))` so Pyright sees `Iterable[str]`.

Added `assert _cache_lock is not None` before `async with _cache_lock` usages.

Added `from typing import Optional` and typed `_cache_lock / _ticker_task` as Optional.
         
		 
		 
		 Why HTTP instead of WebSocket:
  The JEE website sends a strict CSP response header:
    connect-src 'self' *.s3waas.gov.in *.google-analytics.com
  This blocks ALL ws:// connections at the browser level — even from
  Tampermonkey's sandbox. However GM_xmlhttpRequest is fully exempt
  from CSP (confirmed: server returned 426 in diagnostics).
  So we use GM_xhr POST instead — same push architecture, zero scraping.
