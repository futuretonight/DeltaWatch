<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=28&duration=2500&pause=800&color=00F7FF&center=true&vCenter=true&width=600&lines=Exam+Monitor+v2.0;Real-time+JEE+%2F+EAPCET+Tracker;Zero+Delay+DOM+Detection" />
</p>

<p align="center">
  <a href="https://www.codefactor.io/repository/github/futuretonight/deltawatch">
    <img src="https://www.codefactor.io/repository/github/futuretonight/deltawatch/badge" />
  </a>
  <img src="https://img.shields.io/badge/Python-3.9+-blue?style=for-the-badge&logo=python"/>
  <img src="https://img.shields.io/badge/Status-Active-success?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/License-MIT-purple?style=for-the-badge"/>
</p>

---

# 🎯 Exam Monitor (v2.0)

> ⚡ **Real-time change detection for JEE Main & TG EAPCET websites**

---

## 🚀 Features

✨ **CSP Bypass Engine**  
→ Uses `GM_xmlhttpRequest` to bypass strict site protections  

🧠 **Smart Diffing System**  
→ SHA-1 hashing ensures only *new updates* trigger alerts  

🖥️ **Rich Terminal UI**  
→ Clean, colorful logs using `rich`  

🔔 **Instant Alerts**  
→ Desktop notifications + sound alerts  

⚡ **Zero Delay Detection**  
→ DOM mutation observer = no polling lag  

---

## 🛠️ Setup

### 🧩 Backend (Python)

```bash
pip install aiohttp rich plyer
python monitor_server_v7.py
````

---

### 🌐 Browser Agent

* Install **Tampermonkey**
* Paste `monitor_agent.js`

⚠️ **Brave Fix**

> Allow **Insecure Content** for exam sites

---

## 🖥️ Usage

```bash
python monitor_server_v7.py
```

### Options

| Flag          | Description            |
| ------------- | ---------------------- |
| `--reset`     | Reset stored data      |
| `--port 9000` | Custom port            |
| `--no-notify` | Disable desktop alerts |

---

## 🧠 Status Indicator

| Status      | Meaning            |
| ----------- | ------------------ |
| 🟢 Watching | Active             |
| 🔵 Baseline | Captured           |
| 🔴 Alert    | Change detected    |
| ⚪ Offline   | Server not running |

---

## 📂 Structure

```
📁 project/
 ├── monitor_server_v7.py   # Brain
 ├── monitor_agent.js       # Eyes
 ├── exam_cache.json        # Memory
 └── exam_changes.log       # History
```

## 💡 Pro Tip

> Full architecture, CSP bypass explanation, and extension support → **Wiki**

---

<p align="center">
  ⚡ Built for speed. Designed for students.
</p>
```
