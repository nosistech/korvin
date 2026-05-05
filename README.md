# Korvin

**Self-hosted personal AI agent. Voice-first. Memory-persistent. No lock-in.**

Korvin runs on your own machine or a $5 VPS. You bring your API keys. You own your data. No third party ever touches your messages, credentials, or billing.

> ⚠️ **Claude Code users:** If you use Anthropic's Claude Code CLI inside this repo, run it with `ANTHROPIC_API_KEY=your-key claude` instead of your claude.ai subscription. Korvin's source includes directories named `src/openclaw/` and `src/hermes/` (MIT-licensed dependencies) which trigger Anthropic's third-party harness billing detection. A `.claudeignore` file is included to mitigate this, but using an explicit API key is the safest approach. See [Anthropic's billing policy](https://support.claude.ai) for context.

> ⚠️ **For non-technical users:** This is self-hosted software that requires a VPS, basic command-line familiarity, and your own API keys. If terms like "SSH," "systemd," or "environment variables" are unfamiliar, consider asking a technical friend to help with the initial setup. The agent itself is designed to be voice-driven and simple — getting it running is the hardest part.

---

## What Is Korvin?

Korvin is an AI agent you install and run yourself. It listens, thinks, remembers, and acts — through Telegram, voice, or any channel you configure.

Most AI assistants are cloud services. Your conversations live on someone else's server. Your data trains someone else's model. You pay monthly for access you do not control.

Korvin is different. Every message stays on your machine. Every setting is a config file you can read and edit. If you want to switch from DeepSeek to Claude to a local Llama model, you change one line. No migration. No support ticket. No vendor permission required.

This is what "no lock-in" means in practice.

---

## What Korvin Does

- **Talks to you by voice** — Whisper tiny.en for speech-to-text (~2s response), Kokoro TTS for audio replies
- **Answers questions and runs research** — web search; document drafting and inbox summarization are planned, not yet live
- **Runs security scans** — VirusTotal lookup for URLs, IPs, and file hashes; weekly Lynis system audit
- **Researches CVEs on demand** — `/patch openssl` returns severity scores and patch recommendations. Output is AI-generated and must be verified against official sources before acting on it.
- **Works through Telegram** — WhatsApp, Discord, Signal coming
- **Remembers your conversations** — persistent SQLite memory with configurable limits
- **Manages its own memory** — sliding window, summarization, or hard stop strategies
- **Switches models instantly** — tap a model on the dashboard, the agent picks it up on the next message
- **Runs on anything** — $5 VPS, local GPU machine, cloud VM, Raspberry Pi

---

## Voice Optimization

Korvin uses Whisper for speech-to-text. By default it loads `tiny.en` — an English-only model that is 4x faster and uses 75% less RAM than the standard `base` model.

| Model | Size | Response time | Best for |
|-------|------|---------------|----------|
| `tiny.en` | 74 MB | ~2s | Voice commands, fast interaction |
| `base` | 145 MB | ~8s | Longer dictation |
| `small` | 466 MB | ~20s | Best accuracy |

`tiny.en` is the default because most Korvin interactions are short voice commands. It works on a $5 VPS or a Raspberry Pi without GPU. The model pre-loads at bot startup so even the first voice message responds in ~2 seconds instead of waiting for a cold start.

To switch models, change the model name in the `transcribe` function inside `src/openclaw/telegram-bot.js`.

---

## Local Voice Client (Windows) — Experimental

Korvin includes an optional local voice client for Windows (`korvin-voice.py`). This is a
separate tool from the core agent — it is not part of the npm package and requires its own
setup. It is intended for users who want a hands-free desktop experience: speak naturally,
Korvin listens, thinks, and talks back.

**What it does in plain terms:**

Instead of typing into Telegram or a browser, you speak out loud. The client:
1. Listens for a wake phrase (configurable, default: "Hey Korvin")
2. Records what you say after the wake phrase
3. Sends the audio to your VPS for transcription
4. Gets a response from your AI model
5. Speaks the response back through your speakers

**Examples of what this looks like in practice:**

- *Beginner:* You say "Hey Korvin, what is the weather like in my city?" — Korvin
  responds in a natural voice through your speakers, no keyboard needed.
- *Intermediate:* You say "Hey Korvin, research recent news about AI regulation" —
  Korvin processes the request and reads back a summary.
- *- *Advanced:* You say "Hey Korvin, what did we discuss        yesterday?" — Korvin searches its conversation memory and summarizes the relevant context verbally.
  what you find" — Korvin executes the command, waits for results, and reports back verbally.

**Requirements:**
- Windows 10 or 11
- Python 3.11 specifically (3.12 and 3.14 have compatibility issues with the audio stack)
- A running KORVIN VPS with the dashboard and STT endpoint active
- Cloudflare Service Token (if your dashboard is behind Cloudflare Access)

**Setup (one time):**

```bash
py -3.11 -m venv C:\korvin-voice-env
C:\korvin-voice-env\Scripts\Activate.ps1
pip install openwakeword sounddevice numpy pyaudio requests keyboard pyttsx3
python korvin-voice.py
```

The client will prompt you for your API key and Cloudflare credentials on first run and
save them locally in `korvin_voice_config.json`. Your credentials are never committed to git.

**Push-to-talk alternative (recommended for most users):**

If the wake word setup feels complex, use `Ctrl+Space` instead. Press it, speak, release.
No Python install, no venv, no model downloads. This works out of the box and is the
recommended default for most users.

---

### ⚠️ Privacy and Security Notice — Local Voice Client

Read this before running the voice client, especially in a professional or enterprise
environment.

**Continuous microphone access:**

When the voice client is running, it listens to your microphone continuously for as long
as the process is active. This is how wake word detection works. Audio is processed
entirely on your local machine by the openWakeWord library — nothing is transmitted
anywhere during the listening phase.

Once the wake phrase is detected, your speech is recorded and sent to your VPS for
transcription. The transcribed text is then sent to whichever AI model you have configured.

**What this means depending on your setup:**

- *Self-hosted model (local LLM via Ollama or similar):* Your audio goes to your VPS,
  gets transcribed locally, and the text is processed by a model running on your own
  hardware. Nothing leaves your infrastructure.

- *Third-party AI provider:* Your transcribed text is sent to that provider's servers
  for processing. This is equivalent to typing into their API — the content of your
  request is transmitted to and processed by their infrastructure, subject to their
  data retention and privacy policies. Review each provider's terms before using Korvin
  with sensitive information.

- *Hybrid setup (self-hosted VPS + third-party LLM):* Audio transcription stays on your
  VPS. The resulting text leaves your infrastructure when it reaches the LLM provider.

**Even with a fully self-hosted setup, consider these risks:**

- Your VPS provider has physical access to the server. A compromised VPS means a
  compromised conversation history.
- SQLite memory stores conversations in plaintext. Anyone with VPS access can read
  your full conversation history.
- The voice client runs as your Windows user. Any process on your machine with
  sufficient privileges could access the microphone at the same time.
- If the wake word client is running during meetings, calls, or sensitive conversations,
  the microphone is open — even when not triggered. Audio does not leave your machine
  during the listening phase, but the microphone is active.

**Recommended practices:**

- Stop the voice client when not in use (`Ctrl+C` in the terminal)
- Never run the voice client during confidential meetings or legal proceedings
- If using a third-party LLM provider, avoid speaking personally identifiable
  information, financial data, or confidential business details through the voice client
- Review your LLM provider's data retention policy before any production use
- Use a self-hosted model if privacy is a strict requirement

**Audio handling:** Korvin does not store audio files. Audio is converted to text on
your VPS and discarded immediately. The temporary file created during transcription is
deleted after each use. Only the transcribed text enters conversation memory.

---

## Commands

Korvin responds to these commands in Telegram:

| Command | Risk | Description |
|---------|------|-------------|
| `/scan <target>` | HIGH | VirusTotal lookup for a URL, IP, or file hash |
| `/scan system` | HIGH | Display the latest Lynis security audit report |
| `/patch <package>` | HIGH | LLM CVE research -- severity scores and patch recommendations (verify against official sources) |
| `/status` | — | VPS health — CPU, RAM, disk, uptime |
| `/log` | — | Recent Korvin activity |
| `/confirm <hash>` | — | Approve a pending HIGH-risk action |
| `/cancel <hash>` | — | Cancel a pending HIGH-risk action |
| `/pending` | — | List all active pending confirmations |
| `/help` | — | Command menu |
| `/brief` | — | Daily briefing summary |
| `/grill` | — | Stress-test a claim or argument |
| `Research <topic>` | — | Web research on any topic |

> ⚠️ **Important:** `/scan` and `/patch` are intended for technical users only. `/patch` output is AI-generated and must be verified against official sources (NVD, vendor advisories) before acting on it. A clean `/scan` result means no engine flagged the target at scan time — it does not guarantee safety. Never act on either command's output without independent verification.

**Why confirmation gates exist:**
Every HIGH-risk command requires explicit `/confirm <hash>` before executing. This is an architectural constraint — not a prompt suggestion. The agent cannot bypass it. Pending actions expire after 5 minutes automatically.

This design exists because autonomous agents without human checkpoints have caused irreversible data loss in documented production incidents. A confirmation gate is the difference between the agent tried and the agent did.

**Example `/scan` flow:**

```
You:    /scan google.com
Korvin: 🔐 Confirmation Required — Action: scan — Risk: HIGH
        Reply /confirm a1b2c3d4 to execute

You:    /confirm a1b2c3d4
Korvin: 🔍 Scanning `google.com`... (url)

        🟢 VirusTotal — `google.com`
        Type: URL
        • Malicious:  0/92 engines
        • Suspicious: 0/92 engines
        • Harmless:   66 | Undetected: 26
        • Last submission: 2026-04-30
        ✅ No threats detected.
```

**VirusTotal:** Korvin checks what is already known across 90+ engines. It never submits anything on your behalf. A free API key is required — get one at [virustotal.com](https://virustotal.com) and add it to `/etc/korvin.env` as `VIRUSTOTAL_API_KEY`. The free tier allows 500 lookups per day.

**Lynis:** `/scan system` reads a weekly security audit generated by a root cron job. The bot never runs Lynis directly — this preserves the privilege boundary. Install Lynis first:

```bash
apt-get install lynis

# Add the weekly cron job
echo "0 2 * * 0 root lynis audit system --quick > /home/korvin/korvin/data/lynis-report.txt 2>&1" > /etc/cron.d/lynis-audit
```

---

## Quick Start

**Install via npm:**

```bash
npm install -g @nosistech/korvin
```

> **Note:** This installs the Korvin JS SDK surface only -- not the full agent. The npm package does not include the Python dashboard, voice stack, LiteLLM proxy, or systemd services. To run the full agent, follow the Manual Install steps below. The `korvin init` setup wizard is on the roadmap and not yet available.

**Manual Install (full control):**

```bash
# 1. Clone the repo
git clone https://github.com/nosistech/korvin.git
cd korvin
# IMPORTANT: Several internal paths are hardcoded to /home/korvin/korvin
# Clone into that exact path or update the paths in gateway.js, telegram-bot.js, and src/dashboard/main.py before running

# 2. Install Node dependencies
npm install

# 3. Create Python virtual environment for dashboard and voice
python3 -m venv venv
source venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Configure
cp config.example.json config.json
nano config.json
```

Edit `config.json`:

```json
{
  "telegramToken": "YOUR_TELEGRAM_BOT_TOKEN",
  "memory_limit": 46,
  "max_tokens": 128000,
  "memory_strategy": "sliding_window",
  "summarizer_url": "http://localhost:4000/v1/chat/completions",
  "summarizer_model": "YOUR_MODEL_NAME",
  "summarizer_fallback": "sliding_window", // planned -- not yet wired in code
  "litellm_master_key": "YOUR_LITELLM_MASTER_KEY"
}
```

```bash
# 6. Start the bot
node src/openclaw/telegram-bot.js

# 7. Start the dashboard
uvicorn src.dashboard.main:app --host 127.0.0.1 --port 3002
```

---

## Running as a Service (Recommended)

Run both the bot and dashboard as systemd services so they survive reboots.

**Create a dedicated system user:**

```bash
useradd --system --create-home --home-dir /home/korvin \
  --shell /bin/bash --comment "KORVIN service account" korvin

chown -R korvin:korvin /path/to/korvin
```

**Bot service** — `/etc/systemd/system/korvin.service`:

```ini
[Unit]
Description=KORVIN Personal AI Agent
After=network.target

[Service]
Type=simple
User=korvin
Group=korvin
WorkingDirectory=/home/korvin/korvin
ExecStart=/usr/bin/node src/openclaw/telegram-bot.js
Restart=on-failure
RestartSec=10
EnvironmentFile=/etc/korvin.env

[Install]
WantedBy=multi-user.target
```

**Dashboard service** — `/etc/systemd/system/korvin-dashboard.service`:

```ini
[Unit]
Description=KORVIN Dashboard
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
EnvironmentFile=/etc/korvin.env
User=korvin
Group=korvin
WorkingDirectory=/home/korvin/korvin
ExecStart=/home/korvin/korvin/venv/bin/uvicorn src.dashboard.main:app --host 127.0.0.1 --port 3002
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable korvin korvin-dashboard
systemctl start korvin korvin-dashboard
```

**Environment file** — `/etc/korvin.env` (chmod 600, never committed to git):

```
KORVIN_API_KEY=your_dashboard_api_key
VIRUSTOTAL_API_KEY=your_virustotal_key
LITELLM_MASTER_KEY=your_litellm_master_key
```

---

## Dashboard Architecture

Korvin runs two separate dashboard stacks:

**Express dashboard (port 3000)** -- embedded inside the Telegram bot process. Starts automatically when the bot starts. Exposes a single internal endpoint (`GET /api/system`) that the `/status` command uses to read CPU, RAM, disk, and uptime. Never exposed externally. No auth required -- loopback only.

**FastAPI dashboard (port 3002)** -- a separate Python process managed by `korvin-dashboard.service`. This is the full web UI at `dashboard.korvin.cloud` -- chat, memory browser, model switcher, logs, token usage, settings. Requires `X-Korvin-Key` on write endpoints. Exposed via Cloudflare Tunnel with Access OTP.

The two stacks are independent. The bot runs without the FastAPI dashboard. The FastAPI dashboard runs without the bot. Port 3000 is internal only. Port 3002 is the one you expose through Cloudflare.

---

## Exposing the Dashboard

The dashboard runs on `127.0.0.1:3002` — loopback only, never exposed directly. Use Cloudflare Tunnel to reach it from anywhere:

```bash
cloudflared tunnel create korvin-dashboard
cloudflared tunnel route dns korvin-dashboard dashboard.yourdomain.com
```

Then add Cloudflare Access (zero-trust OTP or SSO) so only you can reach it. This gives you two layers: Cloudflare Access at the edge, API key auth on write endpoints inside the app.

---

## LiteLLM Setup

Korvin routes all LLM calls through [LiteLLM](https://github.com/BerriAI/litellm) — a proxy that makes every model provider look identical to the agent.

```bash
pip install litellm
```

Create `/root/litellm_config.yaml`:

```yaml
model_list:
  - model_name: your-model-name
    litellm_params:
      model: openai/your-model-name
      api_base: https://api.yourprovider.com/v1
      api_key: YOUR_PROVIDER_API_KEY

general_settings:
  master_key: YOUR_MASTER_KEY
  drop_params: true
```

**LiteLLM service** — `/etc/systemd/system/litellm.service`:

```ini
[Unit]
Description=LiteLLM Proxy
After=network.target

[Service]
User=root
WorkingDirectory=/root
ExecStart=/usr/local/bin/litellm --config /root/litellm_config.yaml --port 4000 --host 127.0.0.1
Restart=always
RestartSec=5
EnvironmentFile=/etc/korvin.env

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable litellm
systemctl start litellm
```

Always bind LiteLLM to `127.0.0.1`. Verify:

```bash
ss -tlnp | grep 4000
# Expected: 127.0.0.1:4000 — never 0.0.0.0
```

---

## Model Switcher

The dashboard Settings tab lets you swap the active AI model with one tap — no restart, no config file edits.

How it works:

```
Dashboard Settings → select model → writes active_model.txt
Gateway (gateway.js) → reads file on every message → sends model name to LiteLLM
LiteLLM → routes to the correct provider
```

The switch is instant. The gateway picks it up on the next message.

To add a new model: add it to `MODEL_LABELS` and `MODEL_WHITELIST` in `src/dashboard/main.py`, add it to `litellm_config.yaml` with its API key, and the dashboard builds the buttons automatically.

---

## Memory Architecture

Korvin stores every conversation in a local SQLite database and manages growth automatically.

**Sliding window (default)** — oldest messages drop off as new ones arrive. The agent never stops. Choose this when you want zero interruptions.

**Summarize** — when messages hit the limit, Korvin summarizes the oldest half using your configured LLM, stores it as a single entry, and deletes the originals. You keep the meaning without keeping every word. If summarization fails, it falls back to sliding window automatically.

**Hard stop** — new messages are rejected when the limit is hit until you manually clear memory. Choose this only if you want full manual control and can tolerate the agent going silent.

Configure in `config.json`:

```json
{
  "memory_limit": 46,
  "max_tokens": 128000,
  "memory_strategy": "sliding_window",
  "summarizer_url": "http://localhost:4000/v1/chat/completions",
  "summarizer_model": "your-model-name"
}
```

> **Note:** `memory_limit` in `config.example.json` is 46. If `config.json` is missing or the key is absent, the code defaults to 100. Set this explicitly in your config.

Token limits by model:

| Model | Token limit |
|-------|-------------|
| Llama 3 7B local | 8,000 |
| Mistral 7B local | 32,000 |
| DeepSeek V4 / GPT-4o | 128,000 |
| Claude Sonnet / Opus | 200,000 |
| Gemini 2.5 Pro | 1,000,000 |

---

## Dashboard API

All endpoints on `http://127.0.0.1:3002`.

**Public (no auth required):**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Agent status and version |
| GET | `/api/system` | CPU, RAM, disk usage |
| GET | `/api/memory/recent` | Recent conversation messages |
| GET | `/api/memory/context-window` | Token and message usage |
| GET | `/api/memory/limit` | Current memory config |
| GET | `/api/killswitch` | Current killswitch state |
| GET | `/api/health` | Service health check |
| GET | `/api/active-model` | Currently active model |
| GET | `/api/models` | All configured models |

**Protected (require `X-Korvin-Key` header):**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/logs` | Sanitized system logs |
| POST | `/api/killswitch` | Toggle read-only mode |
| POST | `/api/memory/limit` | Save memory configuration |
| POST | `/api/memory/prune` | Manually enforce memory limit |
| POST | `/api/switch-model` | Switch the active model |
| POST | `/api/chat` | Send a message via dashboard chat |
| GET | `/api/chat/history` | Retrieve dashboard chat history |
| POST | `/api/chat-timeout` | Set chat timeout value |
| POST | `/api/token-warning-threshold` | Set token warning threshold |
| GET | `/api/token-usage` | Token usage stats |
| POST | `/api/token-rates` | Set token rate config |
| POST | `/api/stt` | Submit audio for speech-to-text transcription |

**Example calls:**

```bash
# System resources
curl http://127.0.0.1:3002/api/system

# Switch model
curl -X POST http://127.0.0.1:3002/api/switch-model \
  -H "Content-Type: application/json" \
  -H "X-Korvin-Key: YOUR_API_KEY" \
  -d '{"model": "deepseek-v4-pro"}'

# Toggle killswitch
curl -X POST http://127.0.0.1:3002/api/killswitch \
  -H "Content-Type: application/json" \
  -H "X-Korvin-Key: YOUR_API_KEY" \
  -d '{"enabled": true}'
```

---

## Security Design

**Threat model:**

Korvin is designed for single-operator self-hosted deployment. Primary threats and mitigations:

- Unauthorized dashboard access — Cloudflare Access OTP + API key on write endpoints
- Services exposed on public IP — all services bound to `127.0.0.1` only
- Secret leakage — `/etc/korvin.env` chmod 600, never committed; `config.json` gitignored
- Log data exposure — server-side sanitization strips stack traces and file paths
- Prompt injection — `sanitizer.js` blocks malicious patterns before reaching the LLM
- Destructive autonomous actions — confirmation gate requires explicit `/confirm` for all HIGH-risk commands

**Privilege separation:**

The bot and dashboard both run as the `korvin` system user — not root. LiteLLM runs as root because it requires access to `/root/litellm_config.yaml`. Future versions will address this.

**Port security checklist:**

```bash
ss -tlnp | grep -E "3000|3002|4000"
# All must show 127.0.0.1 -- never 0.0.0.0
```

**Never committed to git:**

```
config.json        # Telegram token, LiteLLM master key
data/              # SQLite memory database
logs/              # Runtime logs
*.wav / *.ogg      # Voice recordings
/etc/korvin.env    # All API keys
KORVIN.local.md    # Your personal agent config (identity, tone, rules)
```

---

## Project Structure

```
korvin/
├── src/
│   ├── openclaw/
│   │   ├── gateway.js              # LLM gateway, model switching
│   │   └── telegram-bot.js         # Telegram integration, voice, command routing
│   ├── commands/
│   │   ├── scan.js                 # /scan — VirusTotal + Lynis
│   │   └── patch.js                # /patch — LLM CVE research (verify against official sources)
│   ├── middleware/
│   │   ├── confirmation-gate.js    # /confirm guard for HIGH-risk actions
│   │   ├── sanitizer.js            # Prompt injection blocker
│   │   └── skill-contract.js       # Structured skill return types (not yet wired)
│   ├── security/
│   │   └── defender.js             # Content sanitization (wired)
│   ├── dashboard/
│   │   ├── main.py                 # FastAPI endpoints
│   │   └── static/index.html       # Dashboard UI
│   ├── hermes/
│   │   └── memory.py               # SQLite memory + strategy enforcement
│   ├── skills/
│   │   ├── activity-log.js         # Activity logging
│   │   └── research.js             # Web research skill
│   └── voice/
│       └── voice.py                # Kokoro TTS
├── data/                           # SQLite DB, active_model.txt (gitignored)
├── docs/                           # Extended documentation
├── config.json                     # Your config (gitignored)
├── config.example.json             # Template (committed)
├── package.json
└── README.md
```

---

## Roadmap

- [ ] `korvin init` setup wizard via npm
- [ ] WhatsApp, Discord, Signal channels
- [ ] RAG over local documents
- [ ] Multi-agent orchestration
- [ ] Wake word detection via Porcupine

---

## Contributing

See `CONTRIBUTORS.md` for guidelines.

## Attributions

See `ATTRIBUTIONS.md` for third-party licenses.

## Security

See `SECURITY.md` for responsible disclosure policy.

## License

MIT — see `LICENSE.md` for full details.

MIT License — free for personal, educational, and commercial use. Copies of this software must include the copyright notice and license text. KORVIN is provided as-is with no warranty. See `LICENSE.md` for full terms and third-party attributions.

---

*Built by NosisTech — Cloud  · AI *
