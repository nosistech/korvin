import os, sqlite3, subprocess
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

app = FastAPI(title="Korvin Dashboard")
app.mount("/static", StaticFiles(directory="/root/korvin/src/dashboard/static"), name="static")

DB_PATH = "/root/korvin/data/memory.db"

@app.get("/", response_class=HTMLResponse)
def root():
    with open("/root/korvin/src/dashboard/static/index.html") as f:
        return f.read()

@app.get("/api/status")
def status():
    return {"korvin": "online", "version": "0.1.0", "sandbox": "docker", "memory": "sqlite"}

@app.get("/api/system")
def system_info():
    try:
        disk = subprocess.check_output("df -h / | tail -1", shell=True).decode().split()
        mem = subprocess.check_output("free -m | grep Mem", shell=True).decode().split()
        return {
            "disk_used": disk[2], "disk_free": disk[3], "disk_pct": disk[4],
            "mem_total_mb": mem[1], "mem_used_mb": mem[2], "mem_free_mb": mem[3],
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
