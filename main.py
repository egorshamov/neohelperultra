import os
import time
import sqlite3
import requests
from flask import Flask, request

app = Flask(__name__)

# =========================================
# CONFIG
# =========================================

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

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    action TEXT,
    created_at REAL
)
""")

conn.commit()

# =========================================
# STATE
# =========================================

user_state = {}
admin_state = {}

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
        "images": 25
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
    "anime":
    "masterpiece anime style, ultra detailed, beautiful lighting",

    "realistic":
    "ultra realistic, cinematic lighting, 8k, highly detailed",

    "3d":
    "3d render, unreal engine 5, octane render, cinematic"
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
        VALUES (?,0,0,?,
        'basic',
        'smart',
        'realistic',
        0,
        0,
        ?)
        """, (chat_id, time.time(), time.time()))

        conn.commit()

# =========================================
# LOG SYSTEM
# =========================================

def add_log(chat_id, action):

    try:

        cursor.execute("""
        INSERT INTO logs (
            user_id,
            action,
            created_at
        )
        VALUES (?, ?, ?)
        """, (chat_id, action, time.time()))

        conn.commit()

    except:
        pass

# =========================================
# CLEANUP MEMORY
# =========================================

def cleanup_memory(chat_id):

    try:

        cursor.execute("""
        SELECT id
        FROM memory
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 20
        """, (chat_id,))

        rows = cursor.fetchall()

        ids = [str(x[0]) for x in rows]

        if not ids:
            return

        ids_str = ",".join(ids)

        cursor.execute(f"""
        DELETE FROM memory
        WHERE user_id=?
        AND id NOT IN ({ids_str})
        """, (chat_id,))

        conn.commit()

    except:
        pass

# =========================================
# RESET LIMITS
# =========================================

def reset_limits_if_needed(chat_id):

    try:

        cursor.execute("""
        SELECT last_reset
        FROM users
        WHERE user_id=?
        """, (chat_id,))

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

    except:
        pass

# =========================================
# PLAN
# =========================================

def get_plan(chat_id):

    try:

        cursor.execute("""
        SELECT plan
        FROM users
        WHERE user_id=?
        """, (chat_id,))

        row = cursor.fetchone()

        return row[0] if row else "basic"

    except:
        return "basic"

# =========================================
# ADMIN
# =========================================

def is_admin(chat_id):
    return str(chat_id) == str(ADMIN_ID)

# =========================================
# BAN
# =========================================

def is_banned(chat_id):

    try:

        cursor.execute("""
        SELECT banned
        FROM users
        WHERE user_id=?
        """, (chat_id,))

        row = cursor.fetchone()

        return row and row[0] == 1

    except:
        return False

# =========================================
# ANTI SPAM
# =========================================

def check_spam(chat_id, limit=1.2):

    plan = get_plan(chat_id)

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

    try:

        plan = get_plan(chat_id)

        limit = PLANS[plan]["messages"]

        cursor.execute("""
        SELECT messages
        FROM users
        WHERE user_id=?
        """, (chat_id,))

        row = cursor.fetchone()

        used = row[0] if row else 0

        if used >= limit:
            return False

        cursor.execute("""
        UPDATE users
        SET messages=messages+1
        WHERE user_id=?
        """, (chat_id,))

        conn.commit()

        return True

    except:
        return True

def check_image_limit(chat_id):

    try:

        plan = get_plan(chat_id)

        limit = PLANS[plan]["images"]

        cursor.execute("""
        SELECT images
        FROM users
        WHERE user_id=?
        """, (chat_id,))

        row = cursor.fetchone()

        used = row[0] if row else 0

        if used >= limit:
            return False

        cursor.execute("""
        UPDATE users
        SET images=images+1
        WHERE user_id=?
        """, (chat_id,))

        conn.commit()

        return True

    except:
        return True

# =========================================
# MEMORY SYSTEM
# =========================================

def save_memory(chat_id, role, content):

    try:

        cursor.execute("""
        INSERT INTO memory (
            user_id,
            role,
            content
        )
        VALUES (?, ?, ?)
        """, (chat_id, role, content))

        conn.commit()

        cleanup_memory(chat_id)

    except:
        pass

def load_memory(chat_id):

    try:

        cursor.execute("""
        SELECT role, content
        FROM memory
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 12
        """, (chat_id,))

        rows = cursor.fetchall()

        rows.reverse()

        arr = []

        for role, content in rows:

            arr.append({
                "role": role,
                "content": content
            })

        return arr

    except:
        return []

# =========================================
# AI SYSTEM
# =========================================

def ask_ai(chat_id, text):

    try:

        cursor.execute("""
        SELECT chat_mode
        FROM users
        WHERE user_id=?
        """, (chat_id,))

        row = cursor.fetchone()

        mode = row[0] if row else "smart"

        system = """
Ты современный AI ассистент.
Всегда отвечай на русском языке.
Будь полезным и умным.
"""

        if mode == "fast":
            system += "\nДавай короткие ответы."

        elif mode == "smart":
            system += "\nДавай умные ответы."

        elif mode == "deep":
            system += "\nДавай подробные ответы."

        elif mode == "pro_ai":
            system += """
Ты PRO AI.
Делай premium ответы.
"""

        messages = [{
            "role": "system",
            "content": system
        }]

        messages += load_memory(chat_id)

        messages.append({
            "role": "user",
            "content": text
        })

        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization":
                f"Bearer {OPENROUTER_API_KEY}"
            },
            json={
                "model":
                "deepseek/deepseek-chat-v3-0324:free",

                "messages": messages,

                "temperature": 0.85,

                "max_tokens": 1200
            },
            timeout=60
        )

        data = r.json()

        reply = data["choices"][0]["message"]["content"]

        save_memory(chat_id, "user", text)
        save_memory(chat_id, "assistant", reply)

        add_log(chat_id, "ai_message")

        return reply

    except:

        add_log(chat_id, "ai_error")

        return "⚠️ AI временно недоступен"

# =========================================
# IMAGE SYSTEM
# =========================================

def generate_image(prompt, style):

    style_prompt = IMAGE_STYLES.get(style)

    final_prompt = f"""
{prompt},
{style_prompt},
masterpiece,
high quality,
beautiful composition
"""

    return (
        "https://image.pollinations.ai/prompt/"
        + final_prompt.replace(" ", "%20")
    )

# =========================================
# SEND
# =========================================

def send(chat_id, text, kb=None):

    try:

        data = {
            "chat_id": chat_id,
            "text": text
        }

        if kb:
            data["reply_markup"] = kb

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=data,
            timeout=15
        )

    except:
        pass

def send_photo(chat_id, url, caption=None):

    try:

        data = {
            "chat_id": chat_id,
            "photo": url
        }

        if caption:
            data["caption"] = caption

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            json=data,
            timeout=20
        )

    except:
        pass

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

def admin_keyboard():

    return {
        "keyboard": [
            ["📈 Статистика"],
            ["💎 Выдать PRO"],
            ["👑 Выдать ULTRA"],
            ["🚫 Бан"],
            ["✅ Разбан"],
            ["🔙 Назад"]
        ],
        "resize_keyboard": True
    }

# =========================================
# ROUTER
# =========================================

@app.route("/webhook", methods=["POST"])
def webhook():

    try:

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

            send(chat_id,
            "⏳ Не так быстро :)")

            return "ok"

        # START
        if text == "/start":

            send(
                chat_id,
                "👋 Добро пожаловать в AI BOT V4",
                main_keyboard(chat_id)
            )

            add_log(chat_id, "start")

            return "ok"

        # BACK
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

        # CHAT
        if text == "💬 Чат":

            send(
                chat_id,
                "💬 Выбери режим:",
                chat_keyboard()
            )

            return "ok"

        # CHAT MODES
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

        # PRO AI
        if text == "🧠 PRO AI":

            plan = get_plan(chat_id)

            if plan == "basic":

                send(
                    chat_id,
                    "🚫 PRO AI только для PRO"
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

        # IMAGE MENU
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

        # IMAGE STYLES
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
                "🖼 Отправь описание картинки"
            )

            return "ok"

        # IMAGE GENERATION
        cursor.execute("""
        SELECT image_mode, image_style
        FROM users
        WHERE user_id=?
        """, (chat_id,))

        row = cursor.fetchone()

        if row and row[0] == 1:

            if not check_image_limit(chat_id):

                send(chat_id,
                "🚫 Лимит картинок")

                return "ok"

            image = generate_image(
                text,
                row[1]
            )

            send_photo(
                chat_id,
                image,
                "🖼 Картинка готова"
            )

            add_log(chat_id, "image_generation")

            return "ok"

        # LIMITS
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

        # ADMIN
        if text == "👑 Админ" and is_admin(chat_id):

            send(
                chat_id,
                "👑 Admin Panel",
                admin_keyboard()
            )

            return "ok"

        # ADMIN STATS
        if text == "📈 Статистика" and is_admin(chat_id):

            cursor.execute(
            "SELECT COUNT(*) FROM users")

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

            cursor.execute("""
            SELECT COUNT(*)
            FROM logs
            """)

            logs = cursor.fetchone()[0]

            send(
                chat_id,
f"""
📈 СТАТИСТИКА

👤 Users:
{users}

💎 PRO:
{pro}

👑 ULTRA:
{ultra}

📜 Logs:
{logs}
"""
            )

            return "ok"

        # GIVE PRO
        if text == "💎 Выдать PRO" and is_admin(chat_id):

            admin_state[chat_id] = "give_pro"

            send(chat_id,
            "ID пользователя?")

            return "ok"

        # GIVE ULTRA
        if text == "👑 Выдать ULTRA" and is_admin(chat_id):

            admin_state[chat_id] = "give_ultra"

            send(chat_id,
            "ID пользователя?")

            return "ok"

        # BAN
        if text == "🚫 Бан" and is_admin(chat_id):

            admin_state[chat_id] = "ban"

            send(chat_id,
            "ID пользователя?")

            return "ok"

        # UNBAN
        if text == "✅ Разбан" and is_admin(chat_id):

            admin_state[chat_id] = "unban"

            send(chat_id,
            "ID пользователя?")

            return "ok"

        # ADMIN ACTIONS
        if chat_id in admin_state and is_admin(chat_id):

            action = admin_state[chat_id]

            target = text

            if action == "give_pro":

                cursor.execute("""
                UPDATE users
                SET plan='pro'
                WHERE user_id=?
                """, (target,))

                conn.commit()

                send(chat_id,
                "✅ PRO выдан")

            elif action == "give_ultra":

                cursor.execute("""
                UPDATE users
                SET plan='ultra'
                WHERE user_id=?
                """, (target,))

                conn.commit()

                send(chat_id,
                "👑 ULTRA выдан")

            elif action == "ban":

                cursor.execute("""
                UPDATE users
                SET banned=1
                WHERE user_id=?
                """, (target,))

                conn.commit()

                send(chat_id,
                "🚫 Пользователь забанен")

            elif action == "unban":

                cursor.execute("""
                UPDATE users
                SET banned=0
                WHERE user_id=?
                """, (target,))

                conn.commit()

                send(chat_id,
                "✅ Пользователь разбанен")

            admin_state.pop(chat_id)

            return "ok"

        # LIMIT CHECK
        if not check_message_limit(chat_id):

            send(chat_id,
            "🚫 Лимит сообщений")

            return "ok"

        # AI
        reply = ask_ai(chat_id, text)

        send(
            chat_id,
            reply,
            main_keyboard(chat_id)
        )

        return "ok"

    except:
        return "ok"

@app.route("/")
def home():
    return "AI BOT V4 STABLE READY"

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )