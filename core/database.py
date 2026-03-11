"""
core/database.py
MemoryManager v2 — расширен для Wingman (emotional_state, stop_list, memory_light)
"""

import json
import os
from datetime import datetime


class MemoryManager:
    def __init__(self, user_id: int):
        self.user_id = user_id
        base_dir = os.getenv("BASE_DIR", "./data")
        self.profile_path = os.path.join(base_dir, "profiles", f"{user_id}.json")
        self.insights_path = os.path.join(base_dir, "insights", f"{user_id}.txt")

        os.makedirs(os.path.dirname(self.profile_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.insights_path), exist_ok=True)

    # ── PROFILE ────────────────────────────────────────────────────

    def get_profile(self) -> dict:
        if os.path.exists(self.profile_path):
            with open(self.profile_path, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except Exception:
                    return {}
        return {}

    def save_profile(self, data: dict):
        existing = self.get_profile()
        existing.update(data)
        existing["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.profile_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=4)

    # ── VIBE ───────────────────────────────────────────────────────

    def set_vibe(self, vibe: str):
        self.save_profile({"current_vibe": vibe})

    def get_vibe(self) -> str:
        return self.get_profile().get("current_vibe", "observer")

    def get_vibe_css(self) -> str:
        mapping = {
            "spark":    "style_spark.css",
            "observer": "style_observer.css",
            "twilight": "style_twilight.css",
        }
        return mapping.get(self.get_vibe(), "style_observer.css")

    # ── EMOTIONAL STATE ────────────────────────────────────────────

    def set_mood(self, mood: str):
        """mood: upbeat | neutral | low"""
        self.save_profile({"emotional_state": mood})

    def get_mood(self) -> str:
        return self.get_profile().get("emotional_state", "neutral")

    # ── STOP LIST (уже видел/слышал) ───────────────────────────────

    def add_to_stop_list(self, item: str):
        profile = self.get_profile()
        stop_list = profile.get("stop_list", [])
        if item not in stop_list:
            stop_list.append(item)
        self.save_profile({"stop_list": stop_list})

    def get_stop_list(self) -> list:
        return self.get_profile().get("stop_list", [])

    # ── MEMORY LIGHT (вкусовые предпочтения) ───────────────────────

    def update_memory_light(self, key: str, value):
        """Мягкое обновление вкусовых предпочтений"""
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

    # ── INSIGHTS / FEATURE LOG ─────────────────────────────────────

    def log_insight(self, text: str):
        with open(self.insights_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now()} ---\n{text}\n")

    # ── TASKS ──────────────────────────────────────────────────────────────

    def save_tasks(self, tasks: list):
        self.save_profile({"today_tasks": tasks})

    def get_tasks(self) -> list:
        return self.get_profile().get("today_tasks", [])

    def add_user_task(self, task: str):
        tasks = self.get_tasks()
        if len(tasks) < 10:
            tasks.append(task)
            self.save_tasks(tasks)
            return True
        return False

    # ── SURPRISE TOGGLE ────────────────────────────────────────────────────

    def toggle_surprise(self, enabled: bool):
        self.save_profile({"surprise_enabled": enabled})

    # ── STREAK ─────────────────────────────────────────────────────────────

    def update_streak(self):
        from datetime import date
        profile = self.get_profile()
        last = profile.get("last_checkin")
        streak = profile.get("streak", 0)
        today = str(date.today())

        if last == today:
            return streak
        from datetime import date, timedelta
        yesterday = str(date.today() - timedelta(days=1))
        if last == yesterday:
            streak += 1
        else:
            streak = 1
        self.save_profile({"streak": streak, "last_checkin": today})
        return streak

    def get_streak(self) -> int:
        return self.get_profile().get("streak", 0)
