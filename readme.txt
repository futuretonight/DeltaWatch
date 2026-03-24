<h1 align="center">





<img src="https://www.google.com/search?q=https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/eye.svg" alt="DeltaWatch Logo" width="128" style="filter: invert(36%) sepia(85%) saturate(1006%) hue-rotate(185deg) brightness(91%) contrast(101%);">





DeltaWatch





</h1>

<h4 align="center">Zero-latency mutation surveillance for JEE Main & TG EAPCET.</h4>

<p align="center">
<a href="https://www.python.org/">
<img src="https://www.google.com/search?q=https://img.shields.io/badge/Python-3.9%2B-3776AB%3Fstyle%3Dfor-the-badge%26logo%3Dpython%26logoColor%3Dwhite" alt="Python Version"/>
</a>
<a href="https://www.apache.org/licenses/LICENSE-2.0">
<img src="https://www.google.com/search?q=https://img.shields.io/badge/License-Apache%25202.0-D22128%3Fstyle%3Dfor-the-badge%26logo%3Dapache%26logoColor%3Dwhite" alt="License"/>
</a>
<a href="#">
<img src="https://www.google.com/search?q=https://img.shields.io/badge/Bypass-CSP_Exempt-005963%3Fstyle%3Dfor-the-badge%26logo%3Dsecurityscorecard%26logoColor%3Dwhite" alt="CSP Status"/>
</a>
</p>

<p align="center">
<a href="#-what-is-it">What is it?</a> •
<a href="#-key-features">Features</a> •
<a href="#-quick-start">Quick Start</a> •
<a href="#-architecture">Architecture</a> •
<a href="#-license">License</a>
</p>

🔍 What is it?

DeltaWatch is a real-time change detection suite specifically engineered for high-stakes exam portals. Unlike traditional scrapers that rely on periodic HTTP polling, DeltaWatch uses a MutationObserver agent that lives inside the browser. It detects DOM changes the millisecond they occur and tunnels a snapshot to a local Python server.

It is designed to solve the "Strict CSP" problem. While sites like JEE Main block WebSockets (ws://) via Content Security Policy, DeltaWatch utilizes GM_xmlhttpRequest to bypass these restrictions entirely, ensuring a 100% reliable connection.

✨ Key Features

Mutation Surveillance: Reacts to live AJAX updates, ticker changes, and document injections instantly.

CSP-Exempt Transport: Uses the extension network stack to bypass site-level security headers.

SHA-1 Diff Engine: Smart hashing prevents duplicate alerts. You only get notified when content actually changes.

Rich Dashboard: A beautiful terminal interface powered by the rich library with color-coded event logging.

Persistence Layer: Saves site states to exam_cache.json so you can restart the server without losing the baseline.

🚀 Quick Start

1. Install Dependencies

The server requires Python 3.9+ and a few lightweight libraries.

pip install aiohttp rich plyer


2. Run the Brain

Start the monitoring server on your local machine.

python monitor_server_v7.py


3. Setup the Agent

Install the Tampermonkey extension.

Create a new script and paste the contents of monitor_agent.js.

Important for Brave/Chrome: Open Site Settings for the exam page and set Insecure content to Allow. This enables the browser to talk to http://localhost.

🏗 Architecture

Class / File

Description

monitor_server_v7.py

The central hub. Handles async HTTP requests, diffing logic, and notifications.

monitor_agent.js

The browser agent. Scans the DOM and handles throttled snapshots.

exam_cache.json

The local state store. Keeps SHA-1 hashes of all known items.

exam_changes.log

A permanent, append-only ledger of every detected website change.

📜 License

Copyright (c) 2026 Yajath Krushna.

DeltaWatch is licensed under the Apache License 2.0.

[!IMPORTANT]

Recognition Policy: You are free to use, modify, and distribute this software. However, you must retain all original copyright headers and attribute the work to the original author (Yajath Krushna). Redistribution without attribution is strictly prohibited.

<p align="center">
Developed for the student community by Yajath Krushna.
</p>