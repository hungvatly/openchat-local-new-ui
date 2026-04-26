"""
OpenChat Local — Chat History (SQLite)
Persistent chat storage with multi-user support, personas, folders, tags, and full-text search.
"""
import os
import json
import sqlite3
import time
from typing import List, Dict, Optional
from config import settings
from utils.local_llm import SYSTEM_PROMPT

DB_PATH = os.path.join(settings.CHROMA_PERSIST_DIR, "chat_history.db")

# ── Default Personas ───────────────────────────────────

DEFAULT_PERSONAS = [
    {
        "id": "default",
        "name": "Default",
        "prompt": SYSTEM_PROMPT,
    },
    {
        "id": "translator",
        "name": "Translator",
        "prompt": "You are a professional translator. Translate text accurately between languages while preserving tone, context, and nuance. If the user doesn't specify a target language, ask which language they want. Provide natural, fluent translations — not word-for-word. For ambiguous phrases, explain multiple possible translations.",
    },
    {
        "id": "code_reviewer",
        "name": "Code Reviewer",
        "prompt": "You are a senior software engineer performing code review. Analyze code for bugs, security issues, performance problems, and style. Suggest specific improvements with corrected code. Explain why each change matters. Be thorough but constructive.",
    },
    {
        "id": "email_writer",
        "name": "Email Writer",
        "prompt": "You are a professional email composer. Write clear, well-structured emails matching the requested tone (formal, friendly, persuasive, apologetic). Include subject line suggestions. Adjust formality based on context. Keep emails concise but complete.",
    },
    {
        "id": "legal_advisor",
        "name": "Legal Advisor",
        "prompt": "You are a legal research assistant. Provide general legal information and help analyze documents from a legal perspective. Always clarify that you are an AI and not a licensed attorney. Flag potential legal issues, explain relevant concepts, and suggest when professional legal counsel is needed.",
    },
    {
        "id": "creative_writer",
        "name": "Creative Writer",
        "prompt": "You are a creative writing assistant. Help with stories, poems, scripts, and creative content. Use vivid language, strong imagery, and engaging narrative techniques. Adapt your style to match the requested genre and tone.",
    },
    {
        "id": "data_analyst",
        "name": "Data Analyst",
        "prompt": "You are a data analyst. Help interpret data, create analyses, and explain findings clearly. When given data, identify patterns, trends, and insights. Suggest visualizations. Present findings in a structured format with clear conclusions.",
    },
]

DEFAULT_USER_ID = "default"
DEFAULT_USER_NAME = "Default User"
DEFAULT_USER_COLOR = "#6366f1"


class ChatHistory:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            # ── Users table ────────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    avatar_color TEXT DEFAULT '#6366f1',
                    created_at REAL
                )
            """)

            # ── Conversations table ────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT DEFAULT 'default',
                    title TEXT DEFAULT 'New Chat',
                    model TEXT DEFAULT '',
                    persona_id TEXT DEFAULT 'default',
                    folder TEXT DEFAULT '',
                    tags TEXT DEFAULT '',
                    created_at REAL,
                    updated_at REAL
                )
            """)

            # ── Messages table ─────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    images TEXT DEFAULT '',
                    sources TEXT DEFAULT '[]',
                    parent_id INTEGER DEFAULT NULL,
                    active_child_index INTEGER DEFAULT 0,
                    created_at REAL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)

            # ── Personas table ─────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS personas (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    is_builtin INTEGER DEFAULT 0,
                    created_at REAL
                )
            """)

            # ── Memory table ───────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory (
                    key TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    value TEXT NOT NULL,
                    updated_at REAL,
                    PRIMARY KEY (key, user_id)
                )
            """)

            # ── Schema migrations (idempotent) ─────────────────
            for col_sql in [
                "ALTER TABLE conversations ADD COLUMN persona_id TEXT DEFAULT 'default'",
                "ALTER TABLE conversations ADD COLUMN folder TEXT DEFAULT ''",
                "ALTER TABLE conversations ADD COLUMN tags TEXT DEFAULT ''",
                "ALTER TABLE conversations ADD COLUMN user_id TEXT DEFAULT 'default'",
                "ALTER TABLE conversations ADD COLUMN is_locked INTEGER DEFAULT 0",
                "ALTER TABLE conversations ADD COLUMN lock_password_hash TEXT DEFAULT ''",
                "ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''",
                "ALTER TABLE users ADD COLUMN avatar_path TEXT DEFAULT ''",
                "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0",
                "ALTER TABLE messages ADD COLUMN parent_id INTEGER DEFAULT NULL",
                "ALTER TABLE messages ADD COLUMN active_child_index INTEGER DEFAULT 0",
            ]:
                try:
                    conn.execute(col_sql)
                except sqlite3.OperationalError:
                    pass

            # Migrate legacy memory table (no user_id column)
            try:
                conn.execute("ALTER TABLE memory ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")
            except sqlite3.OperationalError:
                pass
            # Fix old PRIMARY KEY if needed
            try:
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS memory_key_user ON memory(key, user_id)")
            except Exception:
                pass

            # ── FTS5 ───────────────────────────────────────────
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                        content, conversation_id UNINDEXED,
                        content='messages', content_rowid='id'
                    )
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                        INSERT INTO messages_fts(rowid, content, conversation_id)
                        VALUES (new.id, new.content, new.conversation_id);
                    END
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                        INSERT INTO messages_fts(messages_fts, rowid, content, conversation_id)
                        VALUES('delete', old.id, old.content, old.conversation_id);
                    END
                """)
            except Exception:
                pass

            # ── Seed default user ──────────────────────────────
            conn.execute(
                "INSERT OR IGNORE INTO users (id, name, avatar_color, created_at) VALUES (?, ?, ?, ?)",
                (DEFAULT_USER_ID, DEFAULT_USER_NAME, DEFAULT_USER_COLOR, time.time()),
            )

            # ── Seed default personas ──────────────────────────
            for p in DEFAULT_PERSONAS:
                conn.execute(
                    "INSERT OR IGNORE INTO personas (id, name, prompt, is_builtin, created_at) VALUES (?, ?, ?, 1, ?)",
                    (p["id"], p["name"], p["prompt"], time.time()),
                )
                conn.execute(
                    "UPDATE personas SET prompt = ?, name = ? WHERE id = ? AND is_builtin = 1",
                    (p["prompt"], p["name"], p["id"])
                )
            conn.commit()

    def factory_reset(self):
        """Wipes all data from the database and reseeds defaults."""
        with self._conn() as conn:
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM conversations")
            conn.execute("DELETE FROM users")
            conn.execute("DELETE FROM personas")
            conn.execute("DELETE FROM memory")
        self._init_db()

    # ── Users ──────────────────────────────────────────

    def list_users(self) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, avatar_color, avatar_path, is_admin, (password_hash != '') as has_password, created_at FROM users ORDER BY created_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_user(self, user_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def create_user(self, user_id: str, name: str, avatar_color: str = "#6366f1", is_admin: int = 0) -> Dict:
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (id, name, avatar_color, is_admin, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, name, avatar_color, is_admin, now),
            )
            conn.commit()
        return {"id": user_id, "name": name, "avatar_color": avatar_color, "is_admin": is_admin, "created_at": now}

    def update_user(self, user_id: str, name: str = None, avatar_color: str = None, avatar_path: str = None, password_hash: str = None, is_admin: int = None) -> Dict:
        with self._conn() as conn:
            if name:
                conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))
            if avatar_color:
                conn.execute("UPDATE users SET avatar_color = ? WHERE id = ?", (avatar_color, user_id))
            if avatar_path is not None:
                conn.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (avatar_path, user_id))
            if password_hash is not None:
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
            if is_admin is not None:
                conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (is_admin, user_id))
            conn.commit()
        return self.get_user(user_id)

    def delete_user(self, user_id: str):
        if user_id == DEFAULT_USER_ID:
            return  # Protect default user
        with self._conn() as conn:
            # Cascade delete all user's conversations/messages via FK
            conv_ids = [r[0] for r in conn.execute(
                "SELECT id FROM conversations WHERE user_id = ?", (user_id,)
            ).fetchall()]
            for cid in conv_ids:
                conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
            conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM memory WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()

    # ── Conversations ──────────────────────────────────

    def create_conversation(self, conv_id: str, title: str = "New Chat", model: str = "",
                             persona_id: str = "default", user_id: str = DEFAULT_USER_ID,
                             is_locked: bool = False, lock_password_hash: str = "") -> Dict:
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO conversations (id, user_id, title, model, persona_id, folder, tags, is_locked, lock_password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, '', '', ?, ?, ?, ?)",
                (conv_id, user_id, title, model, persona_id, 1 if is_locked else 0, lock_password_hash, now, now),
            )
            conn.commit()
        return {"id": conv_id, "title": title, "model": model, "persona_id": persona_id,
                "user_id": user_id, "is_locked": is_locked, "created_at": now}

    def add_message(self, conv_id: str, role: str, content: str,
                    images: str = "", sources: list = None,
                    parent_id: int = None) -> int:
        now = time.time()
        src_json = json.dumps(sources or [])
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, images, sources, parent_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (conv_id, role, content, images, src_json, parent_id, now),
            )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
            conn.commit()
            return cur.lastrowid

    def update_title(self, conv_id: str, title: str):
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conv_id))
            conn.commit()

    def update_conversation(self, conv_id: str, **kwargs):
        """Update any conversation fields: title, folder, tags, persona_id."""
        allowed = {"title", "folder", "tags", "persona_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [conv_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE conversations SET {set_clause} WHERE id = ?", values)
            conn.commit()

    def list_conversations(self, limit: int = 50, offset: int = 0,
                           folder: str = None, tag: str = None,
                           user_id: str = DEFAULT_USER_ID) -> List[Dict]:
        with self._conn() as conn:
            query = "SELECT id, title, model, persona_id, folder, tags, is_locked, created_at, updated_at FROM conversations"
            params = []
            conditions = ["user_id = ?"]
            params.append(user_id)
            if folder:
                conditions.append("folder = ?")
                params.append(folder)
            if tag:
                conditions.append("tags LIKE ?")
                params.append(f"%{tag}%")
            query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(query, params).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["is_locked"] = bool(d.get("is_locked", 0))
                result.append(d)
            return result

    def get_message(self, msg_id: int) -> Optional[Dict]:
        with self._conn() as conn:
            m = conn.execute(
                "SELECT id, conversation_id, parent_id, active_child_index, role, content, images, sources, created_at FROM messages WHERE id = ?",
                (msg_id,)
            ).fetchone()
            if not m:
                return None
            children = conn.execute(
                "SELECT id FROM messages WHERE parent_id = ? ORDER BY created_at ASC", (msg_id,)
            ).fetchall()
            return {
                "id": m["id"],
                "conversation_id": m["conversation_id"],
                "parent_id": m["parent_id"],
                "active_child_index": m["active_child_index"] or 0,
                "role": m["role"],
                "content": m["content"],
                "images": m["images"],
                "sources": json.loads(m["sources"]) if m["sources"] else [],
                "children_ids": [r["id"] for r in children],
            }

    def set_active_child(self, parent_id: int, child_index: int):
        with self._conn() as conn:
            conn.execute(
                "UPDATE messages SET active_child_index = ? WHERE id = ?",
                (child_index, parent_id)
            )
            conn.commit()

    def get_conversation(self, conv_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if not row:
                return None
            messages = conn.execute(
                "SELECT id, parent_id, active_child_index, role, content, images, sources, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conv_id,),
            ).fetchall()
            keys = row.keys()
            return {
                "id": row["id"],
                "title": row["title"],
                "model": row["model"],
                "user_id": row["user_id"] if "user_id" in keys else DEFAULT_USER_ID,
                "persona_id": row["persona_id"] if "persona_id" in keys else "default",
                "folder": row["folder"] if "folder" in keys else "",
                "tags": row["tags"] if "tags" in keys else "",
                "is_locked": bool(row["is_locked"]) if "is_locked" in keys else False,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "messages": [
                    {
                        "id": m["id"],
                        "parent_id": m["parent_id"],
                        "active_child_index": m["active_child_index"] or 0,
                        "role": m["role"],
                        "content": m["content"],
                        "images": m["images"],
                        "sources": json.loads(m["sources"]) if m["sources"] else [],
                        "created_at": m["created_at"],
                    }
                    for m in messages
                ],
            }

    def lock_conversation(self, conv_id: str, password_hash: str) -> bool:
        """Lock a conversation with a password hash."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET is_locked = 1, lock_password_hash = ? WHERE id = ?",
                (password_hash, conv_id)
            )
            conn.commit()
        return True

    def unlock_conversation(self, conv_id: str) -> bool:
        """Permanently unlock a conversation."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET is_locked = 0, lock_password_hash = '' WHERE id = ?",
                (conv_id,)
            )
            conn.commit()
        return True

    def verify_lock_password(self, conv_id: str, password_hash: str) -> bool:
        """Check if password_hash matches the stored hash for the conversation."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT lock_password_hash FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            if not row:
                return False
            return row["lock_password_hash"] == password_hash

    def delete_conversation(self, conv_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            conn.commit()

    def get_folders(self, user_id: str = DEFAULT_USER_ID) -> List[str]:
        """Get all unique folder names for a user."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT folder FROM conversations WHERE folder != '' AND user_id = ? ORDER BY folder",
                (user_id,)
            ).fetchall()
            return [r["folder"] for r in rows]

    def get_all_tags(self, user_id: str = DEFAULT_USER_ID) -> List[str]:
        """Get all unique tags across conversations for a user."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT tags FROM conversations WHERE tags != '' AND user_id = ?", (user_id,)
            ).fetchall()
            all_tags = set()
            for r in rows:
                for t in r["tags"].split(","):
                    t = t.strip()
                    if t:
                        all_tags.add(t)
            return sorted(all_tags)

    # ── Search ─────────────────────────────────────────

    def search(self, query: str, limit: int = 20, user_id: str = DEFAULT_USER_ID) -> List[Dict]:
        """Full-text search across messages for a user."""
        with self._conn() as conn:
            try:
                rows = conn.execute("""
                    SELECT m.conversation_id, m.role, m.content, m.created_at, c.title
                    FROM messages_fts f
                    JOIN messages m ON m.id = f.rowid
                    JOIN conversations c ON c.id = m.conversation_id
                    WHERE messages_fts MATCH ? AND c.user_id = ?
                    ORDER BY m.created_at DESC LIMIT ?
                """, (query, user_id, limit)).fetchall()
                return [
                    {
                        "conversation_id": r["conversation_id"],
                        "conversation_title": r["title"],
                        "role": r["role"],
                        "content": r["content"][:200],
                        "created_at": r["created_at"],
                    }
                    for r in rows
                ]
            except Exception:
                rows = conn.execute("""
                    SELECT m.conversation_id, m.role, m.content, m.created_at, c.title
                    FROM messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    WHERE m.content LIKE ? AND c.user_id = ?
                    ORDER BY m.created_at DESC LIMIT ?
                """, (f"%{query}%", user_id, limit)).fetchall()
                return [
                    {
                        "conversation_id": r["conversation_id"],
                        "conversation_title": r["title"],
                        "role": r["role"],
                        "content": r["content"][:200],
                        "created_at": r["created_at"],
                    }
                    for r in rows
                ]

    # ── Personas ───────────────────────────────────────

    def list_personas(self) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT id, name, prompt, is_builtin FROM personas ORDER BY is_builtin DESC, name").fetchall()
            return [dict(r) for r in rows]

    def get_persona(self, persona_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)).fetchone()
            return dict(row) if row else None

    def save_persona(self, persona_id: str, name: str, prompt: str) -> Dict:
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO personas (id, name, prompt, is_builtin, created_at) VALUES (?, ?, ?, 0, ?)",
                (persona_id, name, prompt, now),
            )
            conn.commit()
        return {"id": persona_id, "name": name}

    def delete_persona(self, persona_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM personas WHERE id = ? AND is_builtin = 0", (persona_id,))
            conn.commit()

    # ── Memory ────────────────────────────────────────

    def get_all_memory(self, user_id: str = DEFAULT_USER_ID) -> List[Dict]:
        """Get all memory entries for a user."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT key, value, updated_at FROM memory WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def save_memory(self, key: str, value: str, user_id: str = DEFAULT_USER_ID) -> Dict:
        """Insert or replace a memory entry."""
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO memory (key, user_id, value, updated_at) VALUES (?, ?, ?, ?)",
                (key, user_id, value, now),
            )
            conn.commit()
        return {"key": key, "value": value, "updated_at": now}

    def delete_memory(self, key: str, user_id: str = DEFAULT_USER_ID):
        """Delete a memory entry by key."""
        with self._conn() as conn:
            conn.execute("DELETE FROM memory WHERE key = ? AND user_id = ?", (key, user_id))
            conn.commit()

    def build_memory_prompt(self, user_id: str = DEFAULT_USER_ID) -> str:
        """Return a formatted block of all memories for injection into system prompt."""
        entries = self.get_all_memory(user_id)
        if not entries:
            return ""
        lines = ["[Memory — facts about the user:"]
        for e in entries:
            lines.append(f"  - {e['key']}: {e['value']}")
        lines.append("]")
        return "\n".join(lines)

    # ── Export ─────────────────────────────────────────

    def export_markdown(self, conv_id: str) -> Optional[str]:
        conv = self.get_conversation(conv_id)
        if not conv:
            return None
        lines = [f"# {conv['title']}\n"]
        for m in conv["messages"]:
            role_label = "You" if m["role"] == "user" else "AI"
            lines.append(f"### {role_label}\n")
            lines.append(m["content"] + "\n")
            if m["sources"]:
                src_names = [s.get("source", "") for s in m["sources"] if s.get("source")]
                if src_names:
                    lines.append(f"*Sources: {', '.join(src_names)}*\n")
            lines.append("---\n")
        return "\n".join(lines)

    def get_messages_for_context(self, conv_id: str, limit: int = 10) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
                (conv_id, limit),
            ).fetchall()
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


chat_history = ChatHistory()
