# -*- coding: utf-8 -*-
"""
core/key_manager.py
KeyManager v4 — ротация ключей Gemini
Источники: ENV (GEMINI_KEY_1..5) + keys.txt файл
Singleton, health_report с маскировкой
"""

import os
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

KEYS_FILE = Path(os.getenv("KEYS_FILE", "./keys.txt"))


class KeyManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._keys: list[str] = []
        self._idx: int = 0
        self._stats: dict[str, str] = {}
        self._load()
        self._initialized = True

    def _load(self):
        raw: list[str] = []

        # ENV: GEMINI_KEY_1..5
        for i in range(1, 6):
            key = os.getenv(f"GEMINI_KEY_{i}", "").strip()
            if key.startswith("AIza") and key not in raw:
                raw.append(key)

        # Legacy GEMINI_KEY
        if not raw:
            key = os.getenv("GEMINI_KEY", "").strip()
            if key.startswith("AIza"):
                raw.append(key)

        # keys.txt (Termux / локальная разработка)
        if KEYS_FILE.exists():
            try:
                for line in KEYS_FILE.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    val = line.split("=", 1)[-1].strip() if "=" in line else line
                    if val.startswith("AIza") and len(val) > 20 and val not in raw:
                        raw.append(val)
            except Exception as e:
                logger.warning(f"KeyManager: keys.txt error: {e}")

        self._keys = raw[:5]
        self._idx = 0
        self._stats = {k: "READY" for k in self._keys}

        if self._keys:
            logger.info(f"KeyManager: загружено {len(self._keys)} ключей")
        else:
            logger.error("KeyManager: НЕТ КЛЮЧЕЙ! Проверь GEMINI_KEY_1 в ENV")

    def get_key(self) -> str:
        if not self._keys:
            raise RuntimeError("KeyManager: нет доступных ключей Gemini")
        return self._keys[self._idx % len(self._keys)]

    @property
    def current(self) -> str:
        return self.get_key()

    def rotate(self) -> str:
        if not self._keys:
            raise RuntimeError("KeyManager: нет ключей для ротации")
        old = self.get_key()
        self._stats[old] = "RATE_LIMITED"
        self._idx += 1
        new = self.get_key()
        self._stats[new] = "ACTIVE"
        logger.warning(f"KeyManager: ротация {self._mask(old)} → {self._mask(new)}")
        return new

    def mark_valid(self, key: str):
        if key in self._stats:
            self._stats[key] = "VALID"

    def mark_error(self, key: str, reason: str = ""):
        if key in self._stats:
            self._stats[key] = f"ERROR:{reason[:20]}"

    def reload(self):
        self._load()
        logger.info("KeyManager: перезагружен")

    def health_report(self) -> list[str]:
        out = []
        for i, k in enumerate(self._keys):
            active = " ← ACTIVE" if i == self._idx % len(self._keys) else ""
            out.append(f"Key[{i+1}] {self._mask(k)} → {self._stats.get(k,'UNKNOWN')}{active}")
        return out

    def count(self) -> int:
        return len(self._keys)

    @staticmethod
    def _mask(key: str) -> str:
        return f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "****"


_km = KeyManager()

def get_key() -> str:    return _km.get_key()
def rotate_key() -> str: return _km.rotate()
def health() -> list[str]: return _km.health_report()
