# Wingman v3.1

## Что нового
- ✅ SQLite + WAL + threading.Lock — атомарные записи, не теряет данные при crash
- ✅ KeyManager v4 — ротация до 5 ключей Gemini (ENV + keys.txt), health_report
- ✅ История чата — последние 20 сообщений как контекст
- ✅ Day/Week summary — дайджест дня вечером, анализ недели в воскресенье
- ✅ Список покупок с inline ✅/❌ (/shopping)
- ✅ Трекер веса (/weight, /progress)
- ✅ /fridge — рецепты из холодильника
- ✅ /feedback → уведомление админу
- ✅ Умный парсинг времени (голос/STT)
- ✅ Вечерние рекомендации (фильмы/музыка/книга)
- ✅ **Idea Factory** — 20 субмодулей мышления (/idea, /idea_pipeline, /idea_list)
- ✅ /keys — статус всех API ключей

## Деплой Railway

### Variables
```
TELEGRAM_TOKEN=...
GEMINI_KEY_1=AIzaSy...   # обязательно
GEMINI_KEY_2=AIzaSy...   # опционально
GEMINI_KEY_3=AIzaSy...   # опционально
GEMINI_KEY_4=AIzaSy...   # опционально
ADMIN_ID=123456789        # твой Telegram ID (@userinfobot)
DB_PATH=./data/wingman.db
BASE_DIR=./data
```

### Volume (чтобы данные не терялись)
Railway → Add Volume → Mount Path: `/app/data`
Потом: `DB_PATH=/app/data/wingman.db`

### Push
```bash
git add .
git commit -m "feat: wingman v3.1 — idea factory, key manager v4, atomic db"
git push
```

## Команды
| Команда | Описание |
|---------|----------|
| `анкета` | Онбординг (13 шагов) |
| `/plan` | План на день |
| `/tasks` | Задачи |
| `/weight 78.5` | Записать вес |
| `/progress` | График веса |
| `/shopping` | Список покупок |
| `/fridge курица, рис` | Рецепты из холодильника |
| `/vibe` | Сменить вайб |
| `/streak` | Стрик |
| `/feedback текст` | Отзыв → админу |
| `/keys` | Статус API ключей |
| `/idea тема` | Сгенерировать идею |
| `/idea тема #8` | Идея через модуль #8 |
| `/idea_pipeline тема` | Топ-3 из 5 модулей |
| `/idea_list` | Все 20 субмодулей |

## Idea Factory — субмодули
| # | Название | Тег |
|---|----------|-----|
| 1 | Cross-Domain Fusion | FUSION |
| 2 | Trend-Wave Predictor | TREND |
| 3 | Problem-Solver | PAIN |
| 4 | Sci-Fi Prototype | SCIFI |
| 5 | Resource-Constrained | LEAN |
| 6 | Bionic Design | BIONIC |
| 7 | Anti-Pattern | ANTI |
| 8 | Micro-SaaS | MSAAS |
| 9 | Gamification Engine | GAME |
| 10 | Eco-Systemic | ECO |
| 11 | Emotional AI | EMO |
| 12 | Legacy Reviver | LEGACY |
| 13 | Chaos Engineering | CHAOS |
| 14 | Local-First | LOCAL |
| 15 | Educational Sim | EDU |
| 16 | Security Guard | SEC |
| 17 | Zero-Waste Logistics | ZWL |
| 18 | AI-Agent Specialist | AGENTS |
| 19 | Bio-Hacking | BIO |
| 20 | Ethical AI | ETHICS |
