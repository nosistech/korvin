import os, sqlite3, subprocess, re, json, time
from datetime import datetime
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

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
    return {"korvin": "online", "version": "0.1.0", "sandbox": "docker", "memory": "sqlite"}

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
def recent_memory(chat_id: str = "8023887825", limit: int = 20):
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
def context_window(chat_id: str = "8023887825", limit: int = 10, max_tokens: int = 128000):
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
    chat_id: str = "8023887825"

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