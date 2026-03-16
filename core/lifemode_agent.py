# -*- coding: utf-8 -*-
"""
core/lifemode_agent.py
LifeModeAgent v1 — центральный дирижёр режимов.

Режимы: cut (сушка), bulk (масса), health (здоровье),
        energy (энергия), detox (детокс), vacation (отпуск)

Управляет промптами всех агентов через build_context().
"""

from __future__ import annotations
import logging
from core.db_extensions import get_life_mode, set_life_mode

logger = logging.getLogger(__name__)

# ── Конфигурация режимов ──────────────────────────────────────────────────

MODES = {
    "cut": {
        "label": "🔥 Сушка",
        "diet_hint":    "Дефицит калорий -20% от TDEE. Приоритет белка (2г/кг). Минимум простых углеводов. Дешёвые источники белка: яйца, творог, куриное филе.",
        "fitness_hint": "Кардио 3-4 раза в неделю 30-40 минут. Силовые для сохранения мышц. Не пропускать белковую еду после тренировки.",
        "finance_hint": "Оптимизировать расходы на питание. Избегать дорогих ресторанов. Считать каждую калорию и каждый рубль.",
        "content_hint": "Мотивационные документалки, спортивные драмы, истории трансформации. Музыка: энергичная, драйвовая.",
        "psych_hint":   "Пользователь в режиме самодисциплины. Поддерживать мотивацию. При срывах — не осуждать, анализировать триггер.",
        "control_default": "moderate",
        "emoji": "🔥",
    },
    "bulk": {
        "label": "💪 Набор массы",
        "diet_hint":    "Профицит калорий +15% от TDEE. Много белка и сложных углеводов. Мясо, рыба, крупы, бобовые. 5-6 приёмов пищи.",
        "fitness_hint": "Силовые тренировки 4-5 раз в неделю. Базовые упражнения: присед, жим, тяга. Кардио минимально.",
        "finance_hint": "Бюджет на качественный белок. Спортивное питание если есть возможность. Покупать оптом.",
        "content_hint": "Образовательный контент о тренировках, питании, физиологии. Биографии спортсменов.",
        "psych_hint":   "Долгосрочная цель. Поддерживать терпение — результат не мгновенный.",
        "control_default": "soft",
        "emoji": "💪",
    },
    "health": {
        "label": "❤️ Здоровье",
        "diet_hint":    "Сбалансированное питание. Разнообразие продуктов. Больше овощей и фруктов. Без жёстких ограничений.",
        "fitness_hint": "Ходьба 7000+ шагов в день. Лёгкая растяжка. Любая активность которая нравится.",
        "finance_hint": "Без особых ограничений. Приоритет качественным продуктам.",
        "content_hint": "Разнообразный контент. Что-то для ума, что-то для отдыха.",
        "psych_hint":   "Режим баланса. Поддерживать позитивный настрой без давления.",
        "control_default": "soft",
        "emoji": "❤️",
    },
    "energy": {
        "label": "⚡ Энергия",
        "diet_hint":    "Низкий гликемический индекс. Дробное питание 5-6 раз. Сложные углеводы, орехи, ягоды. Меньше сахара и кофеина после 15:00.",
        "fitness_hint": "Лёгкая аэробная активность. Зарядка утром. Прогулки в обеденный перерыв.",
        "finance_hint": "Инвестировать в качественное питание и сон. Это повышает продуктивность.",
        "content_hint": "Подкасты о продуктивности, биографии успешных людей. Музыка для концентрации.",
        "psych_hint":   "Фокус на продуктивности и ресурсном состоянии. Напоминать о важности отдыха.",
        "control_default": "soft",
        "emoji": "⚡",
    },
    "detox": {
        "label": "🧘 Детокс",
        "diet_hint":    "Овощи, фрукты, вода 2+ литра. Без алкоголя, фастфуда, обработанных продуктов. Лёгкое и чистое питание.",
        "fitness_hint": "Йога, медитация, лёгкие прогулки на природе. Без интенсивных нагрузок.",
        "finance_hint": "Минимизация ненужных трат. Осознанное потребление.",
        "content_hint": "Спокойное кино, медитативная музыка, книги об осознанности.",
        "psych_hint":   "Режим восстановления. Без лишнего давления. Поддерживать ощущение покоя.",
        "control_default": "soft",
        "emoji": "🧘",
    },
    "vacation": {
        "label": "✈️ Подготовка к отпуску",
        "diet_hint":    "Лёгкая подготовка тела к поездке. Без жёстких ограничений. Акцент на энергии и самочувствии.",
        "fitness_hint": "Подготовить тело к активному отдыху. Ходьба, плавание, лёгкие тренировки.",
        "finance_hint": "ПРИОРИТЕТ: накопление на отпуск. Анализировать все расходы. Находить возможности сэкономить.",
        "content_hint": "Контент о путешествиях, культуре дестинации, лайфхаки для путешественников.",
        "psych_hint":   "Мотивация через предвкушение. Визуализировать цель — отпуск близко.",
        "control_default": "moderate",
        "emoji": "✈️",
    },
}

CONTROL_LEVELS = {
    "soft":     "Мягкие рекомендации. Не напоминать об ошибках.",
    "moderate": "Умеренный контроль. Замечать отклонения, но не давить.",
    "strict":   "Жёсткий контроль. Активно возвращать к цели. Называть отклонения прямо.",
}

MODE_LABELS_RU = {
    "cut": "🔥 Сушка", "bulk": "💪 Масса", "health": "❤️ Здоровье",
    "energy": "⚡ Энергия", "detox": "🧘 Детокс", "vacation": "✈️ Отпуск",
}


class LifeModeAgent:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self._data = get_life_mode(user_id)

    @property
    def mode(self) -> str:
        return self._data.get("mode", "health")

    @property
    def control(self) -> str:
        return self._data.get("control", "soft")

    @property
    def config(self) -> dict:
        return MODES.get(self.mode, MODES["health"])

    def set(self, mode: str, control: str = None, until: str = None):
        cfg = MODES.get(mode, MODES["health"])
        ctrl = control or cfg["control_default"]
        set_life_mode(self.user_id, mode, ctrl, until)
        self._data = {"mode": mode, "control": ctrl, "until": until}

    def build_context(self) -> str:
        """Строит строку-контекст для инжекции в промпты агентов."""
        cfg = self.config
        ctrl_desc = CONTROL_LEVELS.get(self.control, "")
        return (
            f"[LIFEMODE: {cfg['label']} | КОНТРОЛЬ: {self.control.upper()}]\n"
            f"Питание: {cfg['diet_hint']}\n"
            f"Фитнес: {cfg['fitness_hint']}\n"
            f"Финансы: {cfg['finance_hint']}\n"
            f"Психология: {cfg['psych_hint']}\n"
            f"Уровень контроля: {ctrl_desc}"
        )

    def get_diet_context(self) -> str:
        return self.config["diet_hint"]

    def get_content_context(self) -> str:
        return self.config["content_hint"]

    def get_finance_context(self) -> str:
        return self.config["finance_hint"]

    def get_psych_tone(self) -> str:
        return self.config["psych_hint"]

    def label(self) -> str:
        return self.config["label"]

    def status_text(self) -> str:
        cfg = self.config
        until = self._data.get("until")
        until_str = f" (до {until})" if until else ""
        return (
            f"{cfg['emoji']} *Режим: {cfg['label']}*{until_str}\n"
            f"Контроль: {self.control}\n\n"
            f"🥗 {cfg['diet_hint'][:80]}...\n"
            f"🏋️ {cfg['fitness_hint'][:80]}..."
        )
