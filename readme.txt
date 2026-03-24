# 🎯 Exam Monitor (v2.0)

**Exam Monitor** is a real-time change detector for the **JEE Main** and **TG EAPCET** official websites. Instead of traditional polling (which can be slow or blocked), this tool uses a browser-resident agent to watch for DOM mutations and instantly "pushes" updates to a local Python server.

### 🚀 Key Features
* **CSP-Exempt Transport:** Uses `GM_xmlhttpRequest` to bypass strict Content Security Policies that block WebSockets.
* **Rich Terminal UI:** Beautifully formatted alerts and status tracking powered by the `rich` library.
* **Smart Diffing:** Only alerts on *new* content (Public Notices, News Tickers, or Link updates) using SHA-1 hashing.
* **Desktop Alerts:** Instant notifications and system beeps so you never miss an update.

---

## 🛠️ Setup & Installation

### 1. The Python Server
Requires **Python 3.9+**. 

```bash
# Install dependencies
pip install aiohttp rich plyer

# Run the server
python monitor_server_v7.py
```

### 2. The Browser Agent
1.  Install the **Tampermonkey** extension (Chrome/Brave/Edge).
2.  Create a "New Script" and paste the contents of `monitor_agent.js`.
3.  **Crucial for Brave Users:** * Go to `Site Settings` for the exam websites.
    * Set **Insecure content** to **Allow** (this lets the HTTPS page talk to your `http://localhost` server).

---

## 🖥️ Usage

Once the server is running and the agent is active, simply keep the exam tabs open. 

| Command | Description |
| :--- | :--- |
| `python monitor_server_v7.py` | Start monitoring with default settings. |
| `python monitor_server_v7.py --reset` | Wipe the cache and start a fresh baseline. |
| `python monitor_server_v7.py --port 9000` | Use a custom port (remember to update the JS agent). |
| `python monitor_server_v7.py --no-notify` | Terminal alerts only (no desktop popups). |

### The "ExamMon" Badge
A small status pill will appear in the bottom-right of your browser:
* 🟢 **Watching:** Active and connected.
* 🔵 **Baseline Saved:** Initial site state captured.
* 🔴 **Alerts:** Change detected! Check your terminal.
* ⚪ **Server Offline:** Check if the Python script is running.

---

## 📂 Project Structure
* `monitor_server_v7.py`: The "Brain." Handles diffing, logging, and notifications.
* `monitor_agent.js`: The "Eyes." Watches the DOM for changes and POSTs snapshots.
* `exam_cache.json`: Persists known items so you don't get duplicate alerts on restart.
* `exam_changes.log`: A permanent, timestamped record of every change detected.

---

> [!TIP]
> **Pro-Tip:** For a full technical breakdown of the hashing logic, the CSP bypass mechanics, and how to add new sites, check out our **Project Wiki**.

---
cd "c:\Users\yajath krushna\Documents\vscode projects\site listener\v3"; $content = @'
# 🎯 Exam Monitor (v7.0)

**Exam Monitor** is a real-time change detector for the **JEE Main** and **TG EAPCET** official websites. Instead of traditional polling (which can be slow or blocked), this tool uses a browser-resident agent to watch for DOM mutations and instantly "pushes" updates to a local Python server.

### 🚀 Key Features
* **CSP-Exempt Transport:** Uses `GM_xmlhttpRequest` to bypass strict Content Security Policies that block WebSockets.
* **Rich Terminal UI:** Beautifully formatted alerts and status tracking powered by the `rich` library.
* **Smart Diffing:** Only alerts on *new* content (Public Notices, News Tickers, or Link updates) using SHA-1 hashing.
* **Desktop Alerts:** Instant notifications and system beeps so you never miss an update.

---

## 🛠️ Setup & Installation

### 1. The Python Server
Requires **Python 3.9+**. 

```bash
# Install dependencies
pip install aiohttp rich plyer

# Run the server
python monitor_server_v7.py
```

### 2. The Browser Agent
1.  Install the **Tampermonkey** extension (Chrome/Brave/Edge).
2.  Create a "New Script" and paste the contents of `monitor_agent.js`.
3.  **Crucial for Brave Users:** * Go to `Site Settings` for the exam websites.
    * Set **Insecure content** to **Allow** (this lets the HTTPS page talk to your `http://localhost` server).

---

## 🖥️ Usage

Once the server is running and the agent is active, simply keep the exam tabs open. 

| Command | Description |
| :--- | :--- |
| `python monitor_server_v7.py` | Start monitoring with default settings. |
| `python monitor_server_v7.py --reset` | Wipe the cache and start a fresh baseline. |
| `python monitor_server_v7.py --port 9000` | Use a custom port (remember to update the JS agent). |
| `python monitor_server_v7.py --no-notify` | Terminal alerts only (no desktop popups). |

### The "ExamMon" Badge
A small status pill will appear in the bottom-right of your browser:
* 🟢 **Watching:** Active and connected.
* 🔵 **Baseline Saved:** Initial site state captured.
* 🔴 **Alerts:** Change detected! Check your terminal.
* ⚪ **Server Offline:** Check if the Python script is running.

---

## 📂 Project Structure
* `monitor_server_v7.py`: The "Brain." Handles diffing, logging, and notifications.
* `monitor_agent.js`: The "Eyes." Watches the DOM for changes and POSTs snapshots.
* `exam_cache.json`: Persists known items so you don't get duplicate alerts on restart.
* `exam_changes.log`: A permanent, timestamped record of every change detected.

---

> [!TIP]
> **Pro-Tip:** For a full technical breakdown of the hashing logic, the CSP bypass mechanics, and how to add new sites, check out our **Project Wiki**.

---
