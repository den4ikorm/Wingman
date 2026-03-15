# -*- coding: utf-8 -*-
"""
core/html_builder.py  v3
DashboardBuilder — HTML-дашборд с вкладками:
  📋 Задачи    — чеклист (sessionStorage)
  🥗 Питание   — сегодня: рецепт-попап, Unsplash-фото, YouTube, альтернативы
  📅 Неделя    — 7 дней accordion, под каждым блюдом рецепт + альтернативы
  🛒 Покупки   — чеклист с галочками
  📖 Рецепты   — сохранённые рецепты (sessionStorage + data['my_recipes'])
  💡 План      — полный текст дня

Альтернативы по уровню режима:
  1-2: любые 3 варианта
  3:   только та же категория
  4:   только близкий БЖУ
  5:   кнопка заблокирована

Фото: Unsplash Source API (бесплатно, без ключа)
"""

import os
import re
import json
import logging
import urllib.parse
from datetime import date, timedelta

logger = logging.getLogger(__name__)

VIBES = {
    "spark": {
        "accent": "#FF6B35", "accent2": "#FFB347",
        "bg": "#0D0D0D", "surface": "#1A1A1A", "tab_bg": "#141414",
        "text": "#F5F0E8", "muted": "#888", "border": "#2A2A2A", "tag": "🔥",
    },
    "observer": {
        "accent": "#4ECDC4", "accent2": "#2196F3",
        "bg": "#080F1A", "surface": "#0D1F35", "tab_bg": "#0A1828",
        "text": "#E8F4FD", "muted": "#6B8CAE", "border": "#1A3050", "tag": "✦",
    },
    "twilight": {
        "accent": "#C084FC", "accent2": "#F472B6",
        "bg": "#0A0612", "surface": "#130920", "tab_bg": "#0E0618",
        "text": "#F0E8FF", "muted": "#9B7BC4", "border": "#2A1545", "tag": "🌙",
    },
}
DEFAULT_VIBE = "observer"

LEVEL_NAMES = {1:"🌿 Интуитивное",2:"🥗 Сбалансированное",3:"⚡ Активное",4:"🏋️ Спортивное",5:"🔥 Максимум"}
DAY_NAMES   = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]


class DashboardBuilder:
    def __init__(self, user_id: int, profile: dict):
        self.user_id  = user_id
        self.profile  = profile
        base_dir      = os.getenv("BASE_DIR", "./data")
        os.makedirs(base_dir, exist_ok=True)
        self.out_path = os.path.join(base_dir, f"dashboard_{user_id}.html")

    def _vibe(self):
        return VIBES.get(self.profile.get("vibe", DEFAULT_VIBE), VIBES[DEFAULT_VIBE])

    def _level(self):
        return int(self.profile.get("diet_level", 2))

    def _yt(self, name):
        return "https://www.youtube.com/results?search_query=" + urllib.parse.quote(f"рецепт {name}")

    def _img(self, name):
        q = urllib.parse.quote(name.lower())
        return f"https://source.unsplash.com/400x240/?food,{q}"

    def _md(self, text):
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*',     r'<em>\1</em>',         text)
        text = re.sub(r'^#{1,3}\s+(.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^---+$', '<hr>', text, flags=re.MULTILINE)
        return text.replace('\n', '<br>')

    def render(self, data):
        html = self._build(data)
        with open(self.out_path, "w", encoding="utf-8") as f:
            f.write(html)
        return self.out_path

    def render_to_string(self, data):
        return self._build(data).encode("utf-8")

    # ── КАРТОЧКА БЛЮДА + ПОПАП ─────────────────────────────────────────────

    def _meal_block(self, meal, pid, emoji, level):
        name  = meal.get("name", "Блюдо")
        desc  = meal.get("desc", meal.get("description", ""))
        kcal  = meal.get("kcal", meal.get("calories", ""))
        steps = meal.get("recipe", meal.get("steps", []))
        alts  = meal.get("alternatives", [])
        yt    = self._yt(name)
        img   = self._img(meal.get("img_query", name))
        badge = f'<span class="badge">{kcal} ккал</span>' if kcal else ""

        # Кнопка альтернатив
        if level >= 5:
            alt_btn = '<button class="btn-alt locked" title="Режим Максимум — замена недоступна">🔒 Замена</button>'
        elif alts:
            alt_btn = f'<button class="btn-alt" onclick="toggleAlts(\'{pid}_a\')">🔄 Альтернативы</button>'
        else:
            alt_btn = ''

        # Альтернативы
        alts_html = ""
        if alts and level < 5:
            items = ""
            for a in alts[:3]:
                an = a.get("name","") if isinstance(a,dict) else str(a)
                ad = a.get("desc","") if isinstance(a,dict) else ""
                items += f'<div class="alt-item"><div class="alt-name">{an}</div><div class="alt-desc">{ad}</div><a class="btn-yt-sm" href="{self._yt(an)}" target="_blank">▶ YouTube</a></div>'
            alts_html = f'<div class="alts" id="{pid}_a">{items}</div>'

        # Шаги рецепта
        if isinstance(steps, list) and steps:
            steps_html = "".join(f"<li>{s}</li>" for s in steps)
        elif isinstance(steps, str) and steps:
            steps_html = "".join(f"<li>{l.strip()}</li>" for l in steps.split("\n") if l.strip())
        else:
            steps_html = f"<li>Найди рецепт на YouTube 👆</li>"

        card = f"""<div class="meal-card">
  <img class="meal-img" src="{img}" alt="{name}" loading="lazy" onerror="this.style.display='none'">
  <div class="meal-body">
    <div class="meal-title">{emoji} {name} {badge}</div>
    <div class="meal-desc">{desc}</div>
    <div class="meal-btns">
      <button class="btn-recipe" onclick="openP('{pid}')">📖 Рецепт</button>
      <a class="btn-yt" href="{yt}" target="_blank">▶ YouTube</a>
      {alt_btn}
    </div>
    {alts_html}
  </div>
</div>"""

        popup = f"""<div class="popup-ov" id="{pid}" onclick="if(event.target===this)closeP('{pid}')">
  <div class="popup-box">
    <button class="popup-x" onclick="closeP('{pid}')">✕</button>
    <img class="popup-img" src="{img}" alt="{name}" onerror="this.style.display='none'">
    <h2>{emoji} {name}</h2>{badge}
    <ol class="rec-steps">{steps_html}</ol>
    <div class="popup-ft">
      <a class="btn-yt-full" href="{yt}" target="_blank">▶ YouTube</a>
      <button class="btn-save" onclick="saveRec('{name.replace(chr(39),' ')}',`{desc.replace('`',' ')}`)">💾 Сохранить</button>
      <button class="btn-print" onclick="window.print()">🖨</button>
    </div>
  </div>
</div>"""

        return card, popup

    def _week_day(self, day_data, idx, level):
        dname = DAY_NAMES[idx % 7]
        ddate = (date.today() + timedelta(days=idx)).strftime("%-d %b")
        meals = day_data.get("meals", {})
        slots = [("breakfast","🌅","Завтрак"),("lunch","☀️","Обед"),("dinner","🌙","Ужин")]
        cards = popups = ""
        for sk, em, lb in slots:
            meal = meals.get(sk, {"name": lb})
            c, p = self._meal_block(meal, f"w{idx}_{sk}", em, level)
            cards += c; popups += p
        return f"""<div class="wday">
  <div class="wday-hdr" onclick="toggleDay('wd{idx}')">
    <span class="wday-name">{dname}</span><span class="wday-date">{ddate}</span><span class="wday-arr">▾</span>
  </div>
  <div class="wday-body" id="wd{idx}">{cards}</div>
</div>{popups}"""

    # ── ГЛАВНЫЙ РЕНДЕР ────────────────────────────────────────────────────────

    def _build(self, data):
        c     = self._vibe()
        lv    = self._level()
        name  = self.profile.get("name","Денис")
        ds    = date.today().strftime("%-d %B %Y")
        tag   = c["tag"]
        uid   = self.user_id
        lvlb  = LEVEL_NAMES.get(lv,"")

        # Задачи
        tasks = data.get("tasks",[])
        thtml = "".join(f'<li class="ci" onclick="toggleCheck(this,\'t{uid}_{i}\')" data-id="t{uid}_{i}"><span class="ch">○</span><span>{t}</span></li>' for i,t in enumerate(tasks)) or '<li class="empty">Задачи появятся после генерации плана</li>'

        # Покупки
        shop = data.get("shopping",[])
        shtml = ""
        for i,item in enumerate(shop):
            if isinstance(item,dict):
                lbl = item.get("name",item.get("item",""))
                qty = item.get("qty",item.get("amount",""))
                lbl = f"{lbl} — {qty}" if qty else lbl
            else: lbl = str(item)
            shtml += f'<li class="ci" onclick="toggleCheck(this,\'s{uid}_{i}\')" data-id="s{uid}_{i}"><span class="ch">○</span><span>{lbl}</span></li>'
        shtml = shtml or '<li class="empty">Список покупок появится после генерации плана</li>'

        # Питание сегодня
        today_meals = data.get("meals",{})
        slots = [("breakfast","🌅","Завтрак"),("lunch","☀️","Обед"),("dinner","🌙","Ужин")]
        tcards = tpopups = ""
        for sk,em,lb in slots:
            meal = today_meals.get(sk,{"name":lb})
            c2,p = self._meal_block(meal, f"today_{sk}", em, lv)
            tcards += c2; tpopups += p

        # Неделя
        week = data.get("week",[])
        whtml = "".join(self._week_day(d,i,lv) for i,d in enumerate(week[:7])) if week else '<div class="empty" style="padding:32px;text-align:center">Недельный план появится после генерации</div>'

        # Мои рецепты
        my_recs = data.get("my_recipes",[])
        mrhtml = ""
        for r in my_recs:
            rn = r.get("name",""); rs = r.get("steps","")
            mrhtml += f'<div class="my-rec"><div class="my-rec-name">{rn}</div><div class="my-rec-steps">{rs}</div><a class="btn-yt-sm" href="{self._yt(rn)}" target="_blank">▶ YouTube</a></div>'
        mrhtml = mrhtml or '<div class="empty" style="padding:24px;text-align:center">Нажми 💾 в рецепте чтобы сохранить</div>'

        # Цитата дня
        quote      = data.get("quote", "")
        quote_auth = data.get("quote_author", "")
        quote_block = f'''<div class="quote-block">
  <div class="quote-text">"{quote}"</div>
  <div class="quote-author">— {quote_auth}</div>
</div>''' if quote else ""

        # Советы дня
        tips = data.get("tips", [])
        tips_html = ""
        for tip in tips:
            t_time = tip.get("time","") if isinstance(tip,dict) else ""
            t_text = tip.get("text", str(tip)) if isinstance(tip,dict) else str(tip)
            tips_html += f'''<div class="tip-card">
  <div class="tip-time">{t_time}</div>
  <div class="tip-text">{t_text}</div>
</div>'''
        if not tips_html:
            tips_html = '<div class="empty" style="padding:24px;text-align:center">Советы появятся после генерации плана</div>'

        # План
        plan = self._md(data.get("html_sections", data.get("plan_text","")))
        surprise = data.get("surprise","")
        surp_html = f'<div class="surprise">{surprise}</div>' if surprise else ""

        vibe_css = c
        return f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Wingman {ds}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700&display=swap');
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--a:{vibe_css['accent']};--a2:{vibe_css['accent2']};--bg:{vibe_css['bg']};--sf:{vibe_css['surface']};--tb:{vibe_css['tab_bg']};--tx:{vibe_css['text']};--mu:{vibe_css['muted']};--br:{vibe_css['border']};--r:12px;--r2:8px}}
body{{font-family:'Manrope',sans-serif;background:var(--bg);color:var(--tx);min-height:100vh;padding-bottom:80px}}
.hdr{{padding:20px 16px 12px;background:linear-gradient(180deg,var(--sf) 0%,transparent 100%)}}
.hdr-name{{font-size:22px;font-weight:700}}.hdr-date{{font-size:13px;color:var(--mu);margin-top:2px}}
.lvl-badge{{display:inline-block;font-size:11px;padding:3px 10px;border-radius:20px;background:var(--a);color:var(--bg);font-weight:600;margin-top:6px}}
.tabs{{display:flex;gap:4px;padding:8px 12px;background:var(--tb);position:sticky;top:0;z-index:100;overflow-x:auto;border-bottom:1px solid var(--br)}}
.tabs::-webkit-scrollbar{{display:none}}
.tab{{flex:none;padding:8px 14px;border-radius:20px;font-size:13px;font-weight:600;background:transparent;color:var(--mu);border:1px solid var(--br);cursor:pointer;transition:all .2s;white-space:nowrap}}
.tab.active{{background:var(--a);color:var(--bg);border-color:var(--a)}}
.panel{{display:none;padding:16px}}.panel.active{{display:block}}
.sec-title{{font-size:13px;font-weight:600;color:var(--mu);text-transform:uppercase;letter-spacing:.08em;margin:0 0 12px}}
.checklist{{list-style:none;display:flex;flex-direction:column;gap:8px}}
.ci{{display:flex;align-items:center;gap:12px;padding:14px 16px;background:var(--sf);border-radius:var(--r);cursor:pointer;border:1px solid var(--br);transition:all .2s;font-size:14px}}
.ci.done{{opacity:.5;text-decoration:line-through}}.ch{{font-size:18px;min-width:20px;color:var(--a)}}
.empty{{color:var(--mu);font-size:13px}}
.meal-card{{background:var(--sf);border-radius:var(--r);overflow:hidden;margin-bottom:12px;border:1px solid var(--br)}}
.meal-img{{width:100%;height:150px;object-fit:cover;display:block}}
.meal-body{{padding:14px}}
.meal-title{{font-size:15px;font-weight:700;margin-bottom:4px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.meal-desc{{font-size:13px;color:var(--mu);margin-bottom:12px;line-height:1.5}}
.badge{{font-size:11px;padding:2px 8px;border-radius:20px;background:color-mix(in srgb,var(--a) 20%,transparent);color:var(--a);font-weight:600}}
.meal-btns{{display:flex;gap:8px;flex-wrap:wrap}}
.btn-recipe{{padding:8px 14px;border-radius:var(--r2);background:var(--a);color:var(--bg);font-size:13px;font-weight:600;border:none;cursor:pointer}}
.btn-yt{{padding:8px 14px;border-radius:var(--r2);background:#FF000020;color:#FF5555;font-size:13px;font-weight:600;border:1px solid #FF555530;text-decoration:none;display:inline-flex;align-items:center}}
.btn-alt{{padding:8px 14px;border-radius:var(--r2);background:color-mix(in srgb,var(--a2) 20%,transparent);color:var(--a2);font-size:13px;font-weight:600;border:1px solid color-mix(in srgb,var(--a2) 30%,transparent);cursor:pointer}}
.btn-alt.locked{{opacity:.4;cursor:not-allowed}}
.alts{{margin-top:12px;display:flex;flex-direction:column;gap:8px}}
.alt-item{{padding:12px;background:var(--bg);border-radius:var(--r2);border:1px solid var(--br)}}
.alt-name{{font-size:14px;font-weight:600;margin-bottom:2px}}.alt-desc{{font-size:12px;color:var(--mu);margin-bottom:6px}}
.btn-yt-sm{{font-size:12px;padding:4px 10px;border-radius:20px;background:#FF000018;color:#FF5555;text-decoration:none;display:inline-block}}
.popup-ov{{display:none;position:fixed;inset:0;background:#00000090;z-index:1000;overflow-y:auto;padding:20px 12px;align-items:flex-start;justify-content:center}}
.popup-ov.open{{display:flex}}
.popup-box{{background:var(--sf);border-radius:var(--r);max-width:480px;width:100%;padding:20px;position:relative;margin:auto}}
.popup-x{{position:absolute;top:12px;right:12px;background:var(--bg);border:1px solid var(--br);color:var(--tx);border-radius:50%;width:32px;height:32px;font-size:16px;cursor:pointer}}
.popup-img{{width:100%;height:180px;object-fit:cover;border-radius:var(--r2);margin-bottom:14px}}
.popup-box h2{{font-size:18px;font-weight:700;margin-bottom:8px}}
.rec-steps{{padding-left:20px;margin:12px 0;display:flex;flex-direction:column;gap:8px;font-size:14px;line-height:1.6}}
.popup-ft{{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap}}
.btn-yt-full{{flex:1;padding:10px;border-radius:var(--r2);background:#FF000020;color:#FF5555;text-align:center;text-decoration:none;font-weight:600;border:1px solid #FF555530}}
.btn-save{{flex:1;padding:10px;border-radius:var(--r2);background:color-mix(in srgb,var(--a) 20%,transparent);color:var(--a);font-weight:600;border:1px solid color-mix(in srgb,var(--a) 30%,transparent);cursor:pointer}}
.btn-print{{padding:10px 14px;border-radius:var(--r2);background:var(--bg);color:var(--mu);font-weight:600;border:1px solid var(--br);cursor:pointer}}
.wday{{background:var(--sf);border-radius:var(--r);margin-bottom:10px;border:1px solid var(--br);overflow:hidden}}
.wday-hdr{{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;cursor:pointer}}
.wday-name{{font-weight:700;font-size:15px}}.wday-date{{font-size:13px;color:var(--mu)}}.wday-arr{{color:var(--a);font-size:16px;transition:transform .2s}}
.wday-hdr.open .wday-arr{{transform:rotate(180deg)}}
.wday-body{{padding:12px;display:none}}
.my-rec{{background:var(--sf);border-radius:var(--r);padding:14px;margin-bottom:10px;border:1px solid var(--br)}}
.my-rec-name{{font-size:15px;font-weight:700;margin-bottom:6px}}.my-rec-steps{{font-size:13px;color:var(--mu);margin-bottom:10px;line-height:1.5}}
.plan-content{{font-size:14px;line-height:1.7}}.plan-content h3{{color:var(--a);margin:14px 0 6px;font-size:15px}}.plan-content hr{{border:none;border-top:1px solid var(--br);margin:12px 0}}
.surprise{{background:linear-gradient(135deg,color-mix(in srgb,var(--a) 15%,transparent),color-mix(in srgb,var(--a2) 15%,transparent));border-radius:var(--r);padding:16px;margin-bottom:16px;border:1px solid color-mix(in srgb,var(--a) 40%,transparent);font-size:14px;line-height:1.6}}
.quote-block{{background:linear-gradient(135deg,color-mix(in srgb,var(--a) 12%,transparent),transparent);border-radius:var(--r2);padding:12px 14px;margin-top:10px;border-left:3px solid var(--a)}}
.quote-text{{font-size:14px;font-style:italic;line-height:1.5;margin-bottom:4px}}
.quote-author{{font-size:12px;color:var(--mu);font-weight:600}}
.tip-card{{background:var(--sf);border-radius:var(--r);padding:16px;margin-bottom:10px;border:1px solid var(--br);border-left:3px solid var(--a2)}}
.tip-time{{font-size:11px;font-weight:700;color:var(--a2);text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}}
.tip-text{{font-size:14px;line-height:1.6}}
.toast{{position:fixed;bottom:90px;left:50%;transform:translateX(-50%);background:var(--a);color:var(--bg);padding:10px 20px;border-radius:20px;font-size:13px;font-weight:600;opacity:0;transition:opacity .3s;z-index:9999;pointer-events:none;white-space:nowrap}}
.toast.show{{opacity:1}}

/* TAB HERO IMAGES */
.tab-hero{{
  width:100%;height:180px;object-fit:cover;display:block;
  border-radius:0 0 var(--r) var(--r);margin-bottom:4px;
  filter:brightness(0.7) saturate(1.2);
  transition:filter .3s;
}}
.tab-hero-wrap{{
  position:relative;margin-bottom:8px;border-radius:0 0 var(--r) var(--r);overflow:hidden;
}}
.tab-hero-title{{
  position:absolute;bottom:0;left:0;right:0;padding:16px;
  background:linear-gradient(transparent,#00000088);
  font-size:18px;font-weight:700;color:#fff;
}}
</style></head><body>

<div class="hdr">
  <div class="hdr-name">Доброе утро, {name} {tag}</div>
  <div class="hdr-date">{ds}</div>
  <div class="lvl-badge">{lvlb}</div>
  {quote_block}
</div>

<div class="tabs">
  <button class="tab active" onclick="sw('tasks',this)">📋 Задачи</button>
  <button class="tab" onclick="sw('food',this)">🥗 Питание</button>
  <button class="tab" onclick="sw('week',this)">📅 Неделя</button>
  <button class="tab" onclick="sw('shop',this)">🛒 Покупки</button>
  <button class="tab" onclick="sw('tips',this)">💡 Советы</button>
  <button class="tab" onclick="sw('myrec',this)">📖 Рецепты</button>
  <button class="tab" onclick="sw('plan',this)">📄 План</button>
</div>

<div id="tab-tasks" class="panel active">
  <div class="tab-hero-wrap">
    <img class="tab-hero" src="https://source.unsplash.com/800x360/?morning,productivity,desk" alt="" onerror="this.style.display='none'">
    <div class="tab-hero-title">Задачи на сегодня</div>
  </div>
  <ul class="checklist">{thtml}</ul>
</div>

<div id="tab-food" class="panel">
  <div class="tab-hero-wrap">
    <img class="tab-hero" src="https://source.unsplash.com/800x360/?healthy,food,nutrition" alt="" onerror="this.style.display='none'">
    <div class="tab-hero-title">Рацион на сегодня</div>
  </div>
  {tcards}
</div>

<div id="tab-week" class="panel">
  <div class="tab-hero-wrap">
    <img class="tab-hero" src="https://source.unsplash.com/800x360/?calendar,planning,week" alt="" onerror="this.style.display='none'">
    <div class="tab-hero-title">План на неделю</div>
  </div>
  {whtml}
</div>

<div id="tab-shop" class="panel">
  <div class="tab-hero-wrap">
    <img class="tab-hero" src="https://source.unsplash.com/800x360/?grocery,market,vegetables" alt="" onerror="this.style.display='none'">
    <div class="tab-hero-title">Список покупок</div>
  </div>
  <ul class="checklist">{shtml}</ul>
</div>

<div id="tab-tips" class="panel">
  <div class="tab-hero-wrap">
    <img class="tab-hero" src="https://source.unsplash.com/800x360/?wellness,mindfulness,health" alt="" onerror="this.style.display='none'">
    <div class="tab-hero-title">Советы дня</div>
  </div>
  {tips_html}
</div>

<div id="tab-myrec" class="panel" data-uid="{uid}">
  <div class="tab-hero-wrap">
    <img class="tab-hero" src="https://source.unsplash.com/800x360/?cookbook,recipe,kitchen" alt="" onerror="this.style.display='none'">
    <div class="tab-hero-title">Мои рецепты</div>
  </div>
  <p class="sec-title">Мои рецепты</p>
  <div id="my-recs-list">{mrhtml}</div>
</div>

<div id="tab-plan" class="panel">
  <div class="tab-hero-wrap">
    <img class="tab-hero" src="https://source.unsplash.com/800x360/?motivation,sunrise,nature" alt="" onerror="this.style.display='none'">
    <div class="tab-hero-title">План дня</div>
  </div>
  {surp_html}
  <div class="plan-content">{plan}</div>
</div>

{tpopups}
<div class="toast" id="toast"></div>

<script>
const UID = '{uid}';

function sw(name, btn) {{
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  btn.classList.add('active');
}}

function toggleCheck(el, id) {{
  el.classList.toggle('done');
  el.querySelector('.ch').textContent = el.classList.contains('done') ? '✓' : '○';
  try {{
    const d = JSON.parse(sessionStorage.getItem('chk_'+UID)||'{{}}');
    d[id] = el.classList.contains('done');
    sessionStorage.setItem('chk_'+UID, JSON.stringify(d));
  }} catch(e){{}}
}}

(function(){{
  try {{
    const d = JSON.parse(sessionStorage.getItem('chk_'+UID)||'{{}}');
    document.querySelectorAll('.ci').forEach(el=>{{
      if(d[el.dataset.id]){{ el.classList.add('done'); el.querySelector('.ch').textContent='✓'; }}
    }});
  }} catch(e){{}}
}})();

function openP(id){{ const e=document.getElementById(id); if(e){{e.classList.add('open');document.body.style.overflow='hidden';}} }}
function closeP(id){{ const e=document.getElementById(id); if(e){{e.classList.remove('open');document.body.style.overflow='';}} }}

function toggleAlts(id){{ const e=document.getElementById(id); if(e) e.style.display=e.style.display==='none'?'flex':'none'; }}

function toggleDay(id){{
  const b=document.getElementById(id);
  const h=b.previousElementSibling;
  const open=b.style.display==='block';
  b.style.display=open?'none':'block';
  h.classList.toggle('open',!open);
}}

function saveRec(name, desc){{
  try{{
    const recs = JSON.parse(sessionStorage.getItem('recs_'+UID)||'[]');
    if(!recs.find(r=>r.name===name)){{
      recs.push({{name, steps:desc, date:new Date().toLocaleDateString('ru')}});
      sessionStorage.setItem('recs_'+UID, JSON.stringify(recs));
      renderRecs(recs);
    }}
    showToast('💾 '+name+' сохранён!');
  }}catch(e){{}}
}}

function renderRecs(recs){{
  const c=document.getElementById('my-recs-list');
  if(!c) return;
  if(!recs.length){{ c.innerHTML='<div class="empty" style="padding:24px;text-align:center">Нажми 💾 в рецепте чтобы сохранить</div>'; return; }}
  c.innerHTML=recs.map(r=>{{
    const yt='https://www.youtube.com/results?search_query='+encodeURIComponent('рецепт '+r.name);
    return `<div class="my-rec"><div class="my-rec-name">${{r.name}}</div><div class="my-rec-steps">${{r.steps||''}}</div><a class="btn-yt-sm" href="${{yt}}" target="_blank">▶ YouTube</a></div>`;
  }}).join('');
}}

(function(){{
  try{{
    const recs=JSON.parse(sessionStorage.getItem('recs_'+UID)||'[]');
    if(recs.length) renderRecs(recs);
  }}catch(e){{}}
}})();

function showToast(msg){{
  const t=document.getElementById('toast');
  t.textContent=msg; t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2500);
}}

// Закрыть попап по Escape
document.addEventListener('keydown',e=>{{ if(e.key==='Escape') document.querySelectorAll('.popup-ov.open').forEach(p=>p.classList.remove('open')); }});
</script>
</body></html>"""
