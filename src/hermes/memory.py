#!/usr/bin/env python3
"""Hermes memory layer — SQLite with full-text search."""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'memory.db')

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
            content,
            content=conversations,
            tokenize='porter unicode61'
        )
    ''')
    conn.execute('''
        CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
            INSERT INTO conversations_fts(rowid, content) VALUES (new.id, new.content);
        END
    ''')
    conn.commit()
    conn.close()

def add_message(session_id, role, content):
    conn = get_db()
    timestamp = datetime.utcnow().isoformat()
    conn.execute(
        'INSERT INTO conversations (timestamp, session_id, role, content) VALUES (?, ?, ?, ?)',
        (timestamp, session_id, role, content)
    )
    conn.commit()
    conn.close()

def get_recent(session_id, limit=10):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM conversations WHERE session_id=? ORDER BY timestamp DESC LIMIT ?',
        (session_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

def search(query, limit=5):
    conn = get_db()
    rows = conn.execute(
        "SELECT c.* FROM conversations c JOIN conversations_fts f ON c.id = f.rowid "
        "WHERE conversations_fts MATCH ? ORDER BY rank LIMIT ?",
        (query, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

if __name__ == '__main__':
    init_db()
    add_message('test-session', 'user', 'Hello, do you remember me?')
    add_message('test-session', 'assistant', 'Yes, I do! We just met.')
    recent = get_recent('test-session')
    for msg in recent:
        print(f"{msg['role'].upper()}: {msg['content']}")
    print("Memory test passed!")
