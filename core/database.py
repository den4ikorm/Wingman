"""
core/database.py
MemoryManager v3 — SQLite с атомарной записью (threading.Lock)
+ chat_log, day_summary, week_summary, shopping, weight, feedback
"""

import json
import sqlite3
import os
import logging
import threading
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "/mnt/data/wingman.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

_lock = threading.Lock()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # атомарность при crash
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    with _lock:
        with get_conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS profiles (
                user_id    INTEGER PRIMARY KEY,
                data       TEXT NOT NULL,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS chat_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                role       TEXT NOT NULL,
                message    TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS day_summaries (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                day_date   TEXT NOT NULL,
                summary    TEXT NOT NULL,
                mood       TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, day_date)
            );
            CREATE TABLE IF NOT EXISTS week_summaries (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                week_start TEXT NOT NULL,
                summary    TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, week_start)
            );
            CREATE TABLE IF NOT EXISTS shopping_list (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                item       TEXT NOT NULL,
                category   TEXT,
                checked    INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS weight_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                weight     REAL NOT NULL,
                logged_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                text       TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS diet_compliance (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                day_date   TEXT NOT NULL,
                followed   INTEGER DEFAULT 1,
                note       TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(user_id, day_date)
            );

            -- Human State Engine tables (v3)

            CREATE TABLE IF NOT EXISTS user_state (
                user_id    INTEGER PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                event_type    TEXT NOT NULL,
                value         TEXT,
                metadata_json TEXT DEFAULT '{}',
                created_at    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_user_date
                ON events(user_id, created_at);

            CREATE TABLE IF NOT EXISTS user_patterns (
                user_id      INTEGER NOT NULL,
                pattern_name TEXT NOT NULL,
                confidence   REAL DEFAULT 0.5,
                detected_at  TEXT NOT NULL,
                PRIMARY KEY (user_id, pattern_name)
            );

            CREATE TABLE IF NOT EXISTS solutions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_type TEXT NOT NULL,
                context_tags TEXT DEFAULT '',
                solution     TEXT NOT NULL,
                success_rate REAL DEFAULT 0.5,
                usage_count  INTEGER DEFAULT 0,
                created_at   TEXT NOT NULL
            );
            """)
    logger.info("DB initialized (WAL mode)")


class MemoryManager:
    def __init__(self, user_id: int):
        self.user_id = user_id

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _exec(self, sql: str, params: tuple = ()):
        """Атомарное выполнение записи с lock."""
        with _lock:
            with get_conn() as conn:
                conn.execute(sql, params)

    def _fetch_one(self, sql: str, params: tuple = ()):
        with get_conn() as conn:
            return conn.execute(sql, params).fetchone()

    def _fetch_all(self, sql: str, params: tuple = ()):
        with get_conn() as conn:
            return conn.execute(sql, params).fetchall()

    # ── PROFILE ────────────────────────────────────────────────────

    def get_profile(self) -> dict:
        row = self._fetch_one("SELECT data FROM profiles WHERE user_id=?", (self.user_id,))
        if row:
            try:
                return json.loads(row["data"])
            except Exception:
                return {}
        return {}

    def save_profile(self, data: dict):
        existing = self.get_profile()
        existing.update(data)
        existing["last_update"] = self._now()
        self._exec(
            "INSERT OR REPLACE INTO profiles (user_id, data, updated_at) VALUES (?,?,?)",
            (self.user_id, json.dumps(existing, ensure_ascii=False), self._now())
        )

    # ── VIBE ───────────────────────────────────────────────────────

    def set_vibe(self, vibe: str):
        self.save_profile({"current_vibe": vibe})

    def get_vibe(self) -> str:
        return self.get_profile().get("current_vibe", "observer")

    def get_vibe_css(self) -> str:
        return {"spark": "style_spark.css", "observer": "style_observer.css",
                "twilight": "style_twilight.css"}.get(self.get_vibe(), "style_observer.css")

    # ── MOOD ───────────────────────────────────────────────────────

    def set_mood(self, mood: str):
        self.save_profile({"emotional_state": mood})

    def get_mood(self) -> str:
        return self.get_profile().get("emotional_state", "neutral")

    # ── STOP LIST ──────────────────────────────────────────────────

    def add_to_stop_list(self, item: str):
        profile = self.get_profile()
        sl = profile.get("stop_list", [])
        if item not in sl:
            sl.append(item)
        self.save_profile({"stop_list": sl})

    def get_stop_list(self) -> list:
        return self.get_profile().get("stop_list", [])

    # ── MEMORY LIGHT ───────────────────────────────────────────────

    def update_memory_light(self, key: str, value):
        profile = self.get_profile()
        memory = profile.get("memory_light", {})
        memory[key] = value
        self.save_profile({"memory_light": memory})

    def reset_memory_light(self):
        self.save_profile({"memory_light": {}})

    def get_memory_light(self) -> dict:
        return self.get_profile().get("memory_light", {})

    # ── PLAN ───────────────────────────────────────────────────────

    def save_last_plan(self, html: str):
        self.save_profile({"last_plan_html": html})

    def get_last_plan(self) -> str:
        return self.get_profile().get("last_plan_html", "")

    # ── REPORT FLAG ────────────────────────────────────────────────

    def mark_report_pending(self, status: bool):
        self.save_profile({"report_pending": status})

    def is_report_pending(self) -> bool:
        return self.get_profile().get("report_pending", False)

    # ── TASKS ──────────────────────────────────────────────────────

    def save_tasks(self, tasks: list):
        self.save_profile({"today_tasks": tasks})

    def get_tasks(self) -> list:
        return self.get_profile().get("today_tasks", [])

    def add_user_task(self, task: str) -> bool:
        tasks = self.get_tasks()
        if len(tasks) < 10:
            tasks.append(task)
            self.save_tasks(tasks)
            return True
        return False

    # ── SURPRISE ───────────────────────────────────────────────────

    def toggle_surprise(self, enabled: bool):
        self.save_profile({"surprise_enabled": enabled})

    # ── STREAK ─────────────────────────────────────────────────────

    def update_streak(self) -> int:
        profile = self.get_profile()
        last = profile.get("last_checkin")
        streak = profile.get("streak", 0)
        today = str(date.today())
        if last == today:
            return streak
        yesterday = str(date.today() - timedelta(days=1))
        streak = streak + 1 if last == yesterday else 1
        self.save_profile({"streak": streak, "last_checkin": today})
        return streak

    def get_streak(self) -> int:
        return self.get_profile().get("streak", 0)

    # ── CHAT LOG ───────────────────────────────────────────────────

    def save_message(self, role: str, message: str):
        self._exec(
            "INSERT INTO chat_log (user_id, role, message, created_at) VALUES (?,?,?,?)",
            (self.user_id, role, message[:1500], self._now())
        )

    def get_recent_history(self, limit: int = 20) -> list[dict]:
        rows = self._fetch_all(
            "SELECT role, message FROM chat_log WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (self.user_id, limit)
        )
        return [{"role": r["role"], "content": r["message"]} for r in reversed(rows)]

    def get_today_messages(self) -> list[dict]:
        today = str(date.today())
        rows = self._fetch_all(
            "SELECT role, message, created_at FROM chat_log WHERE user_id=? AND created_at LIKE ?",
            (self.user_id, f"{today}%")
        )
        return [{"role": r["role"], "content": r["message"], "time": r["created_at"]} for r in rows]

    # ── DAY SUMMARY ────────────────────────────────────────────────

    def save_day_summary(self, summary: str, mood: str = None):
        today = str(date.today())
        self._exec(
            "INSERT OR REPLACE INTO day_summaries "
            "(user_id, day_date, summary, mood, created_at) VALUES (?,?,?,?,?)",
            (self.user_id, today, summary, mood, self._now())
        )

    def get_day_summary(self, day: str = None) -> str:
        day = day or str(date.today())
        row = self._fetch_one(
            "SELECT summary FROM day_summaries WHERE user_id=? AND day_date=?",
            (self.user_id, day)
        )
        return row["summary"] if row else ""

    def get_last_7_summaries(self) -> list[dict]:
        week_ago = str(date.today() - timedelta(days=7))
        rows = self._fetch_all(
            "SELECT day_date, summary, mood FROM day_summaries "
            "WHERE user_id=? AND day_date >= ? ORDER BY day_date",
            (self.user_id, week_ago)
        )
        return [{"date": r["day_date"], "summary": r["summary"], "mood": r["mood"]} for r in rows]

    # ── WEEK SUMMARY ───────────────────────────────────────────────

    def save_week_summary(self, summary: str):
        today = date.today()
        week_start = str(today - timedelta(days=today.weekday()))
        self._exec(
            "INSERT OR REPLACE INTO week_summaries "
            "(user_id, week_start, summary, created_at) VALUES (?,?,?,?)",
            (self.user_id, week_start, summary, self._now())
        )

    def get_latest_week_summary(self) -> str:
        row = self._fetch_one(
            "SELECT summary FROM week_summaries WHERE user_id=? ORDER BY week_start DESC LIMIT 1",
            (self.user_id,)
        )
        return row["summary"] if row else ""

    # ── SHOPPING LIST ──────────────────────────────────────────────

    def save_shopping_list(self, items: list[dict]):
        with _lock:
            with get_conn() as conn:
                conn.execute("DELETE FROM shopping_list WHERE user_id=?", (self.user_id,))
                for it in items:
                    conn.execute(
                        "INSERT INTO shopping_list (user_id, item, category, checked, created_at) VALUES (?,?,?,0,?)",
                        (self.user_id, it.get("item", ""), it.get("category", "Прочее"), self._now())
                    )

    def get_shopping_list(self) -> list[dict]:
        rows = self._fetch_all(
            "SELECT id, item, category, checked FROM shopping_list "
            "WHERE user_id=? ORDER BY category, item",
            (self.user_id,)
        )
        return [{"id": r["id"], "item": r["item"], "category": r["category"],
                 "checked": bool(r["checked"])} for r in rows]

    def toggle_shopping_item(self, item_id: int):
        self._exec(
            "UPDATE shopping_list SET checked = 1 - checked WHERE id=? AND user_id=?",
            (item_id, self.user_id)
        )

    # ── WEIGHT LOG ─────────────────────────────────────────────────

    def log_weight(self, weight: float):
        self._exec(
            "INSERT INTO weight_log (user_id, weight, logged_at) VALUES (?,?,?)",
            (self.user_id, weight, self._now())
        )

    def get_weight_history(self, days: int = 30) -> list[dict]:
        since = str(date.today() - timedelta(days=days))
        rows = self._fetch_all(
            "SELECT weight, logged_at FROM weight_log WHERE user_id=? AND logged_at >= ? ORDER BY logged_at",
            (self.user_id, since)
        )
        return [{"weight": r["weight"], "date": r["logged_at"][:10]} for r in rows]

    # ── FEEDBACK ───────────────────────────────────────────────────

    def save_feedback(self, text: str):
        self._exec(
            "INSERT INTO feedback (user_id, text, created_at) VALUES (?,?,?)",
            (self.user_id, text, self._now())
        )

    # ── DIET COMPLIANCE (соблюдение плана) ────────────────────────

    def log_compliance(self, followed: bool, note: str = ""):
        """Записать соблюдал ли пользователь план сегодня."""
        today = str(date.today())
        self._exec(
            """INSERT OR REPLACE INTO diet_compliance
               (user_id, day_date, followed, note, created_at)
               VALUES (?,?,?,?,?)""",
            (self.user_id, today, int(followed), note, self._now())
        )

    def get_compliance_history(self, days: int = 30) -> list[dict]:
        since = str(date.today() - timedelta(days=days))
        rows = self._fetch_all(
            "SELECT day_date, followed, note FROM diet_compliance "
            "WHERE user_id=? AND day_date >= ? ORDER BY day_date",
            (self.user_id, since)
        )
        return [{"date": r["day_date"], "followed": bool(r["followed"]),
                 "note": r["note"]} for r in rows]

    # ── INSIGHTS ───────────────────────────────────────────────────

    def log_insight(self, text: str):
        path = os.path.join(os.getenv("BASE_DIR", "./data"), "insights", f"{self.user_id}.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {self._now()} ---\n{text}\n")

    # ── STREAK ─────────────────────────────────────────────────────

    def get_compliance_history(self, days: int = 30) -> list[dict]:
        """История соблюдения плана — для streak расчёта."""
        rows = self._fetch_all(
            """SELECT day_date, followed, note FROM diet_compliance
               WHERE user_id=?
               AND day_date >= date('now', ?)
               ORDER BY day_date DESC""",
            (self.user_id, f"-{days} days")
        )
        return [{"date": r["day_date"], "followed": bool(r["followed"]),
                 "note": r["note"]} for r in rows]

    def get_current_streak(self) -> int:
        """Считает текущий streak (дней подряд)."""
        history = self.get_compliance_history(days=60)
        if not history:
            return 0
        streak = 0
        today = date.today()
        for i, entry in enumerate(history):
            entry_date = date.fromisoformat(entry["date"])
            expected = today - timedelta(days=i)
            if entry_date == expected and entry["followed"]:
                streak += 1
            else:
                break
        return streak

    # ── STATE / EVENTS helpers ─────────────────────────────────────

    def get_user_state(self) -> dict:
        """Быстрый доступ к состоянию пользователя."""
        row = self._fetch_one(
            "SELECT state_json FROM user_state WHERE user_id=?",
            (self.user_id,)
        )
        if row:
            import json as _json
            return _json.loads(row["state_json"])
        return {}

    def get_user_patterns(self) -> list[dict]:
        """Паттерны пользователя."""
        rows = self._fetch_all(
            "SELECT pattern_name, confidence FROM user_patterns WHERE user_id=? ORDER BY confidence DESC",
            (self.user_id,)
        )
        return [{"pattern": r["pattern_name"], "confidence": r["confidence"]} for r in rows]


def get_all_user_ids() -> list[int]:
    """Возвращает список всех user_id у которых есть профиль."""
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM profiles").fetchall()
        return [r["user_id"] for r in rows]


def get_last_week_summary(self) -> str:
    """Возвращает дайджест последней недели для контекста агентов."""
    try:
        row = self._fetch_one(
            "SELECT digest FROM week_summaries ORDER BY week_start DESC LIMIT 1"
        )
        return row["digest"] if row else ""
    except Exception:
        return ""

def save_week_summary(self, week_start: str, digest: str):
    """Сохраняет недельный дайджест."""
    try:
        self._exec(
            "CREATE TABLE IF NOT EXISTS week_summaries "
            "(week_start TEXT PRIMARY KEY, digest TEXT, created_at TEXT)"
        )
        self._exec(
            "INSERT OR REPLACE INTO week_summaries (week_start, digest, created_at) "
            "VALUES (?, ?, ?)",
            (week_start, digest, __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
    except Exception as e:
        import logging; logging.getLogger(__name__).error(f"save_week_summary: {e}")
