# Korvin

**Self-hosted AI agent framework. Voice-first. Security-native. No lock-in.**

Korvin runs on your own machine or a $5 VPS. You bring your API keys. You own your data. No third party ever touches your messages, credentials, or billing.

---

## What Is Korvin?

Korvin is an AI agent you install and run yourself. It listens, thinks, remembers, and acts — through Telegram, voice, or any channel you configure.

Most AI assistants are cloud services. Your conversations live on someone else's server. Your data trains someone else's model. You pay monthly for access you don't control.

Korvin is different. Every message stays on your machine. Every setting is a config file you can read and edit. If you want to switch from DeepSeek to Claude to a local Llama model, you change one line. No migration. No support ticket. No vendor permission required.

This is what "no lock-in" means in practice.

---

## What Korvin Does

- **Talks to you by voice** — Whisper for speech-to-text, Kokoro TTS for responses
- **Answers questions and runs research** — web search, document drafting, inbox summarization
- **Works through Telegram** (WhatsApp, Discord, Signal coming)
- **Remembers your conversations** — persistent SQLite memory with configurable limits
- **Manages its own memory** — sliding window, summarization, or hard stop strategies
- **Monitors itself** — live dashboard at `dashboard.korvin.cloud` (or your own domain)
- **Self-patches against threats** — sandboxed OWASP monitoring
- **Runs on anything** — $5 VPS, local GPU machine, cloud VM, Raspberry Pi

---

## Quick Start

### Install via npm

```bash
npm install -g @nosistech/korvin
korvin init
```

> The setup wizard handles API keys, Telegram configuration, and service startup.

### Manual Install (Developer Setup)

For full control or active development:

```bash
# 1. Clone the repo
git clone https://github.com/nosistech/korvin.git
cd korvin

# 2. Create Python virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp config.example.json config.json
nano config.json
```

Edit `config.json` with your values:

```json
{
  "telegramToken": "YOUR_TELEGRAM_BOT_TOKEN",
  "memory_limit": 46,
  "max_tokens": 128000,
  "memory_strategy": "sliding_window",
  "summarizer_url": "http://localhost:4000/v1/chat/completions",
  "summarizer_model": "deepseek-v4-flash",
  "summarizer_fallback": "sliding_window",
  "litellm_master_key": "YOUR_LITELLM_MASTER_KEY"
}
```

```bash
# 5. Start the agent
python3 -m src.hermes.agent

# 6. Start the dashboard
uvicorn src.dashboard.main:app --host 127.0.0.1 --port 3002
```

---

## Dashboard Setup

The Korvin dashboard gives you a live view of your agent — system resources, memory, logs, and a kill switch.

### Run as a systemd service (recommended)

```bash
sudo nano /etc/systemd/system/korvin-dashboard.service
```

```ini
[Unit]
Description=Korvin Dashboard FastAPI
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
User=root
WorkingDirectory=/path/to/korvin
ExecStart=/path/to/korvin/venv/bin/uvicorn src.dashboard.main:app --host 127.0.0.1 --port 3002
Restart=always
RestartSec=5
EnvironmentFile=/etc/korvin.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable korvin-dashboard
sudo systemctl start korvin-dashboard
```

### API Key Setup

The dashboard uses a secret key to protect write endpoints. Generate one and store it:

```bash
# Generate key
API_KEY=$(openssl rand -hex 32)
echo "KORVIN_API_KEY=$API_KEY" > /etc/korvin.env
chmod 600 /etc/korvin.env

# Inject into dashboard HTML
source /etc/korvin.env
sed -i "s/__KORVIN_API_KEY__/$KORVIN_API_KEY/" src/dashboard/static/index.html
```

> **Important:** `index.html` ships with the placeholder `__KORVIN_API_KEY__`. You must run the `sed` injection after cloning. Store your key in a password manager — label it `KORVIN_DASHBOARD_API_KEY`.

### Expose via Cloudflare Tunnel (recommended)

```bash
cloudflared tunnel create korvin-dashboard
cloudflared tunnel route dns korvin-dashboard dashboard.yourdomain.com
```

Then lock it with Cloudflare Access (OTP or SSO) so only you can reach it.

---

## LiteLLM Setup

Korvin routes all LLM calls through [LiteLLM](https://github.com/BerriAI/litellm) — a proxy that translates any OpenAI-compatible API call to any model provider.

### Why LiteLLM?

Most agents hardcode their model endpoint. Switch providers and you rewrite code. LiteLLM means Korvin never knows or cares which model powers it — DeepSeek, Claude, Gemini, or a local Ollama model all look identical to the agent. Swap models by editing one config file.

### Install and configure

```bash
pip install litellm
nano /root/litellm_config.yaml
```

```yaml
model_list:
  - model_name: your-model
    litellm_params:
      model: openai/your-model-name
      api_base: https://api.yourprovider.com/v1
      api_key: YOUR_API_KEY

general_settings:
  master_key: YOUR_MASTER_KEY
  drop_params: true
```

### Run as a systemd service

```bash
sudo nano /etc/systemd/system/litellm.service
```

```ini
[Unit]
Description=LiteLLM Proxy
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
User=root
WorkingDirectory=/root
ExecStart=/usr/local/bin/litellm --config /root/litellm_config.yaml --port 4000 --host 127.0.0.1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable litellm
sudo systemctl start litellm
```

> **Security:** Always bind LiteLLM to `127.0.0.1`, never `0.0.0.0`. Verify with `ss -tlnp | grep 4000`.

---

## Memory Architecture

Korvin stores every conversation in a local SQLite database. When the database grows large, Korvin manages it automatically using the strategy you configure.

### Why per-install configuration?

A researcher running Korvin on a local GPU with an 8k context model needs a limit of 20 messages. A developer on a VPS with DeepSeek's 128k context can hold 200. There is no universal right answer — so Korvin stores the limit in `config.json` and each install is sovereign. No two installs need to agree.

### Memory strategies

#### Sliding Window (default)

When messages exceed the limit, the oldest messages are deleted automatically. New messages always come in; oldest always fall off. The agent never stops.

**Choose this when:** you want zero interruptions and don't need long-term context beyond your limit.

**Why we made this the default:** It is the simplest strategy that guarantees the agent keeps running under all conditions. Predictable, auditable, zero dependencies.

#### Summarize

When messages hit the limit, Korvin summarizes the oldest half using your configured LLM, stores the summary as a single `[SUMMARY]` entry, then deletes the originals. You keep the meaning without keeping every word.

**Choose this when:** you need long-term context and are willing to spend a small amount of API tokens or GPU time per summarization cycle.

**Why half the limit?** We evaluated three options: summarize everything, summarize a fixed batch, summarize half. Half scales correctly for every install size — a limit of 10 summarizes 5, a limit of 200 summarizes 100. Fixed batches either over-summarize on small installs or under-summarize on large ones.

**Fallback behavior:** If the summarization LLM call fails, Korvin retries once, then falls back to sliding window automatically. The agent never blocks. We chose retry-once because a single transient failure (network blip, model timeout) should not trigger a permanent fallback, but two consecutive failures almost certainly indicate a real problem worth working around gracefully.

#### Hard Stop

When messages hit the limit, new messages are rejected until the user manually clears memory. The agent pauses.

**Choose this when:** you want full manual control and can tolerate the agent going silent at the limit.

**We document this but do not recommend it as a default** because it creates invisible failure modes — the agent silently stops responding without any obvious error to the end user.

### Configuring memory

In `config.json`:

```json
{
  "memory_limit": 46,
  "max_tokens": 128000,
  "memory_strategy": "sliding_window",
  "summarizer_url": "http://localhost:4000/v1/chat/completions",
  "summarizer_model": "deepseek-v4-flash"
}
```

**`max_tokens` reference:**

| Model | Token limit |
|---|---|
| Llama 3 7B local | 8,000 |
| Mistral 7B local | 32,000 |
| DeepSeek V4 / GPT-4o | 128,000 |
| Claude Sonnet / Opus | 200,000 |
| Gemini 2.5 Pro | 1,000,000 |

Or configure via the dashboard — Memory tab → adjust slider → Apply to Agent.

---

## Dashboard API

All endpoints are on `http://127.0.0.1:3002`.

### Public endpoints (no auth required)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/status` | Agent status and version |
| GET | `/api/system` | CPU, RAM, disk usage |
| GET | `/api/memory/recent` | Recent conversation messages |
| GET | `/api/memory/context-window` | Token and message usage |
| GET | `/api/memory/limit` | Current memory config |
| GET | `/api/killswitch` | Current killswitch state |

### Protected endpoints (require `X-Korvin-Key` header)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/logs` | Sanitized system logs |
| POST | `/api/killswitch` | Toggle read-only mode |
| POST | `/api/memory/limit` | Save memory configuration |
| POST | `/api/memory/prune` | Manually enforce memory limit |

**Why only some endpoints are protected:**

Read-only endpoints like `/api/system` and `GET /api/killswitch` are safe to leave public — they expose no secrets and perform no actions. Write and sensitive-read endpoints are protected because they can change agent behavior or expose internal log data. This split means future monitoring integrations can poll public endpoints without needing the API key.

### Example API calls

```bash
# Check system resources
curl http://127.0.0.1:3002/api/system

# Get recent messages
curl http://127.0.0.1:3002/api/memory/recent?limit=20

# Toggle killswitch (protected)
curl -X POST http://127.0.0.1:3002/api/killswitch \
  -H "Content-Type: application/json" \
  -H "X-Korvin-Key: YOUR_API_KEY" \
  -d '{"enabled": true}'

# Set memory limit (protected)
curl -X POST http://127.0.0.1:3002/api/memory/limit \
  -H "Content-Type: application/json" \
  -H "X-Korvin-Key: YOUR_API_KEY" \
  -d '{
    "memory_limit": 46,
    "max_tokens": 128000,
    "memory_strategy": "summarize",
    "summarizer_url": "http://localhost:4000/v1/chat/completions",
    "summarizer_model": "deepseek-v4-flash"
  }'
```

---

## Security Design

### Threat model

Korvin is designed for single-operator self-hosted deployment. The primary threats are:

1. **Unauthorized dashboard access** — mitigated by Cloudflare Access + API key auth
2. **Exposed services on public IP** — mitigated by binding all services to `127.0.0.1`
3. **Secret leakage via config files** — mitigated by `.gitignore` on `config.json` and `data/`
4. **Log data exposure** — mitigated by server-side sanitization of stack traces and file paths

### What is never committed to git

```
config.json          # Telegram token, LiteLLM master key, summarizer config
data/                # SQLite memory database
logs/                # Runtime logs
*.wav / *.ogg        # Voice recordings
/etc/korvin.env      # Dashboard API key
```

### Port security checklist

```bash
# Verify all services are loopback-only
ss -tlnp | grep -E "3002|4000"
# Expected: 127.0.0.1 on both — never 0.0.0.0
```

---

## Model-Agnostic Design

Korvin never hardcodes a model. Every LLM call goes through a configurable endpoint stored in `config.json`. This means:

- Swap DeepSeek for Claude by editing one line
- Run entirely offline with Ollama — no API costs, no internet required
- Use a cheap fast model for summarization, expensive model for reasoning
- Each install is independent — a team of ten can run ten different model stacks

This is the same philosophy behind LiteLLM itself. Korvin extends it to the install level. The agent code never changes regardless of what model powers it. This is not an accident — it is a deliberate architectural constraint that makes Korvin future-proof by design.

---

## Project Structure

```
korvin/
├── src/
│   ├── hermes/
│   │   └── memory.py          # SQLite memory + strategy enforcement
│   ├── dashboard/
│   │   ├── main.py            # FastAPI endpoints
│   │   └── static/
│   │       └── index.html     # Dashboard UI
│   ├── openclaw/
│   │   └── gateway.js         # LLM gateway
│   └── skills/
│       ├── activity-log.js    # Activity logging
│       └── research.js        # Web research skill
├── data/                      # SQLite DB (gitignored)
├── docs/                      # Extended documentation
├── config.json                # Your config (gitignored)
├── config.example.json        # Template (committed)
├── package.json               # npm package definition
└── README.md
```

---

## Roadmap

- [ ] `korvin init` setup wizard via npm
- [ ] WhatsApp, Discord, Signal channels
- [x] Summarize memory strategy (Phase 2 complete)
- [ ] RAG over local documents
- [ ] Multi-agent orchestration
- [ ] Wake word detection ("Hey Korvin") via Porcupine
- [ ] Voz — bilingual TTS engine (XTTS v2)
- [ ] JARVIS V2 — full local AI stack

---

## Contributing

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for guidelines.

## Attributions

See [ATTRIBUTIONS.md](ATTRIBUTIONS.md) for third-party licenses.

## Security

See [SECURITY.md](SECURITY.md) for responsible disclosure policy.

## License

MIT — see [LICENSE.md](LICENSE.md) for full details.

---

*Built by [NosisTech](https://nosistech.com) — Cloud Security · AI Governance · Honduras*
