<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Exam Monitor</title>
</head>
<body>

<p>
  <a href="https://www.codefactor.io/repository/github/futuretonight/deltawatch">
    <img src="https://www.codefactor.io/repository/github/futuretonight/deltawatch/badge" alt="CodeFactor" />
  </a>
</p>

<h1>🎯 Exam Monitor (v7.0)</h1>

<p><strong>Exam Monitor</strong> is a real-time change detector for the <strong>JEE Main</strong> and <strong>TG EAPCET</strong> official websites. Instead of traditional polling (which can be slow or blocked), this tool uses a browser-resident agent to watch for DOM mutations and instantly pushes updates to a local Python server.</p>

<h2>🚀 Key Features</h2>
<ul>
  <li><strong>CSP-Exempt Transport:</strong> Uses <code>GM_xmlhttpRequest</code> to bypass strict Content Security Policies that block WebSockets.</li>
  <li><strong>Rich Terminal UI:</strong> Beautifully formatted alerts and status tracking powered by the <code>rich</code> library.</li>
  <li><strong>Smart Diffing:</strong> Only alerts on <em>new</em> content (Public Notices, News Tickers, or Link updates) using SHA-1 hashing.</li>
  <li><strong>Desktop Alerts:</strong> Instant notifications and system beeps so you never miss an update.</li>
</ul>

<hr/>

<h2>🛠️ Setup &amp; Installation</h2>

<h3>1. The Python Server</h3>
<p>Requires <strong>Python 3.9+</strong>.</p>

<pre><code># Install dependencies
pip install aiohttp rich plyer

# Run the server
python monitor_server_v7.py
</code></pre>

<h3>2. The Browser Agent</h3>
<ol>
  <li>Install the <strong>Tampermonkey</strong> extension (Chrome/Brave/Edge).</li>
  <li>Create a "New Script" and paste the contents of <code>monitor_agent.js</code>.</li>
  <li><strong>Crucial for Brave Users:</strong>
    <ul>
      <li>Go to Site Settings for the exam websites.</li>
      <li>Set <strong>Insecure content</strong> to <strong>Allow</strong> (this lets the HTTPS page talk to your <code>http://localhost</code> server).</li>
    </ul>
  </li>
</ol>

<hr/>

<h2>🖥️ Usage</h2>

<p>Once the server is running and the agent is active, simply keep the exam tabs open.</p>

<table border="1" cellpadding="6" cellspacing="0">
  <tr>
    <th>Command</th>
    <th>Description</th>
  </tr>
  <tr>
    <td><code>python monitor_server_v7.py</code></td>
    <td>Start monitoring with default settings.</td>
  </tr>
  <tr>
    <td><code>python monitor_server_v7.py --reset</code></td>
    <td>Wipe the cache and start a fresh baseline.</td>
  </tr>
  <tr>
    <td><code>python monitor_server_v7.py --port 9000</code></td>
    <td>Use a custom port (remember to update the JS agent).</td>
  </tr>
  <tr>
    <td><code>python monitor_server_v7.py --no-notify</code></td>
    <td>Terminal alerts only (no desktop popups).</td>
  </tr>
</table>

<h3>The "ExamMon" Badge</h3>
<ul>
  <li>🟢 <strong>Watching:</strong> Active and connected.</li>
  <li>🔵 <strong>Baseline Saved:</strong> Initial site state captured.</li>
  <li>🔴 <strong>Alerts:</strong> Change detected! Check your terminal.</li>
  <li>⚪ <strong>Server Offline:</strong> Check if the Python script is running.</li>
</ul>

<hr/>

<h2>📂 Project Structure</h2>
<ul>
  <li><code>monitor_server_v7.py</code>: The "Brain." Handles diffing, logging, and notifications.</li>
  <li><code>monitor_agent.js</code>: The "Eyes." Watches the DOM for changes and POSTs snapshots.</li>
  <li><code>exam_cache.json</code>: Persists known items so you don't get duplicate alerts on restart.</li>
  <li><code>exam_changes.log</code>: A permanent, timestamped record of every change detected.</li>
</ul>

<hr/>

<blockquote>
  <strong>💡 Tip:</strong> For a full technical breakdown of the hashing logic, the CSP bypass mechanics, and how to add new sites, check out the <strong>Project Wiki</strong>.
</blockquote>

</body>
</html>
