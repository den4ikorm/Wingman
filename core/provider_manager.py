# -*- coding: utf-8 -*-
"""
core/provider_manager.py
ProviderManager v2 — каскад с ротацией всех провайдеров

Порядок при 429:
  1. Gemini  — ротация GEMINI_KEY_1..4  (4 × 1500 = 6000/day)
  2. Groq    — ротация GROQ_API_KEY_1..4 (4 × 14400 = 57600/day)
  3. OpenRouter — OPENROUTER_API_KEY (запасной)

Переменные в Railway Variables:
  GEMINI_KEY_1..4
  GROQ_API_KEY_1..4
  OPENROUTER_API_KEY  (опционально)
"""

import os
import asyncio
import logging

logger = logging.getLogger(__name__)

GEMINI_MODEL     = "gemini-2.5-flash-lite"
GROQ_MODEL       = "llama-3.3-70b-versatile"
OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"


class GroqKeyManager:
    def __init__(self):
        self._keys: list[str] = []
        self._idx: int = 0
        self._load()

    def _load(self):
        keys = []
        for i in range(1, 6):
            k = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
            if k.startswith("gsk_") and k not in keys:
                keys.append(k)
        if not keys:
            k = os.getenv("GROQ_API_KEY", "").strip()
            if k.startswith("gsk_"):
                keys.append(k)
        self._keys = keys
        if keys:
            logger.info(f"GroqKeyManager: загружено {len(keys)} ключей")
        else:
            logger.warning("GroqKeyManager: ключи не найдены")

    def get_key(self) -> str | None:
        if not self._keys:
            return None
        return self._keys[self._idx % len(self._keys)]

    def rotate(self):
        self._idx += 1

    def count(self) -> int:
        return len(self._keys)


class ProviderManager:

    def __init__(self):
        self._km  = None
        self._gkm = GroqKeyManager()

    def _get_km(self):
        if self._km is None:
            from core.key_manager import KeyManager
            self._km = KeyManager()
        return self._km

    async def generate(self, system_prompt: str, user_text: str, max_tokens: int = 1200) -> str:
        # 1. Groq — основной (быстрее, лимит 57600/day)
        if self._gkm.count() > 0:
            result = await self._try_groq(system_prompt, user_text, max_tokens)
            if result:
                return result
            logger.warning("Groq исчерпан → переключаюсь на Gemini")

        # 2. Gemini — резервный (6000/day)
        result = await self._try_gemini(system_prompt, user_text, max_tokens)
        if result:
            return result

        # 3. OpenRouter — последний резерв
        or_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if or_key:
            logger.warning("Gemini исчерпан → переключаюсь на OpenRouter")
            result = await self._try_openrouter(or_key, system_prompt, user_text, max_tokens)
            if result:
                return result

        logger.error("Все провайдеры исчерпаны")
        return "⚠️ Сервис временно перегружен. Попробуй через несколько минут."

    async def _try_gemini(self, system: str, text: str, max_tokens: int) -> str | None:
        try:
            from google import genai
        except ImportError:
            return None

        km = self._get_km()
        attempts = max(km.count(), 1)

        for attempt in range(attempts):
            try:
                key = km.get_key()
                client = genai.Client(api_key=key)

                def _call():
                    resp = client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=text,
                        config={
                            "system_instruction": system,
                            "max_output_tokens": max_tokens,
                        }
                    )
                    return resp.text.strip()

                result = await asyncio.get_event_loop().run_in_executor(None, _call)
                km.mark_valid(key)
                return result

            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    logger.warning(f"Gemini ключ {attempt+1}/{attempts} 429, ротирую...")
                    km.rotate()
                    await asyncio.sleep(1)
                else:
                    logger.error(f"Gemini error: {e}")
                    return None

        return None

    async def _try_groq(self, system: str, text: str, max_tokens: int) -> str | None:
        gkm = self._gkm
        attempts = gkm.count()

        for attempt in range(attempts):
            api_key = gkm.get_key()
            if not api_key:
                return None
            try:
                import httpx
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": GROQ_MODEL,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user",   "content": text},
                            ],
                            "max_tokens": max_tokens,
                            "temperature": 0.7,
                        }
                    )

                if resp.status_code == 429:
                    logger.warning(f"Groq ключ {attempt+1}/{attempts} 429, ротирую...")
                    gkm.rotate()
                    await asyncio.sleep(1)
                    continue

                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()

            except Exception as e:
                logger.error(f"Groq error: {e}")
                gkm.rotate()

        return None

    async def _try_openrouter(self, api_key: str, system: str, text: str, max_tokens: int) -> str | None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://wingman-bot.app",
                        "X-Title": "Wingman Bot",
                    },
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user",   "content": text},
                        ],
                        "max_tokens": max_tokens,
                    }
                )
            if resp.status_code == 429:
                return None
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"OpenRouter error: {e}")
            return None


# Singleton
_pm = ProviderManager()

async def generate(system: str, text: str, max_tokens: int = 1200) -> str:
    return await _pm.generate(system, text, max_tokens)
