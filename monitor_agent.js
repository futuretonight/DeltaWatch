// ==UserScript==
// @name         Exam Monitor Agent
// @namespace    exam-monitor
// @version      5.0
// @description  Monitors JEE Main + TG EAPCET. Uses GM_xmlhttpRequest POST (CSP-exempt) instead of WebSocket.
// @match        https://jeemain.nta.nic.in/*
// @match        https://eapcet.tsche.ac.in/*
// @match        http://eapcet.tsche.ac.in/*
// @match        https://eapcet.tgche.ac.in/*
// @match        http://eapcet.tgche.ac.in/*
// @grant        GM_xmlhttpRequest
// @grant        GM_info
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-idle
// @noframes
// ==/UserScript==

(function () {
    'use strict';

    // ── Config ────────────────────────────────────────────────────────────────
    var SERVER = 'http://localhost:8765';
    var THROTTLE_MS  = 1000;   // min ms between snapshot POSTs
    var HEARTBEAT_MS = 20000;  // keepalive ping interval
    var PERIODIC_MS  = 15000;  // periodic re-snapshot (belt+suspenders)
    var RETRY_MS     = 5000;   // retry delay when server unreachable

    // ── Site detection ────────────────────────────────────────────────────────
    var HOST = location.hostname;
    var SITE = HOST.indexOf('jeemain') !== -1 ? 'jee'
             : HOST.indexOf('eapcet')  !== -1 ? 'eapcet'
             : 'unknown';

    if (SITE === 'unknown') {
        console.warn('[ExamMonitor] Unknown site — agent inactive.');
        return;
    }

    if (window.__examMonitorRunning) {
        console.log('[ExamMonitor] Already running.');
        return;
    }
    window.__examMonitorRunning = true;

    // ── Badge ─────────────────────────────────────────────────────────────────
    var docRef = (typeof unsafeWindow !== 'undefined') ? unsafeWindow.document : document;

    // Create badge immediately — no async, no null risk
    var badge = docRef.getElementById('__examMonitorBadge');
    if (!badge) {
        badge = docRef.createElement('div');
        badge.id = '__examMonitorBadge';
        badge.style.cssText = [
            'position:fixed', 'bottom:12px', 'right:12px',
            'padding:5px 14px', 'border-radius:20px',
            'font-size:11px', 'font-weight:bold', 'font-family:monospace',
            'z-index:2147483647', 'cursor:default', 'user-select:none',
            'box-shadow:0 2px 10px rgba(0,0,0,.5)',
            'transition:background .4s',
            'color:#fff', 'background:#888',
        ].join(';');
        badge.textContent = 'ExamMon: connecting…';
        (function appendBadge() {
            if (docRef.body) { docRef.body.appendChild(badge); }
            else { setTimeout(appendBadge, 50); }
        })();
    }

    function setBadge(text, color) {
        badge.textContent = 'ExamMon: ' + text;
        badge.style.background = color;
    }

    // ── FNV-1a hash ───────────────────────────────────────────────────────────
    function fnv(str) {
        var h = 2166136261;
        for (var i = 0; i < str.length; i++) {
            h ^= str.charCodeAt(i);
            h = Math.imul(h, 16777619) >>> 0;
        }
        return h.toString(16);
    }

    function clean(el) {
        return (el.textContent || '').replace(/\s+/g, ' ').trim();
    }

    // ── Extractors ────────────────────────────────────────────────────────────

    function fullTextBlocks() {
        var blocks = [];
        var seen = {};
        var els = docRef.querySelectorAll('h1,h2,h3,h4,p,li');
        for (var i = 0; i < els.length; i++) {
            var el = els[i];
            if (el.id === '__examMonitorBadge') continue;
            if (el.closest && el.closest('#__examMonitorBadge')) continue;
            var t = clean(el);
            if (t.length < 10) continue;
            var k = fnv(t);
            if (!seen[k]) { seen[k] = 1; blocks.push({ text: t, href: '' }); }
        }
        return blocks;
    }

    function allLinks() {
        var links = [];
        var seen = {};
        var els = docRef.querySelectorAll('a[href]');
        for (var i = 0; i < els.length; i++) {
            var a = els[i];
            var text = clean(a);
            var href = a.href || '';
            if (!text || text.length < 4) continue;
            var k = fnv(text + href);
            if (!seen[k]) { seen[k] = 1; links.push({ text: text, href: href }); }
        }
        return links;
    }

    function pageHash() {
        return fnv(clean(docRef.body));
    }

    // JEE
    function jeeLastUpdated() {
        var ps = docRef.querySelectorAll('p');
        for (var i = 0; i < ps.length; i++) {
            if (ps[i].textContent.indexOf('Last Updated') !== -1) {
                var s = ps[i].querySelector('strong');
                if (s) return clean(s);
            }
        }
        return null;
    }

    function jeePublicNotices() {
        var panel = docRef.querySelector('#1648447930282-deb48cc0-95ec');
        if (!panel) return [];
        var items = [];
        var links = panel.querySelectorAll('li a');
        for (var i = 0; i < links.length; i++) {
            var t = clean(links[i]);
            if (t) items.push({ text: t, href: links[i].href || '' });
        }
        return items;
    }

    function jeeCandidateActivity() {
        var items = [];
        var heads = docRef.querySelectorAll('h2');
        for (var i = 0; i < heads.length; i++) {
            if (clean(heads[i]) !== 'Candidate Activity') continue;
            var ul = null;
            var sib = heads[i].nextElementSibling;
            while (sib) {
                if (sib.tagName === 'UL') { ul = sib; break; }
                var found = sib.querySelector('ul');
                if (found) { ul = found; break; }
                if (/^H[2-4]$/.test(sib.tagName)) break;
                sib = sib.nextElementSibling;
            }
            if (ul) {
                var as = ul.querySelectorAll('li a');
                for (var j = 0; j < as.length; j++) {
                    var t = clean(as[j]);
                    if (t) items.push({ text: t, href: as[j].href || '' });
                }
            }
        }
        return items;
    }

    function jeeLatestNews() {
        var items = [];
        var seen = {};
        var lis = docRef.querySelectorAll('.newsticker .slides li');
        for (var i = 0; i < lis.length; i++) {
            if (lis[i].classList.contains('clone')) continue;
            var a = lis[i].querySelector('a');
            var text = a ? clean(a) : clean(lis[i]);
            var href = a ? (a.href || '') : '';
            var k = fnv(text);
            if (text && !seen[k]) { seen[k] = 1; items.push({ text: text, href: href }); }
        }
        return items;
    }

    // EAPCET
    function eapcetLatestUpdates() {
        var items = [];
        var seen = {};
        var cards = docRef.querySelectorAll('.card');
        for (var i = 0; i < cards.length; i++) {
            var hdr = cards[i].querySelector('h4');
            if (!hdr || clean(hdr).indexOf('Latest Updates') === -1) continue;
            var lis = cards[i].querySelectorAll('li');
            for (var j = 0; j < lis.length; j++) {
                var text = clean(lis[j]).replace(/new\.gif/gi, '').trim();
                if (text.length < 10) continue;
                var a = lis[j].querySelector('a');
                var href = a ? (a.href || '') : '';
                var k = fnv(text);
                if (!seen[k]) { seen[k] = 1; items.push({ text: text, href: href }); }
            }
        }
        if (items.length === 0) {
            var els = docRef.querySelectorAll('.news-item, .blink_me');
            for (var ii = 0; ii < els.length; ii++) {
                var t = clean(els[ii]).replace(/new\.gif/gi, '').trim();
                if (t.length < 10) continue;
                var aa = els[ii].querySelector('a');
                var h = aa ? (aa.href || '') : '';
                var kk = fnv(t);
                if (!seen[kk]) { seen[kk] = 1; items.push({ text: t, href: h }); }
            }
        }
        return items;
    }

    // ── Snapshot builder ──────────────────────────────────────────────────────
    function buildSnapshot() {
        var snap = {
            pageHash: pageHash(),
            fullTextBlocks: fullTextBlocks(),
            allLinks: allLinks(),
        };
        if (SITE === 'jee') {
            snap.lastUpdated = jeeLastUpdated();
            snap.publicNotices = jeePublicNotices();
            snap.candidateActivity = jeeCandidateActivity();
            snap.latestNews = jeeLatestNews();
        } else {
            snap.latestUpdates = eapcetLatestUpdates();
        }
        return snap;
    }

    // ── GM_xhr POST (the core — bypasses CSP entirely) ────────────────────────
    var lastPostAt = 0;
    var throttleTimer = null;
    var serverReachable = false;

    function post(payload, onSuccess, onFail) {
        GM_xmlhttpRequest({
            method:  'POST',
            url:     SERVER + '/snapshot',
            headers: { 'Content-Type': 'application/json' },
            data:    JSON.stringify(payload),
            timeout: 8000,
            onload: function (r) {
                serverReachable = true;
                if (onSuccess) onSuccess(r);
            },
            onerror: function () {
                serverReachable = false;
                if (onFail) onFail();
            },
            ontimeout: function () {
                serverReachable = false;
                if (onFail) onFail();
            },
        });
    }

    function sendSnapshot(reason) {
        var now = Date.now();
        if (now - lastPostAt < THROTTLE_MS) {
            clearTimeout(throttleTimer);
            throttleTimer = setTimeout(function () { sendSnapshot('throttled'); }, THROTTLE_MS);
            return;
        }
        lastPostAt = now;

        var snap = buildSnapshot();
        post(
            { kind: 'snapshot', site: SITE, data: snap, reason: reason },
            function (r) {
                try {
                    var msg = JSON.parse(r.responseText);

                    if (msg.status === 'baseline_saved') {
                        console.log('[ExamMonitor] Baseline saved by server.');
                        setBadge('baseline saved ✓', '#2980b9');
                        setTimeout(function () { setBadge('watching', '#1a7f3c'); }, 3000);
                    }

                    if (msg.status === 'diffed') {
                        var alerts = msg.total_alerts || 0;
                        if (msg.changed) {
                            setBadge('🔔 ' + alerts + ' alert(s)', '#c0392b');
                            console.warn('[ExamMonitor] Change detected — check your terminal!');
                        } else {
                            setBadge('watching', '#1a7f3c');
                        }
                    }
                } catch (_e) {}
            },
            function () {
                setBadge('server offline?', '#c0392b');
                console.warn('[ExamMonitor] Server unreachable — is monitor_server.py running?');
            }
        );
    }

    // ── Hello handshake ───────────────────────────────────────────────────────
    function sendHello() {
        post(
            { kind: 'hello', site: SITE, url: location.href },
            function (r) {
                try {
                    var msg = JSON.parse(r.responseText);
                    if (msg.status === 'welcome') {
                        var c = msg.cache_counts || {};
                        console.log('[ExamMonitor] Connected. Cache — '
                            + 'notices:' + (c.public_notices || 0)
                            + ' activity:' + (c.candidate_activity || 0)
                            + ' updates:' + (c.latest_updates || 0)
                            + ' links:' + (c.known_links || 0));
                        setBadge('connected ✓', '#1a7f3c');
                        if (msg.is_first_run) {
                            console.log('[ExamMonitor] First run — seeding baseline.');
                        }
                        // Send first snapshot immediately after hello
                        sendSnapshot('initial');
                    }
                } catch (_e) {}
            },
            function () {
                setBadge('server offline?', '#c0392b');
                console.warn('[ExamMonitor] Server not reachable. Retrying in ' + (RETRY_MS / 1000) + 's…');
                setTimeout(sendHello, RETRY_MS);
            }
        );
    }

    // ── Heartbeat ─────────────────────────────────────────────────────────────
    setInterval(function () {
        post({ kind: 'ping', site: SITE }, null, null);
    }, HEARTBEAT_MS);

    // ── Periodic re-snapshot ──────────────────────────────────────────────────
    setInterval(function () {
        sendSnapshot('periodic');
    }, PERIODIC_MS);

    // ── MutationObserver ──────────────────────────────────────────────────────
    var observer = new MutationObserver(function () { sendSnapshot('mutation'); });
    observer.observe(docRef.body || docRef.documentElement, {
        childList: true, subtree: true, characterData: true,
    });

    // Targeted watchers
    if (SITE === 'jee') {
        ['#1648447930282-deb48cc0-95ec', '.newsticker', 'footer'].forEach(function (sel) {
            var el = docRef.querySelector(sel);
            if (el) observer.observe(el, { childList: true, subtree: true, characterData: true });
        });
    }
    if (SITE === 'eapcet') {
        var cards = docRef.querySelectorAll('.card');
        for (var i = 0; i < cards.length; i++) {
            var h = cards[i].querySelector('h4');
            if (h && clean(h).indexOf('Latest Updates') !== -1) {
                observer.observe(cards[i], { childList: true, subtree: true, characterData: true });
            }
        }
        var uls = docRef.querySelectorAll('ul.list-services, ul.demo1');
        for (var j = 0; j < uls.length; j++) {
            observer.observe(uls[j], { childList: true, subtree: true });
        }
    }

    // ── Background tab re-snapshot ────────────────────────────────────────────
    docRef.addEventListener('visibilitychange', function () {
        if (docRef.visibilityState === 'visible') sendSnapshot('tab-visible');
    });

    // ── Page unload ───────────────────────────────────────────────────────────
    window.addEventListener('beforeunload', function () { observer.disconnect(); });

    // ── Start ─────────────────────────────────────────────────────────────────
    // Small delay so badge is guaranteed appended before first server response
    setTimeout(function () {
        sendHello();
        console.log('[ExamMonitor] Agent v5.0 active on '
            + SITE.toUpperCase() + ' → ' + SERVER);
    }, 300);

})();
