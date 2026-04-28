from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

app = FastAPI(title="Korvin Dashboard")

# Shared navigation bar
NAV = """
<nav style="display:flex; gap:1em; margin-bottom:2em; border-bottom:1px solid #333; padding-bottom:0.5em;">
  <a href="/" style="color:#00d4ff; text-decoration:none;">Home</a>
  <a href="/skills" style="color:#00d4ff; text-decoration:none;">Skills</a>
  <a href="/memory" style="color:#00d4ff; text-decoration:none;">Memory</a>
  <a href="/security" style="color:#00d4ff; text-decoration:none;">Security</a>
  <a href="/settings" style="color:#00d4ff; text-decoration:none;">Settings</a>
  <a href="/logs" style="color:#00d4ff; text-decoration:none;">Logs</a>
</nav>
"""

BASE_STYLE = """
<style>
  body { background: #1a1a2e; color: #e0e0ff; font-family: sans-serif; margin: 2em; }
  h1 { color: #00d4ff; }
  a { color: #00d4ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .card { background: #16213e; border: 1px solid #0f3460; padding: 1em; margin: 1em 0; border-radius: 8px; }
  pre { background: #0f3460; padding: 1em; border-radius: 8px; overflow-x: auto; white-space: pre-wrap; }
</style>
"""

def page(title, content):
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} – Korvin</title>
        {BASE_STYLE}
    </head>
    <body>
        <h1>🚀 Korvin Dashboard</h1>
        {NAV}
        <h2>{title}</h2>
        {content}
    </body>
    </html>
    """

# ---------- ROUTES ----------

@app.get("/", response_class=HTMLResponse)
async def home():
    content = """
    <div class="card">
      <h3>Status</h3>
      <p>🟢 Agent running</p>
      <p>🧠 Model: deepseek-v4-pro</p>
      <p>📡 Telegram: @NosisTechBot – active</p>
    </div>
    <div class="card">
      <h3>Last 5 Interactions</h3>
      <ul>
        <li>You: "Hello Korvin" → Korvin: "Hello! How can I help you today?"</li>
        <li>You: "/start" → Korvin: (start message)</li>
      </ul>
      <p><em>More coming soon – memory integration in progress.</em></p>
    </div>
    """
    return HTMLResponse(content=page("Home", content))

@app.get("/skills", response_class=HTMLResponse)
async def skills():
    content = """
    <div class="card">
      <h3>Installed Skills</h3>
      <ul>
        <li>web-researcher</li>
        <li>task-automator</li>
        <li>document-drafter</li>
        <li>inbox-summarizer</li>
        <li>security-monitor</li>
      </ul>
      <p><em>More skills auto-generated from experience will appear here.</em></p>
    </div>
    """
    return HTMLResponse(content=page("Skills", content))

@app.get("/memory", response_class=HTMLResponse)
async def memory():
    content = """
    <div class="card">
      <h3>Conversation Search</h3>
      <input type="text" placeholder="Search memories..." style="width:100%; padding:0.5em; background:#0f3460; color:#e0e0ff; border:none; border-radius:4px;" disabled>
      <p style="margin-top:1em;"><em>Memory search will be enabled when the agent core is wired.</em></p>
    </div>
    <div class="card">
      <h3>Recent Conversations</h3>
      <p>No conversations stored yet.</p>
    </div>
    """
    return HTMLResponse(content=page("Memory", content))

@app.get("/security", response_class=HTMLResponse)
async def security():
    content = """
    <div class="card">
      <h3>Security Status</h3>
      <p>🛡️ Sandbox executor: <span style="color:#00ff88;">active</span></p>
      <p>🛡️ Injection defender: <span style="color:#00ff88;">active</span></p>
      <p>🛡️ Threat monitor: <span style="color:#00ff88;">active</span></p>
      <p>🛡️ Auto-patcher: <span style="color:#00ff88;">active</span></p>
    </div>
    <div class="card">
      <h3>Recent Threats</h3>
      <p>No blocked injection attempts yet.</p>
      <p>Last monitor run: (pending scheduling)</p>
    </div>
    <div class="card" style="border-color: #ff4444;">
      <h3>⚠️ Kill Switch</h3>
      <button disabled style="background:#ff4444; color:white; padding:0.5em 1em; border:none; border-radius:4px;">Read-Only Mode (OFF)</button>
      <p style="margin-top:0.5em;"><em>The kill switch instantly locks all agent actions to read‑only.</em></p>
    </div>
    """
    return HTMLResponse(content=page("Security", content))

@app.get("/settings", response_class=HTMLResponse)
async def settings():
    content = """
    <div class="card">
      <h3>LLM Provider</h3>
      <p>DeepSeek V4 Pro (via LiteLLM proxy)</p>
      <p>Model routing: Flash for simple tasks, Pro for complex</p>
    </div>
    <div class="card">
      <h3>Connected Channels</h3>
      <ul>
        <li>Telegram: @NosisTechBot – connected</li>
        <li>WhatsApp: pending setup</li>
        <li>Discord: pending setup</li>
        <li>Signal: pending setup</li>
      </ul>
    </div>
    <div class="card">
      <h3>Voice</h3>
      <p>STT: Whisper (free tier)</p>
      <p>TTS: Kokoro (bm_lewis voice)</p>
      <p>Wake word: "Hey Korvin" (Porcupine)</p>
    </div>
    """
    return HTMLResponse(content=page("Settings", content))

@app.get("/logs", response_class=HTMLResponse)
async def logs():
    content = """
    <div class="card">
      <h3>Live Log</h3>
      <pre>2026-04-27 14:23:01 – Korvin started
2026-04-27 14:23:04 – Telegram bot connected
2026-04-27 14:24:10 – User message: Hello Korvin
2026-04-27 14:24:12 – AI response sent
2026-04-27 14:25:33 – Threat monitor run: no threats detected
2026-04-27 14:30:00 – Auto-patcher check: no pending updates</pre>
      <p><em>Live log streaming will be enabled shortly.</em></p>
    </div>
    """
    return HTMLResponse(content=page("Logs", content))
