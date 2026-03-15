# -*- coding: utf-8 -*-
"""
core/pattern_cache.py
PatternCache v1.0 — кэш шаблонов, чтобы не гонять Gemini каждый раз

Таблицы:
  patterns        — настроение → рекомендации (фильм/музыка/книга)
  response_cache  — частые вопросы → готовые ответы (TTL 7 дней)
  user_patterns   — паттерны поведения пользователя (Gemini анализирует раз в день)
  content_log     — что показали, понравилось ли (из feedback/stop_list)

Логика:
  1. Бот сначала идёт в кэш
  2. Если есть свежий ответ — отдаёт сразу (0 токенов)
  3. Если нет или устарел — идёт к Gemini, сохраняет результат
  4. Ночью Gemini анализирует накопленные данные и обновляет паттерны
"""

import json
import sqlite3
import logging
import threading
from datetime import datetime, date, timedelta
from typing import Optional

from core.database import DB_PATH, _lock, get_conn

logger = logging.getLogger(__name__)


# ── ИНИЦИАЛИЗАЦИЯ ТАБЛИЦ ──────────────────────────────────────────────

def init_pattern_tables():
    with _lock:
        with get_conn() as conn:
            conn.executescript("""
            -- Шаблоны рекомендаций: настроение → контент
            CREATE TABLE IF NOT EXISTS patterns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                mood        TEXT NOT NULL,
                vibe        TEXT,
                category    TEXT NOT NULL,  -- film / music / book / meal / task
                content     TEXT NOT NULL,  -- JSON со списком вариантов
                used_count  INTEGER DEFAULT 0,
                liked_count INTEGER DEFAULT 0,
                updated_at  TEXT NOT NULL,
                UNIQUE(user_id, mood, vibe, category)
            );

            -- Кэш ответов на частые вопросы
            CREATE TABLE IF NOT EXISTS response_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                query_hash  TEXT NOT NULL,   -- hash(user_id + тип запроса + ключ)
                query_type  TEXT NOT NULL,   -- diet / shopping / morning / evening_rec
                context_key TEXT,            -- доп. ключ (mood, vibe, week_num)
                response    TEXT NOT NULL,
                hit_count   INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                UNIQUE(user_id, query_hash)
            );

            -- Паттерны поведения пользователя (анализируется Gemini раз в день)
            CREATE TABLE IF NOT EXISTS user_patterns (
                user_id      INTEGER PRIMARY KEY,
                wake_pattern TEXT,   -- во сколько реально просыпается
                active_hours TEXT,   -- когда больше всего сообщений
                mood_trend   TEXT,   -- частые настроения
                pref_films   TEXT,   -- жанры которые нравятся
                pref_music   TEXT,   -- жанры музыки
                pref_books   TEXT,   -- жанры книг
                skip_list    TEXT,   -- что не понравилось
                insights     TEXT,   -- Gemini-выводы в свободной форме
                updated_at   TEXT
            );

            -- Лог показанного контента (для обучения паттернов)
            CREATE TABLE IF NOT EXISTS content_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                category    TEXT NOT NULL,
                title       TEXT NOT NULL,
                mood        TEXT,
                vibe        TEXT,
                shown_at    TEXT NOT NULL,
                liked       INTEGER DEFAULT NULL  -- NULL=неизвестно, 1=понравилось, 0=нет
            );
            """)
    logger.info("Pattern tables initialized")


# ── ОСНОВНОЙ КЛАСС ────────────────────────────────────────────────────

class PatternCache:
    def __init__(self, user_id: int):
        self.user_id = user_id

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _exec(self, sql: str, params: tuple = ()):
        with _lock:
            with get_conn() as conn:
                conn.execute(sql, params)

    def _fetch_one(self, sql: str, params: tuple = ()):
        with get_conn() as conn:
            return conn.execute(sql, params).fetchone()

    def _fetch_all(self, sql: str, params: tuple = ()):
        with get_conn() as conn:
            return conn.execute(sql, params).fetchall()

    # ── РЕКОМЕНДАЦИИ ──────────────────────────────────────────────────

    def get_recommendation(self, mood: str, vibe: str, category: str) -> Optional[dict]:
        """
        Берёт рекомендацию из кэша.
        Возвращает случайный элемент из списка, исключая уже показанные недавно.
        """
        row = self._fetch_one(
            "SELECT content FROM patterns WHERE user_id=? AND mood=? AND vibe=? AND category=?",
            (self.user_id, mood, vibe, category)
        )
        if not row:
            # Пробуем без vibe
            row = self._fetch_one(
                "SELECT content FROM patterns WHERE user_id=? AND mood=? AND category=? AND vibe IS NULL",
                (self.user_id, mood, category)
            )
        if not row:
            return None

        try:
            items = json.loads(row["content"])
            if not items:
                return None

            # Исключаем недавно показанные (последние 3 дня)
            recent = self._get_recent_shown(category, days=3)
            fresh = [i for i in items if i.get("title") not in recent]
            pool = fresh if fresh else items

            import random
            chosen = random.choice(pool)
            self._log_shown(category, chosen.get("title", ""), mood, vibe)
            self._inc_used(mood, vibe, category)
            return chosen
        except Exception as e:
            logger.error(f"get_recommendation error: {e}")
            return None

    def save_recommendations(self, mood: str, vibe: str, category: str, items: list):
        """Сохраняет список рекомендаций от Gemini в кэш."""
        self._exec(
            """INSERT OR REPLACE INTO patterns
               (user_id, mood, vibe, category, content, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (self.user_id, mood, vibe, category,
             json.dumps(items, ensure_ascii=False), self._now())
        )

    def _get_recent_shown(self, category: str, days: int = 3) -> set:
        since = str(date.today() - timedelta(days=days))
        rows = self._fetch_all(
            "SELECT title FROM content_log WHERE user_id=? AND category=? AND shown_at >= ?",
            (self.user_id, category, since)
        )
        return {r["title"] for r in rows}

    def _log_shown(self, category: str, title: str, mood: str, vibe: str):
        self._exec(
            "INSERT INTO content_log (user_id, category, title, mood, vibe, shown_at) VALUES (?,?,?,?,?,?)",
            (self.user_id, category, title, mood, vibe, self._now())
        )

    def _inc_used(self, mood: str, vibe: str, category: str):
        self._exec(
            "UPDATE patterns SET used_count = used_count + 1 WHERE user_id=? AND mood=? AND vibe=? AND category=?",
            (self.user_id, mood, vibe, category)
        )

    def mark_liked(self, category: str, title: str, liked: bool):
        """Пользователь лайкнул/дизлайкнул — обновляем лог и паттерн."""
        self._exec(
            "UPDATE content_log SET liked=? WHERE user_id=? AND category=? AND title=? ORDER BY shown_at DESC LIMIT 1",
            (1 if liked else 0, self.user_id, category, title)
        )
        if liked:
            self._exec(
                "UPDATE patterns SET liked_count = liked_count + 1 WHERE user_id=? AND category=?",
                (self.user_id, category)
            )
        else:
            # Дизлайк → добавляем в skip_list паттерна
            self._add_to_skip(title)

    def _add_to_skip(self, title: str):
        row = self._fetch_one(
            "SELECT skip_list FROM user_patterns WHERE user_id=?", (self.user_id,)
        )
        skip = json.loads(row["skip_list"]) if row and row["skip_list"] else []
        if title not in skip:
            skip.append(title)
        self._exec(
            "INSERT OR REPLACE INTO user_patterns (user_id, skip_list, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET skip_list=excluded.skip_list, updated_at=excluded.updated_at",
            (self.user_id, json.dumps(skip, ensure_ascii=False), self._now())
        )

    # ── КЭШИРОВАННЫЕ ОТВЕТЫ ───────────────────────────────────────────

    def get_cached_response(self, query_type: str, context_key: str = "") -> Optional[str]:
        """Ищет свежий кэшированный ответ."""
        qhash = f"{query_type}:{context_key}"
        row = self._fetch_one(
            "SELECT response, expires_at, hit_count FROM response_cache "
            "WHERE user_id=? AND query_hash=? AND expires_at > ?",
            (self.user_id, qhash, self._now())
        )
        if not row:
            return None
        # Инкрементируем счётчик попаданий
        self._exec(
            "UPDATE response_cache SET hit_count = hit_count + 1 WHERE user_id=? AND query_hash=?",
            (self.user_id, qhash)
        )
        logger.info(f"Cache HIT: {query_type} hits={row['hit_count']+1}")
        return row["response"]

    def save_cached_response(self, query_type: str, context_key: str,
                              response: str, ttl_days: int = 7):
        """Сохраняет ответ Gemini в кэш на ttl_days дней."""
        qhash = f"{query_type}:{context_key}"
        expires = (datetime.now() + timedelta(days=ttl_days)).strftime("%Y-%m-%d %H:%M:%S")
        self._exec(
            """INSERT OR REPLACE INTO response_cache
               (user_id, query_hash, query_type, context_key, response, created_at, expires_at)
               VALUES (?,?,?,?,?,?,?)""",
            (self.user_id, qhash, query_type, context_key, response, self._now(), expires)
        )
        logger.info(f"Cache SAVE: {query_type} expires={expires}")

    def invalidate(self, query_type: str):
        """Сбросить кэш определённого типа (например при смене профиля)."""
        self._exec(
            "DELETE FROM response_cache WHERE user_id=? AND query_type=?",
            (self.user_id, query_type)
        )

    def invalidate_all(self):
        """Сбросить весь кэш пользователя."""
        self._exec("DELETE FROM response_cache WHERE user_id=?", (self.user_id,))
        self._exec("DELETE FROM patterns WHERE user_id=?", (self.user_id,))

    # ── ПАТТЕРНЫ ПОВЕДЕНИЯ ────────────────────────────────────────────

    def get_user_patterns(self) -> dict:
        row = self._fetch_one(
            "SELECT * FROM user_patterns WHERE user_id=?", (self.user_id,)
        )
        if not row:
            return {}
        return {
            "wake_pattern":  row["wake_pattern"],
            "active_hours":  row["active_hours"],
            "mood_trend":    row["mood_trend"],
            "pref_films":    row["pref_films"],
            "pref_music":    row["pref_music"],
            "pref_books":    row["pref_books"],
            "skip_list":     json.loads(row["skip_list"]) if row["skip_list"] else [],
            "insights":      row["insights"],
            "updated_at":    row["updated_at"],
        }

    def save_user_patterns(self, patterns: dict):
        """Сохраняет паттерны после анализа Gemini."""
        self._exec(
            """INSERT INTO user_patterns
               (user_id, wake_pattern, active_hours, mood_trend,
                pref_films, pref_music, pref_books, skip_list, insights, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 wake_pattern=excluded.wake_pattern,
                 active_hours=excluded.active_hours,
                 mood_trend=excluded.mood_trend,
                 pref_films=excluded.pref_films,
                 pref_music=excluded.pref_music,
                 pref_books=excluded.pref_books,
                 skip_list=COALESCE(excluded.skip_list, user_patterns.skip_list),
                 insights=excluded.insights,
                 updated_at=excluded.updated_at""",
            (
                self.user_id,
                patterns.get("wake_pattern"),
                patterns.get("active_hours"),
                patterns.get("mood_trend"),
                patterns.get("pref_films"),
                patterns.get("pref_music"),
                patterns.get("pref_books"),
                json.dumps(patterns.get("skip_list", []), ensure_ascii=False),
                patterns.get("insights"),
                self._now()
            )
        )

    def needs_pattern_update(self, hours: int = 24) -> bool:
        """Нужно ли обновить паттерны (прошло больше hours часов)?"""
        row = self._fetch_one(
            "SELECT updated_at FROM user_patterns WHERE user_id=?", (self.user_id,)
        )
        if not row or not row["updated_at"]:
            return True
        try:
            last = datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S")
            return (datetime.now() - last).total_seconds() > hours * 3600
        except Exception:
            return True

    # ── СТАТИСТИКА ─────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Статистика кэша для /keys или /admin."""
        cache_rows = self._fetch_all(
            "SELECT query_type, COUNT(*) as cnt, SUM(hit_count) as hits "
            "FROM response_cache WHERE user_id=? GROUP BY query_type",
            (self.user_id,)
        )
        pattern_rows = self._fetch_all(
            "SELECT category, COUNT(*) as cnt, SUM(used_count) as uses "
            "FROM patterns WHERE user_id=? GROUP BY category",
            (self.user_id,)
        )
        return {
            "cache": [dict(r) for r in cache_rows],
            "patterns": [dict(r) for r in pattern_rows],
        }


# ── GEMINI-АНАЛИЗАТОР ПАТТЕРНОВ ───────────────────────────────────────

PATTERN_ANALYSIS_PROMPT = """Ты анализируешь данные пользователя Wingman AI-коуча.

ПРОФИЛЬ:
{profile}

ИСТОРИЯ НАСТРОЕНИЙ (последние 14 дней):
{mood_history}

ЧТО ПОКАЗЫВАЛИ И РЕАКЦИЯ:
{content_history}

ИСТОРИЯ ДИАЛОГОВ (краткая):
{dialog_summary}

Задача: выяви паттерны и заполни JSON строго по шаблону:

{{
  "wake_pattern": "обычно встаёт в X:00",
  "active_hours": "активен с X до Y",
  "mood_trend": "чаще всего настроение: ...",
  "pref_films": "предпочитает жанры: ...",
  "pref_music": "предпочитает: ...",
  "pref_books": "предпочитает: ...",
  "insights": "3-4 конкретных наблюдения о поведении пользователя",
  "rec_films": [
    {{"title": "Название", "genre": "жанр", "why": "почему подходит"}},
    ...5 фильмов...
  ],
  "rec_music": [
    {{"title": "Исполнитель / Плейлист", "genre": "жанр", "mood": "настроение"}},
    ...5 треков...
  ],
  "rec_books": [
    {{"title": "Книга", "author": "Автор", "why": "почему подходит"}},
    ...3 книги...
  ]
}}

Только JSON, без пояснений."""


async def analyze_and_update_patterns(user_id: int):
    """
    Запускается ночью или по /update_patterns.
    Gemini анализирует данные пользователя и обновляет паттерны.
    """
    from core.database import MemoryManager
    from core.gemini_ai import GeminiEngine

    db = MemoryManager(user_id)
    cache = PatternCache(user_id)
    profile = db.get_profile()

    if not profile:
        return

    # Собираем данные для анализа
    mood_history = db.get_last_7_summaries()
    recent_dialogs = db.get_recent_history(limit=30)
    current_patterns = cache.get_user_patterns()
    skip_list = db.get_stop_list()

    # История показанного контента
    with get_conn() as conn:
        content_rows = conn.execute(
            "SELECT category, title, mood, liked, shown_at FROM content_log "
            "WHERE user_id=? ORDER BY shown_at DESC LIMIT 30",
            (user_id,)
        ).fetchall()

    mood_text = "\n".join(
        f"- {s['date']}: {s['mood']} — {s['summary'][:100]}"
        for s in mood_history
    ) or "нет данных"

    content_text = "\n".join(
        f"- [{r['category']}] {r['title']} | настроение: {r['mood']} | "
        f"реакция: {'👍' if r['liked'] == 1 else '👎' if r['liked'] == 0 else '?'}"
        for r in content_rows
    ) or "нет данных"

    dialog_text = "\n".join(
        f"[{m['role']}]: {m['content'][:80]}"
        for m in recent_dialogs[-10:]
    ) or "нет данных"

    prompt = PATTERN_ANALYSIS_PROMPT.format(
        profile=json.dumps(profile, ensure_ascii=False),
        mood_history=mood_text,
        content_history=content_text,
        dialog_summary=dialog_text,
    )

    ai = GeminiEngine(profile)
    try:
        raw = ai._call(prompt, mode="chat")
        # Парсим JSON
        clean = raw.strip()
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        data = json.loads(clean)

        # Сохраняем паттерны поведения
        cache.save_user_patterns({
            "wake_pattern": data.get("wake_pattern"),
            "active_hours": data.get("active_hours"),
            "mood_trend":   data.get("mood_trend"),
            "pref_films":   data.get("pref_films"),
            "pref_music":   data.get("pref_music"),
            "pref_books":   data.get("pref_books"),
            "insights":     data.get("insights"),
            "skip_list":    skip_list,
        })

        # Сохраняем рекомендации в паттерн-кэш по текущему настроению
        current_mood = db.get_mood() or "neutral"
        current_vibe = db.get_vibe() or "observer"

        if data.get("rec_films"):
            cache.save_recommendations(current_mood, current_vibe, "film", data["rec_films"])
        if data.get("rec_music"):
            cache.save_recommendations(current_mood, current_vibe, "music", data["rec_music"])
        if data.get("rec_books"):
            cache.save_recommendations(current_mood, current_vibe, "book", data["rec_books"])

        logger.info(f"Patterns updated for user {user_id}")
        return data.get("insights", "Паттерны обновлены")

    except Exception as e:
        logger.error(f"Pattern analysis failed for {user_id}: {e}")
        return None
