import os
import sqlite3
import json
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

class Database:
    def __init__(self, db_path: str = "watcher.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create tables if they do not exist."""
        with self._get_conn() as conn:
            # Enable Foreign Keys
            conn.execute("PRAGMA foreign_keys = ON;")
            
            # 1. Watch Groups (for storing cookies and local storage state)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watch_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_key TEXT UNIQUE NOT NULL,
                    session_cookies TEXT, -- Serialized JSON array of cookies
                    local_storage TEXT,   -- Serialized JSON dict of localStorage
                    updated_at TEXT NOT NULL
                )
            """)

            # 2. Watch Pages (for tracking last check/change times)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watch_pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_key TEXT NOT NULL,
                    page_key TEXT NOT NULL,
                    last_content_hash TEXT,
                    last_checked_at TEXT,
                    last_changed_at TEXT,
                    UNIQUE(group_key, page_key)
                )
            """)

            # 3. Page States (stores content history for comparison/viewing)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS page_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_key TEXT NOT NULL,
                    page_key TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    cleaned_content TEXT NOT NULL,
                    screenshot_path TEXT,
                    created_at TEXT NOT NULL
                )
            """)

            # 4. Change History (records detected diffs)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS change_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_key TEXT NOT NULL,
                    page_key TEXT NOT NULL,
                    old_state_id INTEGER,
                    new_state_id INTEGER NOT NULL,
                    diff_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (old_state_id) REFERENCES page_states (id),
                    FOREIGN KEY (new_state_id) REFERENCES page_states (id)
                )
            """)
            conn.commit()

    # --- Watch Groups Operations ---
    def get_group_session(self, group_key: str) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
        """Retrieve cookies and localStorage for a group."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT session_cookies, local_storage FROM watch_groups WHERE group_key = ?",
                (group_key,)
            ).fetchone()
            
            if not row:
                return None, None
            
            cookies = json.loads(row["session_cookies"]) if row["session_cookies"] else None
            local_storage = json.loads(row["local_storage"]) if row["local_storage"] else None
            return cookies, local_storage

    def save_group_session(self, group_key: str, cookies: List[Dict[str, Any]], local_storage: Dict[str, Any]):
        """Save cookies and localStorage for a group."""
        now_str = datetime.utcnow().isoformat()
        cookies_json = json.dumps(cookies) if cookies else None
        local_storage_json = json.dumps(local_storage) if local_storage else None
        
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO watch_groups (group_key, session_cookies, local_storage, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(group_key) DO UPDATE SET
                    session_cookies = excluded.session_cookies,
                    local_storage = excluded.local_storage,
                    updated_at = excluded.updated_at
            """, (group_key, cookies_json, local_storage_json, now_str))
            conn.commit()

    # --- Watch Pages Operations ---
    def get_page_meta(self, group_key: str, page_key: str) -> Optional[sqlite3.Row]:
        """Get the page metadata record."""
        with self._get_conn() as conn:
            return conn.execute(
                "SELECT * FROM watch_pages WHERE group_key = ? AND page_key = ?",
                (group_key, page_key)
            ).fetchone()

    def update_page_check(self, group_key: str, page_key: str, content_hash: Optional[str] = None, did_change: bool = False):
        """Update check execution metadata for a page."""
        now_str = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            # Check if record exists
            row = conn.execute(
                "SELECT id FROM watch_pages WHERE group_key = ? AND page_key = ?",
                (group_key, page_key)
            ).fetchone()

            if not row:
                conn.execute("""
                    INSERT INTO watch_pages (group_key, page_key, last_content_hash, last_checked_at, last_changed_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (group_key, page_key, content_hash, now_str, now_str if did_change else None))
            else:
                if did_change:
                    conn.execute("""
                        UPDATE watch_pages
                        SET last_content_hash = ?, last_checked_at = ?, last_changed_at = ?
                        WHERE group_key = ? AND page_key = ?
                    """, (content_hash, now_str, now_str, group_key, page_key))
                else:
                    # Update content hash if provided, otherwise preserve
                    if content_hash:
                        conn.execute("""
                            UPDATE watch_pages
                            SET last_content_hash = ?, last_checked_at = ?
                            WHERE group_key = ? AND page_key = ?
                        """, (content_hash, now_str, group_key, page_key))
                    else:
                        conn.execute("""
                            UPDATE watch_pages
                            SET last_checked_at = ?
                            WHERE group_key = ? AND page_key = ?
                        """, (now_str, group_key, page_key))
            conn.commit()

    # --- Page States & History Operations ---
    def get_last_page_state(self, group_key: str, page_key: str) -> Optional[sqlite3.Row]:
        """Retrieve the latest page state for comparison."""
        with self._get_conn() as conn:
            return conn.execute("""
                SELECT * FROM page_states
                WHERE group_key = ? AND page_key = ?
                ORDER BY id DESC LIMIT 1
            """, (group_key, page_key)).fetchone()

    def save_page_state(self, group_key: str, page_key: str, content_hash: str, cleaned_content: str, screenshot_path: Optional[str] = None) -> int:
        """Save a new page state snapshot."""
        now_str = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO page_states (group_key, page_key, content_hash, cleaned_content, screenshot_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (group_key, page_key, content_hash, cleaned_content, screenshot_path, now_str))
            conn.commit()
            return cursor.lastrowid

    def save_change_history(self, group_key: str, page_key: str, old_state_id: Optional[int], new_state_id: int, diff_summary: str):
        """Record details of a detected change."""
        now_str = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO change_history (group_key, page_key, old_state_id, new_state_id, diff_summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (group_key, page_key, old_state_id, new_state_id, diff_summary, now_str))
            conn.commit()

    def clean_old_states(self, group_key: str, page_key: str, keep_limit: int = 10):
        """Housekeeping to delete old states and avoid database bloating."""
        with self._get_conn() as conn:
            # Find the IDs of the last `keep_limit` states
            rows = conn.execute("""
                SELECT id FROM page_states
                WHERE group_key = ? AND page_key = ?
                ORDER BY id DESC LIMIT ?
            """, (group_key, page_key, keep_limit)).fetchall()
            
            if not rows:
                return
            
            last_kept_id = rows[-1]["id"]
            
            # Delete states older than the oldest kept state
            # Note: We must also delete or nullify dependent change_history records or let ON DELETE behave correctly
            # We nullify the old_state_id foreign key references in change_history to avoid violating constraints
            conn.execute("""
                UPDATE change_history
                SET old_state_id = NULL
                WHERE old_state_id IN (
                    SELECT id FROM page_states
                    WHERE group_key = ? AND page_key = ? AND id < ?
                )
            """, (group_key, page_key, last_kept_id))
            
            # Delete screenshots associated with states we are removing (if any)
            old_screenshots = conn.execute("""
                SELECT screenshot_path FROM page_states
                WHERE group_key = ? AND page_key = ? AND id < ? AND screenshot_path IS NOT NULL
            """, (group_key, page_key, last_kept_id)).fetchall()
            
            for row in old_screenshots:
                path = row["screenshot_path"]
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass # Ignore deletions of missing files
            
            conn.execute("""
                DELETE FROM page_states
                WHERE group_key = ? AND page_key = ? AND id < ?
            """, (group_key, page_key, last_kept_id))
            conn.commit()
