import os, sqlite3, subprocess, re, json, time
from datetime import datetime, date
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from collections import defaultdict
import requests

app = FastAPI(title="Korvin Dashboard")
app.mount("/static", StaticFiles(directory="/home/korvin/korvin/src/dashboard/static"), name="static")

DB_PATH = "/home/korvin/korvin/data/memory.db"
KILLSWITCH_FLAG = "/home/korvin/korvin/data/killswitch.flag"

def require_key(x_korvin_key: Optional[str] = Header(default=None)):
    api_key = os.environ.get("KORVIN_API_KEY", "")
    if not api_key or x_korvin_key != api_key:
        raise HTTPException(status_code=403, detail="Forbidden")

LOG_SANITIZE = re.compile(
    r'(Traceback \(most recent call last\)|File "/.*?"|^\s+.*\.py.*$)',
    re.MULTILINE
)

# ── Public endpoints ────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root():
    with open("/home/korvin/korvin/src/dashboard/static/index.html") as f:
        html = f.read()
    api_key = os.environ.get("KORVIN_API_KEY", "")
    html = html.replace("__KORVIN_API_KEY__", api_key)
    return HTMLResponse(content=html)

@app.get("/api/status")
def status():
    return {"korvin": "online", "version": "0.1.0", "memory": "sqlite"}

@app.get("/api/health")
def health_check():
    health = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "bot": "unknown",
        "litellm": "unknown",
        "memory_total": 0,
        "last_activity": None,
        "backup_last": None,
        "backup_hours": None,
    }

    # Bot status (systemd)
    try:
        r = subprocess.run(["systemctl", "is-active", "korvin"], capture_output=True, text=True, timeout=3)
        health["bot"] = "running" if r.stdout.strip() == "active" else "stopped"
    except Exception:
        pass

    # LiteLLM proxy
    try:
        key = os.environ.get("LITELLM_MASTER_KEY", "")
        resp = requests.get("http://127.0.0.1:4000/health",
                           headers={"Authorization": f"Bearer {key}"}, timeout=3)
        health["litellm"] = "reachable" if resp.status_code == 200 else "error"
    except Exception:
        health["litellm"] = "unreachable"

    # Memory database
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            last = conn.execute("SELECT MAX(timestamp) FROM messages").fetchone()[0]
            health["memory_total"] = count
            health["last_activity"] = last
            conn.close()
        except Exception:
            pass

    # Backup age
    backup_dir = "/home/korvin/.backup-repo/snapshots"
    if os.path.exists(backup_dir):
        try:
            dirs = sorted([d for d in os.listdir(backup_dir) if os.path.isdir(os.path.join(backup_dir, d))])
            if dirs:
                health["backup_last"] = dirs[-1]
                parts = dirs[-1].split("_", 1)
                last_ts = parts[0] + "T" + parts[1].replace("-", ":")
                age = datetime.utcnow() - datetime.fromisoformat(last_ts)
                health["backup_hours"] = round(age.total_seconds() / 3600, 1)
        except Exception:
            pass

    # Overall status
    if health["bot"] != "running" or health["litellm"] == "unreachable":
        health["status"] = "degraded"

    return health

@app.get("/api/system")
def system_info():
    try:
        disk = subprocess.check_output("df -h / | tail -1", shell=True).decode().split()
        mem = subprocess.check_output("free -m | grep Mem", shell=True).decode().split()
        cpu = subprocess.check_output("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'", shell=True).decode().strip()
        return {
            "disk_used": disk[2], "disk_free": disk[3], "disk_pct": disk[4],
            "mem_total_mb": mem[1], "mem_used_mb": mem[2], "mem_free_mb": mem[3],
            "cpu_pct": cpu,
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/memory/recent")
def recent_memory(chat_id: str = "", limit: int = 20):
    if not chat_id:
        chat_id = os.environ.get("KORVIN_CHAT_ID", "dashboard-chat")
    if not os.path.exists(DB_PATH):
        return {"messages": [], "error": "No memory DB found"}
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()
        conn.close()
        return {"messages": [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]}
    except Exception as e:
        return {"messages": [], "error": str(e)}

@app.get("/api/memory/context-window")
def context_window(chat_id: str = "", limit: int = 10, max_tokens: int = 128000):
    if not chat_id:
        chat_id = os.environ.get("KORVIN_CHAT_ID", "dashboard-chat")
    if not os.path.exists(DB_PATH):
        return {"messages_used": 0, "messages_limit": limit, "tokens_estimate": 0, "max_tokens": max_tokens, "pct_messages": 0, "pct_tokens": 0, "status": "ok"}
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()
        conn.close()
        total_chars = sum(len(r[1]) for r in rows)
        tokens_estimate = total_chars // 4
        pct_messages = round((len(rows) / limit) * 100, 1)
        pct_tokens = round((tokens_estimate / max_tokens) * 100, 2)
        return {
            "chat_id": chat_id,
            "messages_used": len(rows),
            "messages_limit": limit,
            "tokens_estimate": tokens_estimate,
            "max_tokens": max_tokens,
            "pct_messages": pct_messages,
            "pct_tokens": pct_tokens,
            "status": "critical" if pct_messages >= 80 else "warning" if pct_messages >= 60 else "ok"
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/killswitch")
def killswitch_status():
    active = os.path.exists(KILLSWITCH_FLAG)
    return {"killswitch": active, "mode": "read_only" if active else "normal"}

# ── Protected endpoints ─────────────────────────────────────────────

@app.get("/api/logs", dependencies=[Depends(require_key)])
def get_logs(lines: int = 100):
    try:
        output = subprocess.check_output(
            ["journalctl", "-u", "korvin-dashboard", f"-n{lines}", "--no-pager"],
            stderr=subprocess.STDOUT
        ).decode()
        sanitized = LOG_SANITIZE.sub("[sanitized]", output)
        return {"lines": sanitized.strip().splitlines()}
    except Exception as e:
        return {"lines": [], "error": str(e)}

class KillswitchRequest(BaseModel):
    enabled: bool

@app.post("/api/killswitch", dependencies=[Depends(require_key)])
def killswitch_set(body: KillswitchRequest):
    if body.enabled:
        open(KILLSWITCH_FLAG, "w").close()
    else:
        if os.path.exists(KILLSWITCH_FLAG):
            os.remove(KILLSWITCH_FLAG)
    active = os.path.exists(KILLSWITCH_FLAG)
    return {"killswitch": active, "mode": "read_only" if active else "normal"}

CONFIG_PATH = "/home/korvin/korvin/config.json"

def _read_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def _write_config(updates: dict):
    config = _read_config()
    config.update(updates)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

ACTIVE_MODEL_PATH = "/home/korvin/korvin/data/active_model.txt"

MODEL_LABELS = {
    "deepseek-v4-pro": "DeepSeek V4 Pro",
    "deepseek-v4-flash": "DeepSeek V4 Flash",
    "gemini-flash": "Gemini Flash",
    "ollama-qwen": "Local — Qwen 2.5",
    "ollama-deepseek-coder": "Local — DeepSeek Coder",
}

MODEL_WHITELIST = {
    "deepseek-v4-pro":      "openai/deepseek-v4-pro",
    "deepseek-v4-flash":    "openai/deepseek-v4-flash",
    "gemini-flash":         "gemini/gemini-2.5-flash",
    "ollama-qwen":          "ollama/qwen2.5:7b",
    "ollama-deepseek-coder": "ollama/deepseek-coder:6.7b",
}

def _read_active_model():
    try:
        with open(ACTIVE_MODEL_PATH) as f:
            return f.read().strip()
    except Exception:
        return "deepseek-v4-pro"

def _write_active_model(slug: str):
    os.makedirs(os.path.dirname(ACTIVE_MODEL_PATH), exist_ok=True)
    with open(ACTIVE_MODEL_PATH, "w") as f:
        f.write(slug)

@app.get("/api/memory/limit")
def get_memory_limit():
    config = _read_config()
    return {
        "memory_limit": config.get("memory_limit", 100),
        "max_tokens": config.get("max_tokens", 128000),
        "memory_strategy": config.get("memory_strategy", "sliding_window"),
        "summarizer_url": config.get("summarizer_url", "http://localhost:4000/v1/chat/completions"),
        "summarizer_model": config.get("summarizer_model", "deepseek-v4-flash")
    }

class MemoryLimitRequest(BaseModel):
    summarizer_url: str = "http://localhost:4000/v1/chat/completions"
    summarizer_model: str = "deepseek-v4-flash"
    memory_limit: int
    max_tokens: int
    memory_strategy: str = "sliding_window"

@app.post("/api/memory/limit", dependencies=[Depends(require_key)])
def set_memory_limit(body: MemoryLimitRequest):
    if body.memory_limit < 1:
        raise HTTPException(status_code=400, detail="memory_limit must be at least 1")
    if body.max_tokens < 1000:
        raise HTTPException(status_code=400, detail="max_tokens must be at least 1000")
    if body.memory_strategy not in ["sliding_window", "hard_stop", "summarize"]:
        raise HTTPException(status_code=400, detail="Invalid memory_strategy")
    _write_config({
        "summarizer_url": body.summarizer_url,
        "summarizer_model": body.summarizer_model,
        "memory_limit": body.memory_limit,
        "max_tokens": body.max_tokens,
        "memory_strategy": body.memory_strategy
    })
    return {"saved": True, "summarizer_url": body.summarizer_url, "summarizer_model": body.summarizer_model, "memory_limit": body.memory_limit, "max_tokens": body.max_tokens, "memory_strategy": body.memory_strategy}

class PruneRequest(BaseModel):
    chat_id: str = ""

@app.post("/api/memory/prune", dependencies=[Depends(require_key)])
def prune_memory(body: PruneRequest):
    from src.hermes.memory import prune
    config = _read_config()
    limit = config.get("memory_limit", 100)
    pruned = prune(body.chat_id, limit)
    return {"pruned": pruned, "limit": limit, "chat_id": body.chat_id}

@app.get("/api/active-model")
def get_active_model():
    slug = _read_active_model()
    model_string = MODEL_WHITELIST.get(slug, "unknown")
    return {"active_model": slug, "model_string": model_string}

class SwitchModelRequest(BaseModel):
    model: str

@app.post("/api/switch-model", dependencies=[Depends(require_key)])
def switch_model(body: SwitchModelRequest):
    slug = body.model.strip()
    if slug not in MODEL_WHITELIST:
        raise HTTPException(status_code=400, detail=f"Model '{slug}' not in whitelist")
    previous = _read_active_model()
    try:
        _write_active_model(slug)
        return {
            "success": True,
            "active_model": slug,
            "model_string": MODEL_WHITELIST[slug],
            "switched_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        _write_active_model(previous)
        raise HTTPException(status_code=500, detail=f"Switch failed: {str(e)}. Rolled back to {previous}.")

@app.get("/api/models")
def get_models():
    models = []
    for slug, model_string in MODEL_WHITELIST.items():
        models.append({
            "slug": slug,
            "label": MODEL_LABELS.get(slug, slug),
            "model_string": model_string
        })
    return {"models": models, "active": _read_active_model()}

# ── Token Tracking ─────────────────────────────────────────────────────
TOKEN_USAGE_PATH = "/home/korvin/korvin/data/token_usage.json"
TOKEN_RATES_PATH = "/home/korvin/korvin/data/token_rates.json"

DEFAULT_RATES = {
    "deepseek-v4-pro": 0.27,
    "deepseek-v4-flash": 0.07,
    "gemini-flash": 0.15,
    "ollama-qwen": 0.0,
    "ollama-deepseek-coder": 0.0,
}

def _read_token_usage():
    try:
        with open(TOKEN_USAGE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def _add_token_usage(model: str, tokens: int):
    today = date.today().isoformat()
    usage = _read_token_usage()
    if today not in usage:
        usage[today] = {}
    day = usage[today]
    if model not in day:
        day[model] = {"tokens": 0}
    day[model]["tokens"] += tokens
    day["total_tokens"] = day.get("total_tokens", 0) + tokens
    with open(TOKEN_USAGE_PATH, "w") as f:
        json.dump(usage, f)

def _read_token_rates():
    try:
        with open(TOKEN_RATES_PATH) as f:
            return json.load(f)
    except Exception:
        return dict(DEFAULT_RATES)

def _write_token_rates(rates: dict):
    os.makedirs(os.path.dirname(TOKEN_RATES_PATH), exist_ok=True)
    with open(TOKEN_RATES_PATH, "w") as f:
        json.dump(rates, f)

# ── Telegram forwarding ────────────────────────────────────────────────
def _telegram_send(chat_id: str, text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5
        )
    except Exception:
        pass

# ── Chat ────────────────────────────────────────────────────────────────
CHAT_RATE_LIMIT_WINDOW = 60          # 1 minute
CHAT_RATE_LIMIT_MAX    = 10          # max requests per window
_chat_ratelimit: dict[str, list[float]] = defaultdict(list)

def _check_chat_rate_limit(session_id: str):
    now = time.time()
    window = CHAT_RATE_LIMIT_WINDOW
    timestamps = _chat_ratelimit[session_id]
    _chat_ratelimit[session_id] = [t for t in timestamps if now - t < window]
    if len(_chat_ratelimit[session_id]) >= CHAT_RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.")
    _chat_ratelimit[session_id].append(now)

class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None

@app.post("/api/chat", dependencies=[Depends(require_key)])
def chat(body: ChatRequest):
    chat_id = body.chat_id or os.environ.get("KORVIN_CHAT_ID", "dashboard-chat")
    _check_chat_rate_limit(chat_id)

    messages = [{
        "role": "system",
        "content": (
            "You are Korvin, a self-hosted personal AI agent. "
            "You are helpful, concise, and warm. "
            "Respond in English. You are speaking through a dashboard chat interface."
        )
    }]

    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 20",
                (chat_id,)
            ).fetchall()
            conn.close()
            for r in reversed(rows):
                messages.append({"role": r[0], "content": r[1]})
        except Exception:
            pass

    messages.append({"role": "user", "content": body.message})

    litellm_url = "http://127.0.0.1:4000/v1/chat/completions"
    litellm_key = os.environ.get("LITELLM_MASTER_KEY", "")
    try:
        resp = requests.post(
            litellm_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {litellm_key}"
            },
            json={
                "model": "deepseek-v4-pro",
                "messages": messages,
                "temperature": 0.7,
                "stream": False
            },
            timeout=30
        )
        if not resp.ok:
            return {"reply": f"LiteLLM error: {resp.status_code}", "error": True}
        data = resp.json()
        reply = data["choices"][0]["message"]["content"]
        used = data.get("usage", {}).get("total_tokens", 0)
        if used > 5000:
            reply += f"\n\n💰 This response used {used:,} tokens. Use /brief in Telegram to reduce costs."
        # Track token usage
        usage = data.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)
        if total_tokens:
            try:
                _add_token_usage("deepseek-v4-pro", total_tokens)
            except Exception:
                pass
    except Exception as e:
        return {"reply": f"Error: {str(e)}", "error": True}

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO messages (chat_id, role, content, source, timestamp) VALUES (?,?,?,?,?)",
                     (chat_id, "user", body.message, "dashboard", datetime.utcnow().isoformat()))
        conn.execute("INSERT INTO messages (chat_id, role, content, source, timestamp) VALUES (?,?,?,?,?)",
                     (chat_id, "assistant", reply, "dashboard", datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass

    _telegram_send(chat_id, body.message)
    _telegram_send(chat_id, reply)

    return {"reply": reply}

@app.get("/api/chat/history", dependencies=[Depends(require_key)])
def chat_history(limit: int = 50):
    chat_id = os.environ.get("KORVIN_CHAT_ID", "dashboard-chat")
    if not os.path.exists(DB_PATH):
        return {"messages": []}
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT role, content, source, timestamp FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()
        conn.close()
        return {"messages": [{"role": r[0], "content": r[1], "source": r[2] or "telegram", "timestamp": r[3]} for r in reversed(rows)]}
    except Exception:
        return {"messages": []}

# ── Token Usage & Rates ────────────────────────────────────────────────

@app.get("/api/token-usage")
def token_usage():
    usage = _read_token_usage()
    rates = _read_token_rates()
    today = date.today().isoformat()
    today_data = usage.get(today, {})

    total_tokens_today = today_data.get("total_tokens", 0)
    cost_today = 0.0
    for model, data in today_data.items():
        if model == "total_tokens":
            continue
        rate = rates.get(model, 0)
        cost_today += (data.get("tokens", 0) / 1_000_000) * rate

    month_tokens = 0
    month_cost = 0.0
    for day_key, day_data in usage.items():
        if day_key.startswith(today[:7]):
            month_tokens += day_data.get("total_tokens", 0)
            for model, data in day_data.items():
                if model == "total_tokens":
                    continue
                rate = rates.get(model, 0)
                month_cost += (data.get("tokens", 0) / 1_000_000) * rate

    return {
        "today": {
            "tokens": total_tokens_today,
            "cost": round(cost_today, 6)
        },
        "month": {
            "tokens": month_tokens,
            "cost": round(month_cost, 6)
        }
    }

@app.get("/api/token-rates")
def token_rates():
    return {"rates": _read_token_rates()}

class TokenRatesRequest(BaseModel):
    rates: dict

@app.post("/api/token-rates", dependencies=[Depends(require_key)])
def save_token_rates(body: TokenRatesRequest):
    _write_token_rates(body.rates)
    return {"saved": True, "rates": body.rates}