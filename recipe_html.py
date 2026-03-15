# -*- coding: utf-8 -*-
"""
core/recipe_html.py
Генератор красивых HTML-карточек рецептов для скачивания.
Использование:
    from core.recipe_html import build_recipe_html
    html = build_recipe_html(recipe_dict)
"""

import urllib.parse


def build_recipe_html(recipe: dict) -> str:
    """
    recipe dict:
      name, kcal, protein, fat, carbs,
      description, steps (list[str]),
      ingredients (list[str]),
      time_min, servings,
      img_query (для Unsplash)
    """
    name        = recipe.get("name", "Рецепт")
    kcal        = recipe.get("kcal", recipe.get("calories", ""))
    protein     = recipe.get("protein", "")
    fat         = recipe.get("fat", "")
    carbs       = recipe.get("carbs", "")
    desc        = recipe.get("description", recipe.get("desc", ""))
    steps       = recipe.get("steps", recipe.get("recipe", []))
    ingredients = recipe.get("ingredients", [])
    time_min    = recipe.get("time_min", recipe.get("time", ""))
    servings    = recipe.get("servings", "1")
    img_query   = recipe.get("img_query", name)

    # URLs
    img_url = f"https://source.unsplash.com/800x500/?food,{urllib.parse.quote(img_query.lower())}"
    yt_url  = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(f"рецепт {name}")

    # Ингредиенты
    if isinstance(ingredients, list):
        ingr_html = "\n".join(f'<li>{i}</li>' for i in ingredients)
    else:
        ingr_html = f'<li>{ingredients}</li>'

    # Шаги
    if isinstance(steps, list):
        steps_html = "\n".join(
            f'<div class="step"><span class="step-num">{i+1}</span><span>{s}</span></div>'
            for i, s in enumerate(steps)
        )
    else:
        steps_html = f'<div class="step"><span class="step-num">1</span><span>{steps}</span></div>'

    # КБЖУ плашки
    nutrition_html = ""
    if kcal:
        nutrition_html += f'<div class="nutr-item"><div class="nutr-val">{kcal}</div><div class="nutr-label">ккал</div></div>'
    if protein:
        nutrition_html += f'<div class="nutr-item"><div class="nutr-val">{protein}г</div><div class="nutr-label">белки</div></div>'
    if fat:
        nutrition_html += f'<div class="nutr-item"><div class="nutr-val">{fat}г</div><div class="nutr-label">жиры</div></div>'
    if carbs:
        nutrition_html += f'<div class="nutr-item"><div class="nutr-val">{carbs}г</div><div class="nutr-label">углеводы</div></div>'

    meta_parts = []
    if time_min: meta_parts.append(f"⏱ {time_min} мин")
    if servings: meta_parts.append(f"🍽 {servings} порц.")
    meta_str = "  ·  ".join(meta_parts)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Unbounded:wght@400;700;900&family=Inter:wght@300;400;500&display=swap');

* {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  font-family: 'Inter', sans-serif;
  background: #07090d;
  color: #e8e8e8;
  min-height: 100vh;
}}

.hero {{
  position: relative;
  height: 320px;
  overflow: hidden;
}}

.hero-img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}}

.hero-overlay {{
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, rgba(7,9,13,1) 0%, rgba(7,9,13,0.4) 50%, transparent 100%);
}}

.hero-title {{
  position: absolute;
  bottom: 24px;
  left: 24px;
  right: 24px;
  font-family: 'Unbounded', sans-serif;
  font-size: clamp(1.4rem, 6vw, 2.2rem);
  font-weight: 900;
  line-height: 1.2;
  color: #fff;
  text-shadow: 0 2px 20px rgba(0,0,0,0.5);
}}

.content {{
  max-width: 680px;
  margin: 0 auto;
  padding: 24px 20px 48px;
}}

.meta-row {{
  display: flex;
  align-items: center;
  gap: 16px;
  color: #666;
  font-size: 0.82rem;
  margin-bottom: 20px;
  flex-wrap: wrap;
}}

.desc {{
  font-size: 0.92rem;
  line-height: 1.7;
  color: #aaa;
  margin-bottom: 24px;
}}

/* КБЖУ */
.nutrition {{
  display: flex;
  gap: 10px;
  margin-bottom: 28px;
  flex-wrap: wrap;
}}

.nutr-item {{
  flex: 1;
  min-width: 70px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 14px 10px;
  text-align: center;
}}

.nutr-val {{
  font-family: 'Unbounded', sans-serif;
  font-size: 1.1rem;
  font-weight: 700;
  color: #39ff6a;
  margin-bottom: 4px;
}}

.nutr-label {{
  font-size: 0.65rem;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}

/* Секции */
.section-title {{
  font-family: 'Unbounded', sans-serif;
  font-size: 0.85rem;
  font-weight: 700;
  color: #39ff6a;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}}

.section-title::after {{
  content: '';
  flex: 1;
  height: 1px;
  background: rgba(57,255,106,0.15);
}}

/* Ингредиенты */
.ingredients {{
  list-style: none;
  margin-bottom: 28px;
}}

.ingredients li {{
  padding: 10px 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  font-size: 0.88rem;
  color: #ccc;
  display: flex;
  align-items: center;
  gap: 10px;
}}

.ingredients li::before {{
  content: '·';
  color: #39ff6a;
  font-size: 1.5rem;
  line-height: 0;
  flex-shrink: 0;
}}

/* Шаги */
.steps {{
  margin-bottom: 32px;
}}

.step {{
  display: flex;
  gap: 14px;
  margin-bottom: 14px;
  align-items: flex-start;
}}

.step-num {{
  width: 28px;
  height: 28px;
  background: rgba(57,255,106,0.12);
  border: 1px solid rgba(57,255,106,0.25);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Unbounded', sans-serif;
  font-size: 0.7rem;
  font-weight: 700;
  color: #39ff6a;
  flex-shrink: 0;
  margin-top: 2px;
}}

.step span:last-child {{
  font-size: 0.88rem;
  line-height: 1.6;
  color: #ccc;
}}

/* Кнопка YouTube */
.yt-btn {{
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: #ff0000;
  color: #fff;
  font-family: 'Unbounded', sans-serif;
  font-weight: 700;
  font-size: 0.85rem;
  padding: 14px 24px;
  border-radius: 12px;
  text-decoration: none;
  transition: opacity 0.2s;
  margin-bottom: 16px;
}}

.yt-btn:hover {{ opacity: 0.85; }}

.footer {{
  text-align: center;
  font-size: 0.72rem;
  color: #333;
  margin-top: 8px;
}}
</style>
</head>
<body>

<div class="hero">
  <img class="hero-img"
       src="{img_url}"
       alt="{name}"
       onerror="this.src='https://source.unsplash.com/800x500/?food,cooking'">
  <div class="hero-overlay"></div>
  <div class="hero-title">{name}</div>
</div>

<div class="content">

  <div class="meta-row">
    {meta_str}
  </div>

  {"<p class='desc'>" + desc + "</p>" if desc else ""}

  {"<div class='nutrition'>" + nutrition_html + "</div>" if nutrition_html else ""}

  {"<div class='section-title'>Ингредиенты</div><ul class='ingredients'>" + ingr_html + "</ul>" if ingr_html else ""}

  {"<div class='section-title'>Приготовление</div><div class='steps'>" + steps_html + "</div>" if steps_html else ""}

  <a href="{yt_url}" target="_blank" class="yt-btn">
    ▶ Смотреть рецепт на YouTube
  </a>

  <div class="footer">Создано @AEatolog · Wingman v3.9</div>

</div>
</body>
</html>"""


def recipe_from_text(text: str, name: str = "") -> dict:
    """
    Пробует распарсить рецепт из свободного текста AI.
    Возвращает dict для build_recipe_html.
    """
    import re

    recipe = {"name": name or "Рецепт", "steps": [], "ingredients": []}

    # Ккал
    m = re.search(r'(\d{2,4})\s*(?:ккал|калор)', text, re.IGNORECASE)
    if m: recipe["kcal"] = m.group(1)

    # Белки/жиры/углеводы
    m = re.search(r'[Бб]елк\w+[:\s]+(\d+)', text)
    if m: recipe["protein"] = m.group(1)
    m = re.search(r'[Жж]ир\w+[:\s]+(\d+)', text)
    if m: recipe["fat"] = m.group(1)
    m = re.search(r'[Уу]глевод\w+[:\s]+(\d+)', text)
    if m: recipe["carbs"] = m.group(1)

    # Время
    m = re.search(r'(\d+)\s*мин', text, re.IGNORECASE)
    if m: recipe["time_min"] = m.group(1)

    # Шаги — ищем нумерованные строки
    steps = re.findall(r'(?:^|\n)\s*\d+[.)]\s*(.+)', text)
    if steps:
        recipe["steps"] = [s.strip() for s in steps[:12]]

    # Ингредиенты — ищем строки с •, -, *
    ingredients = re.findall(r'(?:^|\n)\s*[-•*]\s*(.+)', text)
    if ingredients:
        recipe["ingredients"] = [i.strip() for i in ingredients[:15]]

    return recipe
