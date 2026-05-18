# =========================================
# AI BOT V3 BETA
# STABLE RENDER FREE EDITION
# =========================================

import os
import time
import sqlite3
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ADMIN_ID = str(os.getenv("ADMIN_ID", ""))

# =========================================
# DATABASE
# =========================================

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    messages INTEGER DEFAULT 0,
    images INTEGER DEFAULT 0,
    last_reset REAL DEFAULT 0,
    plan TEXT DEFAULT 'basic',
    chat_mode TEXT DEFAULT 'smart',
    image_style TEXT DEFAULT 'realistic',
    image_mode INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0,
    created_at REAL DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    role TEXT,
    content TEXT
)
""")

conn.commit()

# =========================================
# MEMORY STATE
# =========================================

user_state = {}

# =========================================
# PLANS
# =========================================

PLANS = {
    "basic": {
        "messages": 40,
        "images": 3
    },

    "pro": {
        "messages": 300,
        "images": 20
    },

    "ultra": {
        "messages": 999999,
        "images": 999999
    }
}

# =========================================
# IMAGE STYLES
# =========================================

IMAGE_STYLES = {
    "anime": "anime style, detailed, beautiful",
    "realistic": "ultra realistic, cinematic lighting",
    "3d": "3d render, octane render, unreal engine"
}

# =========================================
# USER SYSTEM
# =========================================

def ensure_user(chat_id):

    cursor.execute(
        "SELECT user_id FROM users WHERE user_id=?",
        (chat_id,)
    )

    if not cursor.fetchone():

        cursor.execute("""
        INSERT INTO users (
            user_id,
            messages,
            images,
            last_reset,
            plan,
            chat_mode,
            image_style,
            image_mode,
            banned,
            created_at
        )
        VALUES (?, 0, 0, ?, 'basic', 'smart',
        'realistic', 0, 0, ?)
        """, (chat_id, time.time(), time.time()))

        conn.commit()

# =========================================
# RESET LIMITS
# =========================================

def reset_limits_if_needed(chat_id):

    cursor.execute(
        "SELECT last_reset FROM users WHERE user_id=?",
        (chat_id,)
    )

    row = cursor.fetchone()

    if not row:
        return

    if time.time() - row[0] > 86400:

        cursor.execute("""
        UPDATE users
        SET messages=0,
            images=0,
            last_reset=?
        WHERE user_id=?
        """, (time.time(), chat_id))

        conn.commit()

# =========================================
# PLAN
# =========================================

def get_plan(chat_id):

    cursor.execute(
        "SELECT plan FROM users WHERE user_id=?",
        (chat_id,)
    )

    row = cursor.fetchone()

    return row[0] if row else "basic"

# =========================================
# ADMIN
# =========================================

def is_admin(chat_id):
    return str(chat_id) == str(ADMIN_ID)

# =========================================
# BAN SYSTEM
# =========================================

def is_banned(chat_id):

    cursor.execute(
        "SELECT banned FROM users WHERE user_id=?",
        (chat_id,)
    )

    row = cursor.fetchone()

    return row and row[0] == 1

# =========================================
# ANTI SPAM
# =========================================

def check_spam(chat_id, limit=1.2):

    plan = get_plan(chat_id)

    # PRO / ULTRA без антиспама
    if plan in ["pro", "ultra"]:
        return True

    now = time.time()

    if chat_id in user_state:

        if now - user_state[chat_id] < limit:
            return False

    user_state[chat_id] = now

    return True

# =========================================
# LIMITS
# =========================================

def check_message_limit(chat_id):

    plan = get_plan(chat_id)

    limit = PLANS[plan]["messages"]

    cursor.execute(
        "SELECT messages FROM users WHERE user_id=?",
        (chat_id,)
    )

    row = cursor.fetchone()

    used = row[0] if row else 0

    if used >= limit:
        return False

    cursor.execute("""
    UPDATE users
    SET messages = messages + 1
    WHERE user_id=?
    """, (chat_id,))

    conn.commit()

    return True

def check_image_limit(chat_id):

    plan = get_plan(chat_id)

    limit = PLANS[plan]["images"]

    cursor.execute(
        "SELECT images FROM users WHERE user_id=?",
        (chat_id,)
    )

    row = cursor.fetchone()

    used = row[0] if row else 0

    if used >= limit:
        return False

    cursor.execute("""
    UPDATE users
    SET images = images + 1
    WHERE user_id=?
    """, (chat_id,))

    conn.commit()

    return True

# =========================================
# MEMORY SYSTEM
# =========================================

def save_memory(chat_id, role, content):

    cursor.execute("""
    INSERT INTO memory (user_id, role, content)
    VALUES (?, ?, ?)
    """, (chat_id, role, content))

    conn.commit()

def load_memory(chat_id):

    cursor.execute("""
    SELECT role, content
    FROM memory
    WHERE user_id=?
    ORDER BY id DESC
    LIMIT 10
    """, (chat_id,))

    rows = cursor.fetchall()

    rows.reverse()

    msgs = []

    for role, content in rows:

        msgs.append({
            "role": role,
            "content": content
        })

    return msgs

# =========================================
# AI SYSTEM
# =========================================

def ask_ai(chat_id, text):

    cursor.execute(
        "SELECT chat_mode FROM users WHERE user_id=?",
        (chat_id,)
    )

    row = cursor.fetchone()

    mode = row[0] if row else "smart"

    system = """
Ты профессиональный AI ассистент Telegram.
Всегда отвечай только на русском языке.
Будь умным, полезным и современным.
"""

    if mode == "fast":
        system += "\nКороткие ответы."

    elif mode == "smart":
        system += "\nУмные обычные ответы."

    elif mode == "deep":
        system += "\nОчень подробные ответы."

    elif mode == "pro_ai":
        system += """
Ты PRO AI.
Очень глубокие,
структурированные,
умные ответы уровня premium.
"""

    messages = [
        {
            "role": "system",
            "content": system
        }
    ]

    messages += load_memory(chat_id)

    messages.append({
        "role": "user",
        "content": text
    })

    try:

        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}"
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 900
            },
            timeout=60
        )

        data = r.json()

        reply = data["choices"][0]["message"]["content"]

        save_memory(chat_id, "user", text)
        save_memory(chat_id, "assistant", reply)

        return reply

    except:
        return "⚠️ AI временно недоступен"

# =========================================
# IMAGE SYSTEM
# =========================================

def make_image(prompt, style):

    style_prompt = IMAGE_STYLES.get(style)

    final = f"{prompt}, {style_prompt}"

    return (
        "https://image.pollinations.ai/prompt/"
        + final.replace(" ", "%20")
    )

# =========================================
# SEND
# =========================================

def send(chat_id, text, kb=None):

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if kb:
        data["reply_markup"] = kb

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=data
    )

def send_photo(chat_id, url, caption=None):

    data = {
        "chat_id": chat_id,
        "photo": url
    }

    if caption:
        data["caption"] = caption

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        json=data
    )

# =========================================
# KEYBOARDS
# =========================================

def main_keyboard(chat_id):

    kb = [
        ["💬 Чат", "🧠 PRO AI"],
        ["🖼 Картинка", "💳 PRO"],
        ["📊 Лимиты"]
    ]

    if is_admin(chat_id):
        kb.append(["👑 Админ"])

    return {
        "keyboard": kb,
        "resize_keyboard": True
    }

def chat_keyboard():

    return {
        "keyboard": [
            ["⚡ Быстрый", "🧠 Умный"],
            ["📚 Подробный"],
            ["🔙 Назад"]
        ],
        "resize_keyboard": True
    }

def image_keyboard():

    return {
        "keyboard": [
            ["🎨 Anime", "📸 Realistic"],
            ["🧊 3D"],
            ["🔙 Назад"]
        ],
        "resize_keyboard": True
    }

def pro_keyboard():

    return {
        "keyboard": [
            ["🔹 PRO - 120⭐"],
            ["💎 ULTRA - 500⭐"],
            ["🔙 Назад"]
        ],
        "resize_keyboard": True
    }

def admin_keyboard():

    return {
        "keyboard": [
            ["📈 Статистика"],
            ["🔙 Назад"]
        ],
        "resize_keyboard": True
    }

# =========================================
# ROUTER
# =========================================

@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.json

    msg = data.get("message", {})

    chat_id = str(
        msg.get("chat", {}).get("id")
    )

    text = msg.get("text", "")

    if not chat_id:
        return "ok"

    ensure_user(chat_id)

    if is_banned(chat_id):
        return "ok"

    reset_limits_if_needed(chat_id)

    if not check_spam(chat_id):

        send(
            chat_id,
            "⏳ Не так быстро :)"
        )

        return "ok"

    # =====================================
    # START
    # =====================================

    if text == "/start":

        send(
            chat_id,
            "👋 Добро пожаловать в AI BOT V3",
            main_keyboard(chat_id)
        )

        return "ok"

    # =====================================
    # BACK
    # =====================================

    if text == "🔙 Назад":

        cursor.execute("""
        UPDATE users
        SET image_mode=0
        WHERE user_id=?
        """, (chat_id,))

        conn.commit()

        send(
            chat_id,
            "🏠 Главное меню",
            main_keyboard(chat_id)
        )

        return "ok"

    # =====================================
    # CHAT MENU
    # =====================================

    if text == "💬 Чат":

        send(
            chat_id,
            "💬 Выбери режим:",
            chat_keyboard()
        )

        return "ok"

    # =====================================
    # CHAT MODES
    # =====================================

    modes = {
        "⚡ Быстрый": "fast",
        "🧠 Умный": "smart",
        "📚 Подробный": "deep"
    }

    if text in modes:

        cursor.execute("""
        UPDATE users
        SET chat_mode=?
        WHERE user_id=?
        """, (modes[text], chat_id))

        conn.commit()

        send(
            chat_id,
            "✅ Режим обновлён",
            chat_keyboard()
        )

        return "ok"

    # =====================================
    # PRO AI
    # =====================================

    if text == "🧠 PRO AI":

        plan = get_plan(chat_id)

        if plan == "basic":

            send(
                chat_id,
                "🚫 PRO AI доступен только для PRO пользователей"
            )

            return "ok"

        cursor.execute("""
        UPDATE users
        SET chat_mode='pro_ai'
        WHERE user_id=?
        """, (chat_id,))

        conn.commit()

        send(
            chat_id,
            "🧠 PRO AI включён",
            main_keyboard(chat_id)
        )

        return "ok"

    # =====================================
    # IMAGE MENU
    # =====================================

    if text == "🖼 Картинка":

        cursor.execute("""
        UPDATE users
        SET image_mode=1
        WHERE user_id=?
        """, (chat_id,))

        conn.commit()

        send(
            chat_id,
            "🎨 Выбери стиль:",
            image_keyboard()
        )

        return "ok"

    # =====================================
    # IMAGE STYLE
    # =====================================

    styles = {
        "🎨 Anime": "anime",
        "📸 Realistic": "realistic",
        "🧊 3D": "3d"
    }

    if text in styles:

        cursor.execute("""
        UPDATE users
        SET image_style=?
        WHERE user_id=?
        """, (styles[text], chat_id))

        conn.commit()

        send(
            chat_id,
            "🖼 Теперь отправь описание картинки"
        )

        return "ok"

    # =====================================
    # IMAGE GENERATION
    # =====================================

    cursor.execute("""
    SELECT image_mode, image_style
    FROM users
    WHERE user_id=?
    """, (chat_id,))

    row = cursor.fetchone()

    if row and row[0] == 1:

        if text.startswith("/"):
            return "ok"

        if not check_image_limit(chat_id):

            send(
                chat_id,
                "🚫 Лимит картинок"
            )

            return "ok"

        img = make_image(text, row[1])

        send_photo(
            chat_id,
            img,
            "🖼 Картинка готова"
        )

        return "ok"

    # =====================================
    # PRO MENU
    # =====================================

    if text == "💳 PRO":

        send(
            chat_id,
            "💎 Платные тарифы:\n\n🔹 PRO — 120⭐\n💎 ULTRA — 500⭐",
            pro_keyboard()
        )

        return "ok"

    # =====================================
    # BLOCK FREE PRO
    # =====================================

    if text in ["🔹 PRO - 120⭐", "💎 ULTRA - 500⭐"]:

        send(
            chat_id,
            "⭐ Покупка через Telegram Stars скоро будет подключена"
        )

        return "ok"

    # =====================================
    # LIMITS
    # =====================================

    if text == "📊 Лимиты":

        plan = get_plan(chat_id)

        msg_limit = PLANS[plan]["messages"]
        img_limit = PLANS[plan]["images"]

        cursor.execute("""
        SELECT messages, images
        FROM users
        WHERE user_id=?
        """, (chat_id,))

        used_msg, used_img = cursor.fetchone()

        send(
            chat_id,
            f"""
📊 ЛИМИТЫ

💬 Сообщения:
{used_msg}/{msg_limit}

🖼 Картинки:
{used_img}/{img_limit}

💎 План:
{plan}
""",
            main_keyboard(chat_id)
        )

        return "ok"

    # =====================================
    # ADMIN PANEL
    # =====================================

    if text == "👑 Админ" and is_admin(chat_id):

        send(
            chat_id,
            "👑 Admin Panel",
            admin_keyboard()
        )

        return "ok"

    if text == "📈 Статистика" and is_admin(chat_id):

        cursor.execute("SELECT COUNT(*) FROM users")
        users = cursor.fetchone()[0]

        cursor.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE plan='pro'
        """)
        pro = cursor.fetchone()[0]

        cursor.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE plan='ultra'
        """)
        ultra = cursor.fetchone()[0]

        send(
            chat_id,
            f"""
📈 СТАТИСТИКА

👤 Пользователей:
{users}

🔹 PRO:
{pro}

💎 ULTRA:
{ultra}
"""
        )

        return "ok"

    # =====================================
    # MESSAGE LIMIT
    # =====================================

    if not check_message_limit(chat_id):

        send(
            chat_id,
            "🚫 Лимит сообщений"
        )

        return "ok"

    # =====================================
    # AI RESPONSE
    # =====================================

    reply = ask_ai(chat_id, text)

    send(
        chat_id,
        reply,
        main_keyboard(chat_id)
    )

    return "ok"

# =========================================
# HOME
# =========================================

@app.route("/")
def home():
    return "AI BOT V3 STABLE"

# =========================================
# RUN
# =========================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )