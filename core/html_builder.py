"""
core/html_builder.py
Строит красивый HTML-дашборд из данных Gemini
"""

import os
from datetime import datetime


class DashboardBuilder:
    def __init__(self, user_id: int, profile: dict):
        self.user_id  = user_id
        self.profile  = profile
        self.vibe     = profile.get("current_vibe", "observer")
        base_dir      = os.getenv("BASE_DIR", "./data")
        self.out_path = os.path.join(base_dir, f"dashboard_{user_id}.html")
        os.makedirs(base_dir, exist_ok=True)

    def render(self, data: dict) -> str:
        vibe_colors = {
            "spark":    {"accent": "#FF6B35", "bg": "#1a0f0a", "card": "#2a1510"},
            "observer": {"accent": "#4CAF50", "bg": "#0f1a0f", "card": "#152015"},
            "twilight": {"accent": "#7C6AF5", "bg": "#0f0d1a", "card": "#17142a"},
        }
        c = vibe_colors.get(self.vibe, vibe_colors["observer"])
        name     = self.profile.get("name", "")
        date_str = datetime.now().strftime("%d %B %Y")
        tasks    = data.get("tasks", [])
        meals    = data.get("meals", {})
        surprise = data.get("surprise", "")
        sections = data.get("html_sections", "")

        tasks_html = "".join(
            f'<li class="task-item" onclick="toggleTask(this)">'
            f'<span class="check">○</span> {t}</li>'
            for t in tasks
        )

        meals_html = ""
        for meal, content in meals.items():
            emoji = {"завтрак": "🌅", "обед": "☀️", "ужин": "🌙"}.get(meal.lower(), "🍽")
            meals_html += f"<div class='meal-row'><b>{emoji} {meal.capitalize()}</b><p>{content}</p></div>"

        surprise_html = f"""
        <div class="surprise-card">
            <div class="surprise-icon">🎁</div>
            <div class="surprise-content">{surprise}</div>
        </div>
        """ if surprise else ""

        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Wingman — {date_str}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --accent: {c['accent']};
    --bg: {c['bg']};
    --card: {c['card']};
    --text: #e8e8e8;
    --muted: #888;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 0 0 40px 0;
  }}
  header {{
    padding: 24px 20px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.07);
  }}
  header h1 {{ font-size: 1.4rem; font-weight: 700; color: var(--accent); }}
  header p  {{ font-size: 0.85rem; color: var(--muted); margin-top: 4px; }}

  nav {{
    display: flex;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    position: sticky; top: 0;
    background: var(--bg);
    z-index: 10;
  }}
  nav button {{
    flex: 1; padding: 12px 4px;
    background: none; border: none;
    color: var(--muted); font-size: 0.75rem;
    cursor: pointer; border-bottom: 2px solid transparent;
    transition: all 0.2s; letter-spacing: 0.04em;
  }}
  nav button.active {{ color: var(--accent); border-bottom-color: var(--accent); }}

  .page {{ display: none; padding: 16px 16px; }}
  .page.active {{ display: block; animation: fadeIn 0.25s ease; }}
  @keyframes fadeIn {{ from {{ opacity:0; transform: translateY(5px) }} to {{ opacity:1; transform: none }} }}

  .card {{
    background: var(--card);
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 12px;
    border-left: 3px solid var(--accent);
  }}
  .card h2 {{ color: var(--accent); font-size: 0.95rem; margin-bottom: 10px; }}

  /* ЗАДАЧИ */
  .task-list {{ list-style: none; }}
  .task-item {{
    padding: 10px 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    cursor: pointer;
    display: flex; align-items: center; gap: 10px;
    transition: opacity 0.2s;
    font-size: 0.95rem;
  }}
  .task-item:last-child {{ border-bottom: none; }}
  .task-item.done {{ opacity: 0.4; text-decoration: line-through; }}
  .task-item.done .check {{ color: var(--accent); }}
  .check {{ font-size: 1.1rem; min-width: 20px; }}

  /* ЕДА */
  .meal-row {{ padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }}
  .meal-row:last-child {{ border-bottom: none; }}
  .meal-row b {{ color: var(--accent); display: block; margin-bottom: 4px; }}
  .meal-row p {{ color: var(--text); font-size: 0.9rem; line-height: 1.5; }}

  /* СЮРПРИЗ */
  .surprise-card {{
    background: linear-gradient(135deg, var(--card), rgba(255,255,255,0.03));
    border-radius: 16px;
    padding: 20px;
    text-align: center;
    border: 1px solid rgba(255,255,255,0.08);
  }}
  .surprise-icon {{ font-size: 2.5rem; margin-bottom: 12px; }}
  .surprise-content {{ font-size: 0.95rem; line-height: 1.7; color: var(--text); }}

  /* AI КОНТЕНТ */
  .ai-content h2, .ai-content h3 {{ color: var(--accent); margin: 12px 0 6px; }}
  .ai-content ul {{ padding-left: 18px; }}
  .ai-content li {{ margin-bottom: 6px; line-height: 1.5; }}
  .ai-content p  {{ line-height: 1.6; margin-bottom: 8px; }}

  .footer {{
    text-align: center;
    color: var(--muted);
    font-size: 0.75rem;
    margin-top: 24px;
    padding: 0 16px;
  }}
</style>
</head>
<body>

<header>
  <h1>{'Доброе утро, ' + name + ' ✦' if name else 'Wingman ✦'}</h1>
  <p>{date_str}</p>
</header>

<nav>
  <button class="active" onclick="show('tasks', this)">📋 ЗАДАЧИ</button>
  <button onclick="show('food', this)">🥗 ПИТАНИЕ</button>
  <button onclick="show('plan', this)">📅 ПЛАН</button>
  <button onclick="show('surprise', this)">🎁 СЮРПРИЗ</button>
</nav>

<div id="tasks" class="page active">
  <div class="card">
    <h2>Задачи на сегодня</h2>
    <ul class="task-list">{tasks_html}</ul>
  </div>
</div>

<div id="food" class="page">
  <div class="card">
    <h2>Рацион на день</h2>
    {meals_html}
  </div>
</div>

<div id="plan" class="page">
  <div class="ai-content">{sections}</div>
</div>

<div id="surprise" class="page">
  {surprise_html if surprise_html else '<div class="card"><h2>Сюрприз</h2><p>Сюрприз будет позже 😉</p></div>'}
</div>

<div class="footer">Wingman v2 · {date_str}</div>

<script>
function show(id, btn) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  if (btn) btn.classList.add('active');
}}

function toggleTask(el) {{
  el.classList.toggle('done');
  el.querySelector('.check').textContent = el.classList.contains('done') ? '✓' : '○';
  // Сохраняем прогресс локально
  const tasks = Array.from(document.querySelectorAll('.task-item'))
    .map(t => ({{ text: t.textContent.trim(), done: t.classList.contains('done') }}));
  localStorage.setItem('tasks_{user_id}', JSON.stringify(tasks));
}}

// Восстанавливаем состояние задач
window.onload = () => {{
  const saved = localStorage.getItem('tasks_{user_id}');
  if (saved) {{
    const tasks = JSON.parse(saved);
    const items = document.querySelectorAll('.task-item');
    tasks.forEach((t, i) => {{
      if (items[i] && t.done) {{
        items[i].classList.add('done');
        items[i].querySelector('.check').textContent = '✓';
      }}
    }});
  }}
}};
</script>
</body>
</html>"""

        with open(self.out_path, "w", encoding="utf-8") as f:
            f.write(html)
        return self.out_path

    def render_to_string(self, data: dict) -> str:
        """
        Возвращает HTML как строку без записи на диск.
        Дублирует логику render() но без open().
        """
        vibe_colors = {
            "spark":    {"accent": "#FF6B35", "bg": "#1a0f0a", "card": "#2a1510"},
            "observer": {"accent": "#4CAF50", "bg": "#0f1a0f", "card": "#152015"},
            "twilight": {"accent": "#7C6AF5", "bg": "#0f0d1a", "card": "#17142a"},
        }
        c = vibe_colors.get(self.vibe, vibe_colors["observer"])
        name     = self.profile.get("name", "")
        date_str = datetime.now().strftime("%d %B %Y")
        tasks    = data.get("tasks", [])
        meals    = data.get("meals", {})
        surprise = data.get("surprise", "")

        tasks_html = "".join(
            f'<li class="task-item" onclick="toggleTask(this)">'
            f'<span class="check">○</span> {t}</li>'
            for t in tasks
        )

        meals_html = ""
        for meal, content in meals.items():
            emoji = {"завтрак": "🌅", "обед": "☀️", "ужин": "🌙"}.get(meal.lower(), "🍽")
            meals_html += f"<div class='meal-row'><b>{emoji} {meal.capitalize()}</b><p>{content}</p></div>"

        surprise_html = f"""
        <div class="surprise-card">
            <div class="surprise-icon">🎁</div>
            <div class="surprise-content">{surprise}</div>
        </div>
        """ if surprise else ""

        # Вызываем render() как источник правды для HTML-шаблона,
        # но перехватываем результат до записи файла
        # Проще — строим html напрямую через тот же шаблон что и render()
        # Патчим out_path на /tmp чтобы не упасть на read-only /app
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
        tmp.close()
        old_path = self.out_path
        self.out_path = tmp.name
        try:
            path = self.render(data)
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
        finally:
            self.out_path = old_path
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
        return html
