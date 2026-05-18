import os
import time
import sqlite3
import requests
from flask import Flask, request

app = Flask(__name__)

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_ID = str(os.getenv("ADMIN_ID", ""))

# ================= DATABASE =================

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
    banned INTEGER DEFAULT 0
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
    created REAL
)
""")

conn.commit()

# ================= STATE =================

user_state = {}

# ================= PLANS =================

PLANS = {
    "basic": {"messages": 40, "images": 3},
    "pro": {"messages": 300, "images": 20},
    "ultra": {"messages": 999999, "images": 999999}
}

# ================= USER =================

def ensure_user(chat_id):

    cursor.execute("""
    SELECT user_id FROM users
    WHERE user_id=?
    """, (chat_id,))

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
            banned
        )
        VALUES (?, 0, 0, ?, 'basic', 'smart', 'realistic', 0)
        """, (chat_id, time.time()))

        conn.commit()

# ================= LOGS =================

def add_log(chat_id, action):

    cursor.execute("""
    INSERT INTO logs (
        user_id,
        action,
        created
    )
    VALUES (?, ?, ?)
    """, (chat_id, action, time.time()))

    conn.commit()

# ================= MEMORY =================

def save_memory(chat_id, role, content):

    cursor.execute("""
    INSERT INTO memory (
        user_id,
        role,
        content
    )
    VALUES (?, ?, ?)
    """, (chat_id, role, content))

    conn.commit()

    cursor.execute("""
    SELECT id
    FROM memory
    WHERE user_id=?
    ORDER BY id DESC
    """, (chat_id,))

    rows = cursor.fetchall()

    if len(rows) > 20:

        ids = [str(x[0]) for x in rows[20:]]

        cursor.execute(f"""
        DELETE FROM memory
        WHERE id IN ({",".join(ids)})
        """)

        conn.commit()

def load_memory(chat_id):

    cursor.execute("""
    SELECT role, content
    FROM memory
    WHERE user_id=?
    ORDER BY id ASC
    LIMIT 12
    """, (chat_id,))

    rows = cursor.fetchall()

    memory = []

    for role, content in rows:

        memory.append({
            "role": role,
            "content": content
        })

    return memory

# ================= RESET =================

def reset_limits_if_needed(chat_id):

    cursor.execute("""
    SELECT last_reset
    FROM users
    WHERE user_id=?
    """, (chat_id,))

    row = cursor.fetchone()

    if row:

        if time.time() - row[0] > 86400:

            cursor.execute("""
            UPDATE users
            SET messages=0,
                images=0,
                last_reset=?
            WHERE user_id=?
            """, (time.time(), chat_id))

            conn.commit()

# ================= HELPERS =================

def get_plan(chat_id):

    cursor.execute("""
    SELECT plan
    FROM users
    WHERE user_id=?
    """, (chat_id,))

    row = cursor.fetchone()

    return row[0] if row else "basic"

def is_admin(chat_id):
    return str(chat_id) == str(ADMIN_ID)

def is_banned(chat_id):

    cursor.execute("""
    SELECT banned
    FROM users
    WHERE user_id=?
    """, (chat_id,))

    row = cursor.fetchone()

    return row and row[0] == 1

# ================= ANTI SPAM =================

def check_spam(chat_id, limit=1.0):

    plan = get_plan(chat_id)

    if plan in ["pro", "ultra"]:
        return True

    now = time.time()

    if chat_id in user_state:

        if now - user_state[chat_id] < limit:
            return False

    user_state[chat_id] = now

    return True

# ================= LIMITS =================

def check_message_limit(chat_id):

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
    SET messages = messages + 1
    WHERE user_id=?
    """, (chat_id,))

    conn.commit()

    return True

def check_image_limit(chat_id):

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
    SET images = images + 1
    WHERE user_id=?
    """, (chat_id,))

    conn.commit()

    return True

# ================= AI =================

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
Ты NeoHelper AI ассистент.
Всегда отвечай только на русском языке.
Будь полезным и умным.
"""

        if mode == "fast":
            system += "\nКороткие ответы."

        elif mode == "smart":
            system += "\nУмные ответы."

        elif mode == "deep":
            system += "\nПодробные ответы."

        elif mode == "pro_ai":
            system += "\nТы premium PRO AI."

        messages = [{
            "role": "system",
            "content": system
        }]

        try:
            messages += load_memory(chat_id)
        except:
            pass

        messages.append({
            "role": "user",
            "content": text
        })

        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",

            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },

            json={
                "model": "llama3-8b-8192",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1000
            },

            timeout=60
        )

        print("STATUS:", r.status_code)
        print("TEXT:", r.text)

        if r.status_code != 200:
            return f"⚠️ AI ERROR {r.status_code}"

        try:
            data = r.json()
        except:
            return "⚠️ Ошибка JSON"

        if "choices" not in data:
            return "⚠️ Нет choices"

        if not data["choices"]:
            return "⚠️ Пустой ответ"

        reply = data["choices"][0]["message"]["content"]

        try:
            save_memory(chat_id, "user", text)
            save_memory(chat_id, "assistant", reply)
        except:
            pass

        try:
            add_log(chat_id, "ai_message")
        except:
            pass

        return reply

    except Exception as e:

        print("AI ERROR:", e)

        return "⚠️ Ошибка подключения AI"

# ================= IMAGE =================

IMAGE_STYLES = {
    "anime": "anime style, masterpiece",
    "realistic": "ultra realistic, cinematic lighting",
    "3d": "3d render, octane render"
}

def generate_image(prompt, style):

    enhanced = f"""
{prompt},
{IMAGE_STYLES.get(style, 'realistic')}
"""

    return "https://image.pollinations.ai/prompt/" + enhanced.replace(" ", "%20")

# ================= SEND =================

def send(chat_id, text, kb=None):

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if kb:
        data["reply_markup"] = kb

    try:

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=data,
            timeout=30
        )

    except Exception as e:
        print(e)

def send_photo(chat_id, photo):

    try:

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",

            json={
                "chat_id": chat_id,
                "photo": photo
            },

            timeout=60
        )

    except Exception as e:
        print(e)

# ================= KEYBOARDS =================

def keyboard(chat_id):

    kb = [
        ["💬 Чат", "🧠 PRO AI"],
        ["🖼 Картинка", "📊 Лимиты"],
        ["💎 Купить PRO"]
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
            ["⚡ Быстро", "🧠 Умно"],
            ["📚 Подробно"],
            ["🔙 Назад"]
        ],
        "resize_keyboard": True
    }

def image_keyboard():

    return {
        "keyboard": [
            ["🎨 anime"],
            ["📸 realistic"],
            ["🧊 3d"],
            ["🔙 Назад"]
        ],
        "resize_keyboard": True
    }

def admin_keyboard():

    return {
        "keyboard": [
            ["📊 Статистика"],
            ["🔙 Назад"]
        ],
        "resize_keyboard": True
    }

# ================= ROUTER =================

@app.route("/webhook", methods=["POST"])
def webhook():

    try:

        data = request.json

        if not data:
            return "ok"

        msg = data.get("message", {})

        chat_id = str(msg.get("chat", {}).get("id"))

        text = msg.get("text", "")

        if not chat_id:
            return "ok"

        ensure_user(chat_id)

        reset_limits_if_needed(chat_id)

        if is_banned(chat_id):
            return "ok"

        if not check_spam(chat_id):

            send(chat_id, "⏳ Слишком быстро")

            return "ok"

        # START

        if text == "/start":

            add_log(chat_id, "start")

            send(
                chat_id,
                "👋 Добро пожаловать в NeoHelper AI",
                keyboard(chat_id)
            )

            return "ok"

        # CHAT

        if text == "💬 Чат":

            send(
                chat_id,
                "💬 Выбери режим",
                chat_keyboard()
            )

            return "ok"

        if text == "⚡ Быстро":

            cursor.execute("""
            UPDATE users
            SET chat_mode='fast'
            WHERE user_id=?
            """, (chat_id,))

            conn.commit()

            send(chat_id, "⚡ Быстрый режим", keyboard(chat_id))

            return "ok"

        if text == "🧠 Умно":

            cursor.execute("""
            UPDATE users
            SET chat_mode='smart'
            WHERE user_id=?
            """, (chat_id,))

            conn.commit()

            send(chat_id, "🧠 Умный режим", keyboard(chat_id))

            return "ok"

        if text == "📚 Подробно":

            cursor.execute("""
            UPDATE users
            SET chat_mode='deep'
            WHERE user_id=?
            """, (chat_id,))

            conn.commit()

            send(chat_id, "📚 Подробный режим", keyboard(chat_id))

            return "ok"

        # PRO AI

        if text == "🧠 PRO AI":

            if get_plan(chat_id) == "basic":

                send(chat_id, "🚫 Только для PRO")

                return "ok"

            cursor.execute("""
            UPDATE users
            SET chat_mode='pro_ai'
            WHERE user_id=?
            """, (chat_id,))

            conn.commit()

            send(chat_id, "🧠 PRO AI включён", keyboard(chat_id))

            return "ok"

        # IMAGE

        if text == "🖼 Картинка":

            send(
                chat_id,
                "🎨 Выбери стиль",
                image_keyboard()
            )

            return "ok"

        if text in ["🎨 anime", "📸 realistic", "🧊 3d"]:

            styles = {
                "🎨 anime": "anime",
                "📸 realistic": "realistic",
                "🧊 3d": "3d"
            }

            style = styles[text]

            cursor.execute("""
            UPDATE users
            SET image_style=?
            WHERE user_id=?
            """, (style, chat_id))

            conn.commit()

            send(
                chat_id,
                f"🎨 Стиль {style} выбран\n\nОтправь описание картинки"
            )

            return "ok"

        # LIMITS

        if text == "📊 Лимиты":

            plan = get_plan(chat_id)

            cursor.execute("""
            SELECT messages, images
            FROM users
            WHERE user_id=?
            """, (chat_id,))

            row = cursor.fetchone()

            send(
                chat_id,
                f"""
📊 Лимиты

💬 Сообщения:
{row[0]}/{PLANS[plan]["messages"]}

🖼 Картинки:
{row[1]}/{PLANS[plan]["images"]}

💎 План:
{plan}
""",
                keyboard(chat_id)
            )

            return "ok"

        # ADMIN

        if text == "👑 Админ" and is_admin(chat_id):

            send(
                chat_id,
                "👑 Админ панель",
                admin_keyboard()
            )

            return "ok"

        if text == "📊 Статистика" and is_admin(chat_id):

            cursor.execute("SELECT COUNT(*) FROM users")
            users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM logs")
            logs = cursor.fetchone()[0]

            send(
                chat_id,
                f"""
📊 Статистика

👥 Пользователи: {users}
📝 Логи: {logs}
"""
            )

            return "ok"

        # BACK

        if text == "🔙 Назад":

            send(chat_id, "🏠 Главное меню", keyboard(chat_id))

            return "ok"

        # IMAGE GENERATION

        image_words = [
            "нарисуй",
            "создай",
            "картинка",
            "draw",
            "image"
        ]

        if any(word in text.lower() for word in image_words):

            if not check_image_limit(chat_id):

                send(chat_id, "🚫 Лимит картинок")

                return "ok"

            cursor.execute("""
            SELECT image_style
            FROM users
            WHERE user_id=?
            """, (chat_id,))

            row = cursor.fetchone()

            style = row[0] if row else "realistic"

            photo = generate_image(text, style)

            send_photo(chat_id, photo)

            add_log(chat_id, "image")

            return "ok"

        # AI LIMIT

        if not check_message_limit(chat_id):

            send(chat_id, "🚫 Лимит сообщений")

            return "ok"

        # AI

        reply = ask_ai(chat_id, text)

        send(chat_id, reply, keyboard(chat_id))

        return "ok"

    except Exception as e:

        print("WEBHOOK ERROR:", e)

        return "ok"

# ================= HOME =================

@app.route("/")
def home():
    return "NeoHelper V5 Stable"

# ================= RUN =================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )