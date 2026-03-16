# -*- coding: utf-8 -*-
"""
core/receipt_agent.py
ReceiptAgent v1 — OCR чеков через Gemini Vision.

Фото чека → JSON позиций → база цен → советы где дешевле.
"""

from __future__ import annotations
import json
import logging
import base64
from core.db_extensions import save_receipt, get_price_compare

logger = logging.getLogger(__name__)

OCR_PROMPT = """Ты OCR-агент для чеков. Извлеки данные из фотографии чека.

Верни ТОЛЬКО валидный JSON без пояснений:
{
  "store": "название магазина или пустая строка",
  "city": "город если есть или пустая строка",
  "date": "дата в формате YYYY-MM-DD или пустая строка",
  "total": числовая сумма или 0,
  "items": [
    {"name": "название продукта", "price": числовая цена, "qty": количество или 1}
  ]
}

Если не можешь распознать — верни {"error": "не удалось распознать чек"}
Нормализуй названия: "Молоко 3.2% 1л" → так и оставь, убери только лишние пробелы."""

ADVICE_PROMPT = """Ты финансовый советник по продуктам питания.

Данные о ценах пользователя по продуктам:
{price_data}

Город: {city}
Режим жизни: {lifemode}

Дай 2-3 конкретных совета где выгоднее покупать. Формат:
💡 [Продукт]: в [Магазин1] — X₽, в [Магазин2] — Y₽. Экономия: Z₽/мес.

Только если есть реальные данные для сравнения. Без воды."""


class ReceiptAgent:
    def __init__(self, user_id: int, profile: dict = None):
        self.user_id = user_id
        self.profile = profile or {}

    async def parse_photo(self, photo_bytes: bytes) -> dict:
        """OCR фото чека через Gemini Vision."""
        try:
            from core.key_manager import KeyManager
            from google import genai

            km = KeyManager()
            client = genai.Client(api_key=km.get_key())

            # Кодируем фото в base64
            b64 = base64.b64encode(photo_bytes).decode()

            response = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=[
                    {
                        "parts": [
                            {"text": OCR_PROMPT},
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": b64
                                }
                            }
                        ]
                    }
                ]
            )
            raw = response.text.strip()

            # Чистим markdown если есть
            import re
            raw = re.sub(r'```(?:json)?\s*', '', raw).strip().rstrip('`')

            data = json.loads(raw)
            if "error" in data:
                logger.warning(f"OCR error: {data['error']}")
                return {"ok": False, "error": data["error"]}

            return {"ok": True, "data": data}

        except json.JSONDecodeError as e:
            logger.error(f"OCR JSON parse error: {e}")
            return {"ok": False, "error": "Не удалось разобрать ответ. Попробуй сфотографировать чётче."}
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return {"ok": False, "error": str(e)}

    def save(self, data: dict) -> int:
        """Сохраняет распознанный чек в БД."""
        city = data.get("city") or self.profile.get("city", "")
        return save_receipt(
            user_id=self.user_id,
            store=data.get("store", ""),
            city=city,
            items=data.get("items", []),
            total=data.get("total", 0),
            receipt_date=data.get("date"),
        )

    def format_receipt(self, data: dict) -> str:
        """Форматирует распознанный чек для показа пользователю."""
        store = data.get("store") or "магазин не распознан"
        total = data.get("total", 0)
        items = data.get("items", [])

        lines = [
            f"🧾 *Чек распознан*",
            f"🏪 {store}",
            f"💰 Итого: {total}₽\n",
            "*Позиции:*"
        ]
        for item in items[:15]:
            name = item.get("name", "")
            price = item.get("price", 0)
            qty = item.get("qty", 1)
            if qty > 1:
                lines.append(f"• {name} × {qty} = {price}₽")
            else:
                lines.append(f"• {name} — {price}₽")
        if len(items) > 15:
            lines.append(f"_...и ещё {len(items) - 15} позиций_")

        return "\n".join(lines)

    async def get_price_advice(self) -> str:
        """Советы где дешевле на основе накопленной базы цен."""
        city = self.profile.get("city", "")
        if not city:
            return ""

        # Берём часто покупаемые продукты
        from core.database import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT product_key FROM price_db
                   WHERE user_id=? AND city=?
                   GROUP BY product_key HAVING COUNT(*) >= 3
                   ORDER BY COUNT(*) DESC LIMIT 10""",
                (self.user_id, city)
            ).fetchall()

        if not rows:
            return ""

        keys = [r["product_key"] for r in rows]
        price_data = get_price_compare(self.user_id, keys, city)

        if not price_data:
            return ""

        # Форматируем для промпта
        price_lines = []
        for key, stores in price_data.items():
            if len(stores) >= 2:
                stores_str = " / ".join(f"{s['store']} {s['price']}₽" for s in stores[:3])
                price_lines.append(f"{key}: {stores_str}")

        if not price_lines:
            return ""

        try:
            from core.provider_manager import generate as pm_gen
            from core.lifemode_agent import LifeModeAgent
            lm = LifeModeAgent(self.user_id)
            lifemode = lm.get_finance_context()
        except Exception:
            lifemode = "обычный режим"

        from core.provider_manager import generate as pm_gen
        advice = await pm_gen(
            ADVICE_PROMPT.format(
                price_data="\n".join(price_lines),
                city=city,
                lifemode=lifemode,
            ),
            mode="chat"
        )
        return advice

    def sync_with_shopping_list(self, items: list, db) -> list:
        """Вычёркивает купленные позиции из списка покупок."""
        try:
            shopping = db.get_shopping_list()
            bought = [i.get("name", "").lower() for i in items]
            checked = []
            for sh_item in shopping:
                sh_name = sh_item.get("item", "").lower()
                if any(sh_name in b or b in sh_name for b in bought):
                    db.check_shopping_item(sh_item.get("id"))
                    checked.append(sh_item.get("item"))
            return checked
        except Exception as e:
            logger.debug(f"sync_shopping error: {e}")
            return []
