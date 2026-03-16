# -*- coding: utf-8 -*-
"""
core/db_extensions.py
Расширение базы данных — новые таблицы v4:
  life_modes      — текущий режим и уровень контроля пользователя
  finance_goals   — финансовые цели
  finance_txns    — транзакции (доходы и расходы)
  receipts        — сохранённые чеки
  price_db        — база цен по городам
  content_log     — история рекомендаций контента
  mood_log        — дневник настроения
  user_onboarding — стадия онбординга (разовый / лайфмод)
"""

import logging
from core.database import get_conn, _lock

logger = logging.getLogger(__name__)


def init_extensions():
    """Вызывать при старте после init_db()."""
    with _lock:
        with get_conn() as conn:
            conn.executescript("""
            -- Режим жизни пользователя
            CREATE TABLE IF NOT EXISTS life_modes (
                user_id       INTEGER PRIMARY KEY,
                mode          TEXT NOT NULL DEFAULT 'health',
                control_level TEXT NOT NULL DEFAULT 'soft',
                mode_until    TEXT,
                started_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            );

            -- Стадия онбординга
            CREATE TABLE IF NOT EXISTS user_onboarding (
                user_id        INTEGER PRIMARY KEY,
                stage          TEXT NOT NULL DEFAULT 'new',
                is_lifemode    INTEGER DEFAULT 0,
                survey_blocks  TEXT DEFAULT '{}',
                updated_at     TEXT NOT NULL
            );

            -- Финансовые цели
            CREATE TABLE IF NOT EXISTS finance_goals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                title       TEXT NOT NULL,
                emoji       TEXT DEFAULT '🎯',
                target_amt  REAL NOT NULL,
                current_amt REAL DEFAULT 0,
                deadline    TEXT,
                is_active   INTEGER DEFAULT 1,
                created_at  TEXT NOT NULL
            );

            -- Транзакции
            CREATE TABLE IF NOT EXISTS finance_txns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                amount      REAL NOT NULL,
                direction   TEXT NOT NULL CHECK(direction IN ('income','expense')),
                category    TEXT DEFAULT 'other',
                note        TEXT DEFAULT '',
                txn_date    TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );

            -- Сохранённые чеки
            CREATE TABLE IF NOT EXISTS receipts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                store       TEXT,
                city        TEXT,
                total_amt   REAL,
                items_json  TEXT NOT NULL,
                receipt_date TEXT,
                created_at  TEXT NOT NULL
            );

            -- База цен по городам
            CREATE TABLE IF NOT EXISTS price_db (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                product_key  TEXT NOT NULL,
                product_raw  TEXT NOT NULL,
                price        REAL NOT NULL,
                store        TEXT,
                city         TEXT,
                user_id      INTEGER,
                recorded_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_price_key ON price_db(product_key, city);

            -- История контент-рекомендаций
            CREATE TABLE IF NOT EXISTS content_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                category    TEXT NOT NULL,
                title       TEXT NOT NULL,
                detail      TEXT,
                rating      INTEGER,
                created_at  TEXT NOT NULL
            );

            -- Дневник настроения
            CREATE TABLE IF NOT EXISTS mood_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                mood        TEXT NOT NULL,
                note        TEXT DEFAULT '',
                log_date    TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                UNIQUE(user_id, log_date)
            );
            """)
    logger.info("DB extensions initialized ✅")


# ── LifeMode helpers ──────────────────────────────────────────────────────

from datetime import datetime as _dt

def _now():
    return _dt.now().strftime("%Y-%m-%d %H:%M:%S")


def get_life_mode(user_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT mode, control_level, mode_until FROM life_modes WHERE user_id=?",
            (user_id,)
        ).fetchone()
    if row:
        return {"mode": row["mode"], "control": row["control_level"], "until": row["mode_until"]}
    return {"mode": "health", "control": "soft", "until": None}


def set_life_mode(user_id: int, mode: str, control: str = "soft", until: str = None):
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO life_modes
                   (user_id, mode, control_level, mode_until, started_at, updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (user_id, mode, control, until, _now(), _now())
            )


# ── Onboarding helpers ────────────────────────────────────────────────────

def get_onboarding(user_id: int) -> dict:
    import json
    with get_conn() as conn:
        row = conn.execute(
            "SELECT stage, is_lifemode, survey_blocks FROM user_onboarding WHERE user_id=?",
            (user_id,)
        ).fetchone()
    if row:
        return {
            "stage": row["stage"],
            "is_lifemode": bool(row["is_lifemode"]),
            "blocks": json.loads(row["survey_blocks"] or "{}")
        }
    return {"stage": "new", "is_lifemode": False, "blocks": {}}


def set_onboarding(user_id: int, stage: str, is_lifemode: bool = False, blocks: dict = None):
    import json
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO user_onboarding
                   (user_id, stage, is_lifemode, survey_blocks, updated_at)
                   VALUES (?,?,?,?,?)""",
                (user_id, stage, int(is_lifemode),
                 json.dumps(blocks or {}, ensure_ascii=False), _now())
            )


# ── Finance helpers ───────────────────────────────────────────────────────

def add_finance_goal(user_id: int, title: str, target: float,
                     emoji: str = "🎯", deadline: str = None) -> int:
    with _lock:
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO finance_goals
                   (user_id, title, emoji, target_amt, deadline, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (user_id, title, emoji, target, deadline, _now())
            )
            return cur.lastrowid


def get_finance_goals(user_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, title, emoji, target_amt, current_amt, deadline
               FROM finance_goals WHERE user_id=? AND is_active=1
               ORDER BY created_at DESC""",
            (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def update_goal_progress(goal_id: int, amount: float):
    with _lock:
        with get_conn() as conn:
            conn.execute(
                "UPDATE finance_goals SET current_amt=current_amt+? WHERE id=?",
                (amount, goal_id)
            )


def add_txn(user_id: int, amount: float, direction: str,
            category: str = "other", note: str = "", date: str = None):
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO finance_txns
                   (user_id, amount, direction, category, note, txn_date, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (user_id, amount, direction, category, note,
                 date or _dt.now().strftime("%Y-%m-%d"), _now())
            )


def get_month_stats(user_id: int) -> dict:
    """Доходы и расходы за текущий месяц по категориям."""
    month = _dt.now().strftime("%Y-%m")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT direction, category, SUM(amount) as total
               FROM finance_txns
               WHERE user_id=? AND txn_date LIKE ?
               GROUP BY direction, category""",
            (user_id, f"{month}%")
        ).fetchall()
    income = {}
    expense = {}
    for r in rows:
        if r["direction"] == "income":
            income[r["category"]] = r["total"]
        else:
            expense[r["category"]] = r["total"]
    return {
        "income": income,
        "expense": expense,
        "total_income": sum(income.values()),
        "total_expense": sum(expense.values()),
        "balance": sum(income.values()) - sum(expense.values())
    }


# ── Receipt helpers ───────────────────────────────────────────────────────

def save_receipt(user_id: int, store: str, city: str,
                 items: list, total: float, receipt_date: str = None) -> int:
    import json
    with _lock:
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO receipts
                   (user_id, store, city, total_amt, items_json, receipt_date, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (user_id, store, city, total,
                 json.dumps(items, ensure_ascii=False),
                 receipt_date or _dt.now().strftime("%Y-%m-%d"), _now())
            )
            receipt_id = cur.lastrowid

        # Сохраняем каждую позицию в price_db
        for item in items:
            key = _normalize_product(item.get("name", ""))
            if key:
                conn.execute(
                    """INSERT INTO price_db
                       (product_key, product_raw, price, store, city, user_id, recorded_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (key, item.get("name", ""), item.get("price", 0),
                     store, city, user_id, _now())
                )
    return receipt_id


def _normalize_product(name: str) -> str:
    """Простая нормализация — lowercase, убираем числа и единицы."""
    import re
    n = name.lower().strip()
    n = re.sub(r'\d+[\.,]?\d*\s*(г|кг|мл|л|шт|уп|пач)', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n[:80] if n else ""


def get_price_compare(user_id: int, product_keys: list, city: str) -> dict:
    """Сравнение цен по магазинам для списка продуктов."""
    result = {}
    with get_conn() as conn:
        for key in product_keys:
            rows = conn.execute(
                """SELECT store, AVG(price) as avg_price, COUNT(*) as cnt
                   FROM price_db
                   WHERE product_key=? AND city=?
                   GROUP BY store HAVING cnt >= 2
                   ORDER BY avg_price""",
                (key, city)
            ).fetchall()
            if rows:
                result[key] = [{"store": r["store"], "price": round(r["avg_price"], 1)} for r in rows]
    return result


# ── Mood helpers ──────────────────────────────────────────────────────────

def log_mood(user_id: int, mood: str, note: str = ""):
    today = _dt.now().strftime("%Y-%m-%d")
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO mood_log
                   (user_id, mood, note, log_date, created_at)
                   VALUES (?,?,?,?,?)""",
                (user_id, mood, note, today, _now())
            )


def get_mood_week(user_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT log_date, mood FROM mood_log
               WHERE user_id=? AND log_date >= date('now','-7 days')
               ORDER BY log_date""",
            (user_id,)
        ).fetchall()
    return [{"date": r["log_date"], "mood": r["mood"]} for r in rows]


# ── Content log helpers ───────────────────────────────────────────────────

def log_content(user_id: int, category: str, title: str, detail: str = ""):
    with _lock:
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO content_log (user_id, category, title, detail, created_at)
                   VALUES (?,?,?,?,?)""",
                (user_id, category, title, detail, _now())
            )


def get_content_history(user_id: int, category: str, limit: int = 30) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT title FROM content_log
               WHERE user_id=? AND category=?
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, category, limit)
        ).fetchall()
    return [r["title"] for r in rows]
