import sqlite3, os, datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '../../data/memory.db')

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )''')
    c.commit()
    return c

def save(chat_id, role, content):
    c = _conn()
    c.execute(
        'INSERT INTO messages (chat_id, role, content, timestamp) VALUES (?,?,?,?)',
        (str(chat_id), role, content, datetime.datetime.now(datetime.timezone.utc).isoformat())
    )
    c.commit()
    c.close()

def get_history(chat_id, limit=10):
    c = _conn()
    rows = c.execute(
        'SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?',
        (str(chat_id), limit)
    ).fetchall()
    c.close()
    return [{'role': r[0], 'content': r[1]} for r in reversed(rows)]

def clear(chat_id):
    c = _conn()
    c.execute('DELETE FROM messages WHERE chat_id=?', (str(chat_id),))
    c.commit()
    c.close()

if __name__ == '__main__':
    save('test123', 'user', 'Hello Korvin')
    save('test123', 'assistant', 'Hello Carlos, how can I help?')
    history = get_history('test123')
    for m in history:
        print(f"  [{m['role']}]: {m['content']}")
    print('Memory working.')
