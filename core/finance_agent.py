# -*- coding: utf-8 -*-
"""
core/finance_agent.py
FinanceAgent v1 — финансовые цели, расходы, аналитика.
"""

from __future__ import annotations
import logging
from datetime import datetime, date, timedelta
from core.db_extensions import (
    add_finance_goal, get_finance_goals, update_goal_progress,
    add_txn, get_month_stats
)

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """Ты личный финансовый советник. Говоришь просто, конкретно, без воды.

ПРОФИЛЬ: {profile}
LIFEMODE: {lifemode}

РАСХОДЫ ЗА МЕСЯЦ:
{expenses}

ДОХОДЫ ЗА МЕСЯЦ:
{income}

ФИНАНСОВЫЕ ЦЕЛИ:
{goals}

Дай 3-5 конкретных совета. Называй реальные суммы. Формат каждого совета:
💡 [категория]: [конкретный совет с цифрами]

В конце — краткий вывод: идёт ли пользователь к цели или нет."""

GOAL_ADVICE_PROMPT = """Пользователь хочет накопить {target}₽ к {deadline}.
Текущие накопления: {current}₽.
Осталось: {remaining}₽.
Дней до цели: {days_left}.
Нужно откладывать в день: {per_day}₽.

Текущие расходы в месяц: {monthly_expense}₽.
Доходы в месяц: {monthly_income}₽.

Цель: {title}

Дай 1-2 конкретных рекомендации как ускорить накопление. Укажи на какой категории расходов можно сэкономить."""


class FinanceAgent:
    def __init__(self, user_id: int, profile: dict = None):
        self.user_id = user_id
        self.profile = profile or {}

    def _lifemode(self) -> str:
        try:
            from core.lifemode_agent import LifeModeAgent
            return LifeModeAgent(self.user_id).get_finance_context()
        except Exception:
            return ""

    def add_goal(self, title: str, target: float,
                 emoji: str = "🎯", deadline: str = None) -> int:
        return add_finance_goal(self.user_id, title, target, emoji, deadline)

    def add_income(self, amount: float, category: str = "salary", note: str = ""):
        add_txn(self.user_id, amount, "income", category, note)

    def add_expense(self, amount: float, category: str = "food", note: str = ""):
        add_txn(self.user_id, amount, "expense", category, note)

    def contribute_to_goal(self, goal_id: int, amount: float):
        update_goal_progress(goal_id, amount)
        add_txn(self.user_id, amount, "expense", "savings", f"цель #{goal_id}")

    def get_goals(self) -> list:
        return get_finance_goals(self.user_id)

    def get_month(self) -> dict:
        return get_month_stats(self.user_id)

    def goals_summary(self) -> str:
        goals = self.get_goals()
        if not goals:
            return "Финансовых целей пока нет. Добавь командой /addgoal"
        lines = ["💰 *Финансовые цели:*\n"]
        for g in goals:
            pct = int(g["current_amt"] / g["target_amt"] * 100) if g["target_amt"] > 0 else 0
            bar = "▓" * (pct // 10) + "░" * (10 - pct // 10)
            remaining = g["target_amt"] - g["current_amt"]
            lines.append(
                f"{g['emoji']} *{g['title']}*\n"
                f"`{bar}` {pct}%\n"
                f"Накоплено: {g['current_amt']:.0f}₽ / {g['target_amt']:.0f}₽\n"
                f"Осталось: {remaining:.0f}₽"
            )
            if g.get("deadline"):
                try:
                    dl = date.fromisoformat(g["deadline"])
                    days = (dl - date.today()).days
                    if days > 0:
                        per_day = remaining / days
                        lines.append(f"⏳ {days} дней → {per_day:.0f}₽/день")
                except Exception:
                    pass
            lines.append("")
        return "\n".join(lines)

    def month_summary(self) -> str:
        stats = self.get_month()
        month_name = datetime.now().strftime("%B %Y")
        lines = [f"📊 *Финансы за {month_name}*\n"]

        total_in = stats["total_income"]
        total_out = stats["total_expense"]
        balance = stats["balance"]

        lines.append(f"💚 Доходы: {total_in:.0f}₽")
        lines.append(f"🔴 Расходы: {total_out:.0f}₽")
        bal_emoji = "✅" if balance >= 0 else "⚠️"
        lines.append(f"{bal_emoji} Баланс: {balance:+.0f}₽\n")

        if stats["expense"]:
            lines.append("*Расходы по категориям:*")
            for cat, amt in sorted(stats["expense"].items(), key=lambda x: -x[1]):
                cat_labels = {
                    "food": "🛒 Продукты", "transport": "🚗 Транспорт",
                    "cafe": "☕ Кафе/рестораны", "entertainment": "🎬 Развлечения",
                    "health": "💊 Здоровье", "clothing": "👕 Одежда",
                    "savings": "💰 Накопления", "other": "📦 Прочее",
                }
                label = cat_labels.get(cat, cat)
                lines.append(f"  {label}: {amt:.0f}₽")

        return "\n".join(lines)

    async def get_analysis(self) -> str:
        """Аналитика расходов с советами от AI."""
        from core.provider_manager import generate as pm_gen

        stats = self.get_month()
        goals = self.get_goals()

        goals_str = "\n".join(
            f"- {g['emoji']} {g['title']}: {g['current_amt']:.0f}/{g['target_amt']:.0f}₽"
            for g in goals
        ) or "нет целей"

        expenses_str = "\n".join(
            f"- {cat}: {amt:.0f}₽"
            for cat, amt in stats["expense"].items()
        ) or "нет данных"

        income_str = "\n".join(
            f"- {cat}: {amt:.0f}₽"
            for cat, amt in stats["income"].items()
        ) or "нет данных"

        profile_str = (
            f"имя: {self.profile.get('name','')}, "
            f"город: {self.profile.get('city','')}, "
            f"бюджет/день: {self.profile.get('budget','?')}"
        )

        return await pm_gen(
            ANALYSIS_PROMPT.format(
                profile=profile_str,
                lifemode=self._lifemode(),
                expenses=expenses_str,
                income=income_str,
                goals=goals_str,
            ),
            mode="chat"
        )

    async def get_goal_advice(self, goal: dict) -> str:
        """Совет как быстрее накопить на конкретную цель."""
        from core.provider_manager import generate as pm_gen

        remaining = goal["target_amt"] - goal["current_amt"]
        days_left = 999
        if goal.get("deadline"):
            try:
                dl = date.fromisoformat(goal["deadline"])
                days_left = max(1, (dl - date.today()).days)
            except Exception:
                pass

        per_day = remaining / days_left if days_left < 999 else 0
        stats = self.get_month()

        return await pm_gen(
            GOAL_ADVICE_PROMPT.format(
                title=goal["title"],
                target=goal["target_amt"],
                deadline=goal.get("deadline", "не задан"),
                current=goal["current_amt"],
                remaining=remaining,
                days_left=days_left,
                per_day=f"{per_day:.0f}" if per_day > 0 else "не задано",
                monthly_expense=stats["total_expense"],
                monthly_income=stats["total_income"],
            ),
            mode="chat"
        )


# ── Категории расходов ────────────────────────────────────────────────────

EXPENSE_CATEGORIES = {
    "food":          ("🛒", "Продукты"),
    "cafe":          ("☕", "Кафе / рестораны"),
    "transport":     ("🚗", "Транспорт / бензин"),
    "health":        ("💊", "Здоровье / аптека"),
    "entertainment": ("🎬", "Развлечения"),
    "clothing":      ("👕", "Одежда"),
    "savings":       ("💰", "Накопления"),
    "other":         ("📦", "Прочее"),
}

INCOME_CATEGORIES = {
    "salary":    ("💼", "Зарплата"),
    "freelance": ("💻", "Фриланс"),
    "other":     ("💸", "Прочее"),
}
