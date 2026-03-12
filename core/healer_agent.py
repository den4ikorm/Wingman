# -*- coding: utf-8 -*-
"""
core/healer_agent.py  v2 — без Railway API
Ловит ошибки через Python logging handler внутри бота.
Нужны только: GITHUB_TOKEN + GITHUB_REPO
"""

import os, re, base64, hashlib, logging, py_compile, tempfile, traceback
from collections import deque
from datetime import datetime, date
import requests

logger = logging.getLogger(__name__)

GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO   = os.getenv("GITHUB_REPO", "den4ikorm/Wingman")
ADMIN_ID      = int(os.getenv("ADMIN_ID", "7709651193"))
MAX_PATCHES_PER_DAY    = 5
MAX_ATTEMPTS_PER_ERROR = 3

PROTECTED_FILES = {
    "core/database.py", "core/healer_agent.py",
    "bot/config.py", "bot/main.py",
    "requirements.txt", "Procfile", "nixpacks.toml",
}


# ── LOG HANDLER ───────────────────────────────────────────────────────────────

class ErrorLogHandler(logging.Handler):
    """Перехватывает ERROR/CRITICAL логи и передаёт в HealerAgent."""

    def __init__(self, healer_ref):
        super().__init__(level=logging.ERROR)
        self.healer = healer_ref
        self._buffer: deque = deque(maxlen=50)
        self._processing: set = set()

    def emit(self, record: logging.LogRecord):
        try:
            if "healer" in record.name.lower():
                return
            msg = self.format(record)
            exc_text = ""
            if record.exc_info:
                exc_text = "".join(traceback.format_exception(*record.exc_info))
            full = exc_text or msg
            tb_hash = hashlib.md5(full[:400].encode()).hexdigest()[:12]
            if tb_hash in self._processing:
                return
            entry = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "name": record.name, "level": record.levelname,
                "message": msg, "exc": exc_text, "hash": tb_hash,
            }
            self._buffer.append(entry)
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.healer.handle_error(entry))
            except RuntimeError:
                pass
        except Exception:
            pass

    def get_recent(self, n=10):
        return list(self._buffer)[-n:]


# ── CLASSIFIER ────────────────────────────────────────────────────────────────

def classify_error(text: str) -> dict:
    result = {"healable": False, "category": "unknown",
              "file": None, "line": None, "error": None}
    for pat in [r"MemoryError", r"RecursionError", r"SystemExit",
                r"ConnectionRefused", r"TimeoutError", r"429",
                r"rate.?limit", r"TelegramRetry", r"NetworkError"]:
        if re.search(pat, text, re.IGNORECASE):
            result["category"] = "infrastructure"
            return result
    for pat in [r"NameError", r"AttributeError", r"TypeError",
                r"KeyError", r"IndexError", r"ValueError",
                r"ImportError", r"ModuleNotFoundError",
                r"UnboundLocalError", r"JSONDecodeError", r"SyntaxError"]:
        if re.search(pat, text):
            result["healable"] = True
            result["category"] = "code_bug"
            break
    m = re.findall(r'File "/app/([^"]+)", line (\d+)', text)
    if m:
        result["file"] = m[-1][0]
        result["line"] = int(m[-1][1])
    e = re.search(r'(\w+(?:Error|Exception)): (.+)', text)
    if e:
        result["error"] = f"{e.group(1)}: {e.group(2)[:120]}"
    if result["file"] and result["file"] in PROTECTED_FILES:
        result["healable"] = False
        result["category"] = "protected_file"
    return result


# ── GITHUB CLIENT ─────────────────────────────────────────────────────────────

class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self):
        self.h = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_file(self, path: str, branch="main") -> dict:
        r = requests.get(f"{self.BASE}/repos/{GITHUB_REPO}/contents/{path}?ref={branch}",
                         headers=self.h, timeout=15)
        r.raise_for_status()
        d = r.json()
        return {"content": base64.b64decode(d["content"]).decode(), "sha": d["sha"]}

    def get_head_sha(self, branch="main") -> str:
        r = requests.get(f"{self.BASE}/repos/{GITHUB_REPO}/git/ref/heads/{branch}",
                         headers=self.h, timeout=15)
        r.raise_for_status()
        return r.json()["object"]["sha"]

    def create_branch(self, name: str, sha: str) -> bool:
        r = requests.post(f"{self.BASE}/repos/{GITHUB_REPO}/git/refs",
                          headers=self.h,
                          json={"ref": f"refs/heads/{name}", "sha": sha}, timeout=15)
        return r.status_code in (201, 422)

    def push_file(self, path, content, message, branch, sha) -> bool:
        r = requests.put(f"{self.BASE}/repos/{GITHUB_REPO}/contents/{path}",
                         headers=self.h,
                         json={"message": message,
                               "content": base64.b64encode(content.encode()).decode(),
                               "branch": branch, "sha": sha}, timeout=15)
        return r.status_code in (200, 201)

    def create_pr(self, title, head, body="") -> dict:
        r = requests.post(f"{self.BASE}/repos/{GITHUB_REPO}/pulls",
                          headers=self.h,
                          json={"title": title, "head": head,
                                "base": "main", "body": body}, timeout=15)
        r.raise_for_status()
        return r.json()

    def merge_pr(self, pr_number: int) -> bool:
        r = requests.put(f"{self.BASE}/repos/{GITHUB_REPO}/pulls/{pr_number}/merge",
                         headers=self.h, json={"merge_method": "squash"}, timeout=15)
        return r.status_code == 200

    def revert_to_sha(self, sha: str, branch="main") -> bool:
        r = requests.patch(f"{self.BASE}/repos/{GITHUB_REPO}/git/refs/heads/{branch}",
                           headers=self.h, json={"sha": sha, "force": True}, timeout=15)
        return r.status_code == 200


# ── GEMINI SURGEON ────────────────────────────────────────────────────────────

def gemini_patch(file_content: str, error_text: str, info: dict, file_path: str):
    try:
        from core.key_manager import KeyManager
        from google import genai
        client = genai.Client(api_key=KeyManager().get_key())
        prompt = (
            f"Ты Python-разработчик. Исправь баг.\n\n"
            f"ФАЙЛ: {file_path}\nСТРОКА: {info.get('line','?')}\n"
            f"ОШИБКА: {info.get('error','?')}\n\n"
            f"TRACEBACK:\n{error_text[-1500:]}\n\n"
            f"КОД:\n```python\n{file_content[:6000]}\n```\n\n"
            f"Верни ТОЛЬКО полный исправленный файл. Без пояснений. Без ```."
        )
        resp = client.models.generate_content(
            model="gemini-2.0-flash", contents=prompt,
            config={"max_output_tokens": 8192}
        )
        code = re.sub(r'^```\w*\n?', '', resp.text.strip())
        code = re.sub(r'\n?```$', '', code)
        return code.strip()
    except Exception as e:
        logger.error(f"Gemini Surgeon: {e}")
        return None


def validate_syntax(code: str) -> tuple:
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py',
                                     delete=False, encoding='utf-8') as f:
        f.write(code); tmp = f.name
    try:
        py_compile.compile(tmp, doraise=True)
        return True, ""
    except py_compile.PyCompileError as e:
        return False, str(e)
    finally:
        os.unlink(tmp)


# ── HEALING LOG ───────────────────────────────────────────────────────────────

class HealingLog:
    def __init__(self):
        self.path = os.getenv("DB_PATH", "./data/wingman.db")
        self._init()

    def _c(self):
        import sqlite3
        c = sqlite3.connect(self.path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._c() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS healing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                traceback_hash TEXT, error_type TEXT, file_path TEXT,
                branch_name TEXT, pr_number INTEGER,
                status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 1,
                created_at TEXT, resolved_at TEXT)""")

    def attempts(self, h: str) -> int:
        with self._c() as c:
            r = c.execute("SELECT attempts FROM healing_log WHERE traceback_hash=? "
                          "ORDER BY created_at DESC LIMIT 1", (h,)).fetchone()
            return r["attempts"] if r else 0

    def today_count(self) -> int:
        with self._c() as c:
            r = c.execute("SELECT COUNT(*) n FROM healing_log WHERE created_at LIKE ?",
                          (f"{date.today().isoformat()}%",)).fetchone()
            return r["n"] if r else 0

    def add(self, tb_hash, error_type, file_path, branch=None, pr_number=None) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._c() as c:
            cur = c.execute(
                "INSERT INTO healing_log (traceback_hash,error_type,file_path,"
                "branch_name,pr_number,status,attempts,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (tb_hash, error_type, file_path, branch, pr_number,
                 "pending", self.attempts(tb_hash)+1, now))
            return cur.lastrowid

    def set_status(self, lid: int, status: str):
        with self._c() as c:
            c.execute("UPDATE healing_log SET status=?,resolved_at=? WHERE id=?",
                      (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), lid))

    def pending(self):
        with self._c() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM healing_log WHERE status='pending' "
                "ORDER BY created_at DESC LIMIT 10").fetchall()]

    def history(self, n=10):
        with self._c() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM healing_log ORDER BY created_at DESC LIMIT ?", (n,)
            ).fetchall()]


# ── ГЛАВНЫЙ АГЕНТ ─────────────────────────────────────────────────────────────

class HealerAgent:
    def __init__(self, bot=None):
        self.bot     = bot
        self.gh      = GitHubClient()
        self.log_db  = HealingLog()
        self.enabled = True
        self._last_good_sha = None
        # Вешаем handler на root logger
        self._handler = ErrorLogHandler(self)
        fmt = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
        self._handler.setFormatter(fmt)
        logging.getLogger().addHandler(self._handler)
        logger.info("HealerAgent v2: log handler attached ✓")

    async def handle_error(self, entry: dict):
        if not self.enabled or not GITHUB_TOKEN:
            return
        full = entry.get("exc") or entry.get("message", "")
        tb_hash = entry.get("hash", "")
        if self.log_db.today_count() >= MAX_PATCHES_PER_DAY:
            return
        if self.log_db.attempts(tb_hash) >= MAX_ATTEMPTS_PER_ERROR:
            return
        info = classify_error(full)
        if not info["healable"]:
            return
        if not info.get("file"):
            return
        self._handler._processing.add(tb_hash)
        try:
            await self._heal(full, tb_hash, info)
        finally:
            self._handler._processing.discard(tb_hash)

    async def _heal(self, error_text: str, tb_hash: str, info: dict):
        file_path = info["file"]
        logger.info(f"HealerAgent: healing {file_path}")
        try:
            self._last_good_sha = self.gh.get_head_sha()
            file_data = self.gh.get_file(file_path)
            patched = gemini_patch(file_data["content"], error_text, info, file_path)
            if not patched:
                return
            ok, err = validate_syntax(patched)
            if not ok:
                await self._notify(f"🔧 Нашёл баг в `{file_path}`, патч не прошёл синтаксис:\n`{err}`", md=True)
                return
            ts = datetime.now().strftime("%m%d-%H%M")
            branch = f"fix/auto-{ts}"
            self.gh.create_branch(branch, self._last_good_sha)
            pushed = self.gh.push_file(file_path, patched,
                f"fix: auto-heal {info.get('error','bug')[:60]}", branch, file_data["sha"])
            if not pushed:
                await self._notify("❌ HealerAgent: push failed")
                return
            pr = self.gh.create_pr(
                title=f"🔧 Auto-fix: {info.get('error','bug')[:80]}",
                head=branch,
                body=f"**Файл:** `{file_path}` строка {info.get('line','?')}\n"
                     f"**Ошибка:** `{info.get('error','?')}` \n\n```\n{error_text[-500:]}\n```"
            )
            lid = self.log_db.add(tb_hash, info.get("error","?"), file_path,
                                  branch=branch, pr_number=pr.get("number"))
            await self._notify_ready(lid, pr.get("number"), pr.get("html_url",""), info)
        except Exception as e:
            logger.error(f"HealerAgent._heal: {e}", exc_info=True)

    async def approve(self, log_id: int, pr_number: int):
        if self.gh.merge_pr(pr_number):
            self.log_db.set_status(log_id, "merged")
            await self._notify(f"✅ Патч #{pr_number} применён! Деплой через ~2 мин.")
            import asyncio; await asyncio.sleep(300)
            recent_errors = [e for e in self._handler.get_recent(5)
                             if e["level"] in ("ERROR","CRITICAL")]
            if recent_errors:
                self.log_db.set_status(log_id, "regression")
                await self._notify("⚠️ Новые ошибки после патча! /healer rollback")
            else:
                self.log_db.set_status(log_id, "resolved")
                await self._notify("✅ Патч работает — ошибок нет!")
        else:
            await self._notify(f"❌ Не удалось смёрджить PR #{pr_number}")

    async def reject(self, log_id: int):
        self.log_db.set_status(log_id, "rejected")
        await self._notify("Патч отклонён.")

    async def rollback(self):
        if not self._last_good_sha:
            await self._notify("⚠️ SHA неизвестен — откатывай вручную.")
            return
        ok = self.gh.revert_to_sha(self._last_good_sha)
        await self._notify("✅ Откат выполнен!" if ok else "❌ Откат не удался.")

    async def _notify(self, text: str, md=False):
        if not self.bot: return
        try:
            from aiogram.enums import ParseMode
            await self.bot.send_message(ADMIN_ID, text,
                parse_mode=ParseMode.MARKDOWN if md else None)
        except Exception as e:
            logger.error(f"HealerAgent notify: {e}")

    async def _notify_ready(self, log_id, pr_number, pr_url, info):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Применить",
                callback_data=f"healer_approve_{log_id}_{pr_number}"),
            InlineKeyboardButton(text="❌ Отклонить",
                callback_data=f"healer_reject_{log_id}"),
        ],[
            InlineKeyboardButton(text="🔄 Откатить",
                callback_data="healer_rollback"),
        ]])
        text = (f"🔧 *Лечилка исправила баг*\n\n"
                f"📄 `{info.get('file','?')}` строка {info.get('line','?')}\n"
                f"⚠️ `{info.get('error','?')}` \n\n"
                f"[PR →]({pr_url})\n\nПрименить?")
        try:
            await self.bot.send_message(ADMIN_ID, text, parse_mode="Markdown",
                reply_markup=kb, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"notify_ready: {e}")

    async def cmd_status(self) -> str:
        return (f"🔧 *HealerAgent v2*\n\n"
                f"Статус: {'✅ активен' if self.enabled else '⏸ пауза'}\n"
                f"GitHub: {'✅' if GITHUB_TOKEN else '❌ нет токена'}\n"
                f"Патчей сегодня: {self.log_db.today_count()}/{MAX_PATCHES_PER_DAY}\n"
                f"Ожидают: {len(self.log_db.pending())}\n\n"
                f"_Ловит ошибки через logging автоматически_")

    async def cmd_history(self) -> str:
        items = self.log_db.history(10)
        if not items: return "Патчей пока не было."
        icons = {"pending":"🕐","merged":"✅","rejected":"❌","resolved":"🟢","regression":"🔴"}
        lines = ["📋 *История:*\n"]
        for h in items:
            lines.append(f"{icons.get(h['status'],'❓')} `{h['file_path']}` {h['created_at'][:16]}")
        return "\n".join(lines)
