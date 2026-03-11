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

    # --- PROFILE ---

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

    # --- VIBE ---

    def set_vibe(self, vibe: str):
        self.save_profile({"current_vibe": vibe})

    def get_vibe(self) -> str:
        return self.get_profile().get("current_vibe", "observer")

    def get_vibe_css(self) -> str:
        mapping = {
            "spark": "style_spark.css",
            "observer": "style_observer.css",
            "twilight": "style_twilight.css",
        }
        return mapping.get(self.get_vibe(), "style_observer.css")

    # --- PLAN ---

    def save_last_plan(self, html: str):
        self.save_profile({"last_plan_html": html})

    def get_last_plan(self) -> str:
        return self.get_profile().get("last_plan_html", "")

    # --- REPORT FLAG ---

    def mark_report_pending(self, status: bool):
        self.save_profile({"report_pending": status})

    def is_report_pending(self) -> bool:
        return self.get_profile().get("report_pending", False)

    # --- INSIGHTS ---

    def log_insight(self, text: str):
        with open(self.insights_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now()} ---\n{text}\n")
