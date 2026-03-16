# Деплой WebApp на Railway — инструкция

## Шаг 1. Создать новый сервис в Railway

1. Открой railway.com → твой проект
2. Нажми **+ New Service** → **Empty Service**
3. Назови его `webapp`

## Шаг 2. Подключить GitHub папку

В настройках нового сервиса:
- Source: **GitHub** → твой репо `Wingman`
- Root Directory: `webapp`
- Build Command: (пусто)
- Start Command: (пусто)

## Шаг 3. Получить HTTPS URL

После деплоя Railway автоматически даст URL вида:
```
https://webapp-production-xxxx.up.railway.app
```

Скопируй этот URL.

## Шаг 4. Добавить в Variables бота

В сервисе **bot** → Variables:
```
WEBAPP_URL = https://webapp-production-xxxx.up.railway.app
```

После сохранения Railway передеплоит бота автоматически.

## Шаг 5. Проверить

Напиши /start боту — появится кнопка "📱 Открыть приложение".
Нажми — откроется WebApp прямо в Telegram.

---

## Альтернатива — GitHub Pages (если Railway не даёт)

1. Создай репо `aeatolog-webapp` на GitHub
2. Загрузи `webapp/index.html` как `index.html`
3. Settings → Pages → Deploy from branch: main
4. URL будет: `https://твой-ник.github.io/aeatolog-webapp`
5. Вставь этот URL в WEBAPP_URL

GitHub Pages полностью бесплатно и работает всегда.
