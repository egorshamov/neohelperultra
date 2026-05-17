import os
import time
import sqlite3
import requests
from flask import Flask, request

app = Flask(__name__)

# =====================
# CONFIG
# =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ADMIN_ID = str(os.getenv("ADMIN_ID", ""))

COOLDOWN = 3

# =====================
# DB
# =====================
conn = sqlite3.connect("neohelper.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    messages INTEGER DEFAULT 0,
    last_time REAL DEFAULT 0,
    image_used INTEGER DEFAULT 0,
    image_reset REAL DEFAULT 0,
    last_reply TEXT DEFAULT ''
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    user_id TEXT,
    role TEXT,
    content TEXT
)
""")

conn.commit()

# =====================
# USER
# =====================
def get_user(user_id):
    cursor.execute(
        "SELECT messages, last_time, image_used, image_reset, last_reply FROM users WHERE user_id=?",
        (user_id,)
    )
    return cursor.fetchone()

def register(user_id):
    if not get_user(user_id):
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                       (user_id, 0, 0, 0, 0, ""))
        conn.commit()

def is_admin(user_id):
    return str(user_id) == ADMIN_ID

# =====================
# LIMITS
# =====================
def check_limit(user_id):
    if is_admin(user_id):
        return None

    user = get_user(user_id)
    if not user:
        register(user_id)
        user = (0, 0, 0, 0, "")

    messages, last_time, _, _, _ = user
    now = time.time()

    if now - last_time < COOLDOWN:
        return "⏳ Слишком быстро"

    cursor.execute("""
        UPDATE users
        SET messages = messages + 1,
            last_time = ?
        WHERE user_id=?
    """, (now, user_id))

    conn.commit()
    return None

# =====================
# IMAGE LIMIT (1/day)
# =====================
def can_use_image(user_id):
    if is_admin(user_id):
        return True

    user = get_user(user_id)
    if not user:
        register(user_id)
        return True

    _, _, img_used, img_reset, _ = user
    now = time.time()

    if now - img_reset > 86400:
        cursor.execute("""
            UPDATE users
            SET image_used=0, image_reset=?
            WHERE user_id=?
        """, (now, user_id))
        conn.commit()
        return True

    if img_used >= 1:
        return False

    cursor.execute("""
        UPDATE users
        SET image_used = image_used + 1,
            image_reset = ?
        WHERE user_id=?
    """, (now, user_id))

    conn.commit()
    return True

# =====================
# IMAGE
# =====================
def make_image(prompt):
    prompt = prompt.replace(" ", "%20")
    return f"https://image.pollinations.ai/prompt/{prompt}, cinematic, ultra realistic"

def is_image(text):
    return any(k in text.lower() for k in ["нарисуй", "картинка", "создай", "изобрази"])

# =====================
# MEMORY (NO REPEATS)
# =====================
def save_memory(user_id, role, content):
    cursor.execute("INSERT INTO memory VALUES (?, ?, ?)", (user_id, role, content))

    cursor.execute("""
        DELETE FROM memory
        WHERE rowid NOT IN (
            SELECT rowid FROM memory
            WHERE user_id=?
            ORDER BY rowid DESC
            LIMIT 4
        )
        AND user_id=?
    """, (user_id, user_id))

    conn.commit()

# =====================
# ANTI REPEAT ANSWER
# =====================
def is_repeat(user_id, answer):
    cursor.execute("SELECT last_reply FROM users WHERE user_id=?", (user_id,))
    last = cursor.fetchone()[0]
    return last == answer

def save_reply(user_id, answer):
    cursor.execute("UPDATE users SET last_reply=? WHERE user_id=?", (answer, user_id))
    conn.commit()

# =====================
# AI
# =====================
def ask_ai(user_id, text):

    cursor.execute("""
        SELECT role, content FROM memory
        WHERE user_id=?
        ORDER BY rowid DESC
        LIMIT 4
    """, (user_id,))

    history = cursor.fetchall()[::-1]

    messages = [
        {
            "role": "system",
            "content": "Ты NeoHelper — умный, краткий, не повторяющийся AI ассистент."
        }
    ]

    for h in history:
        messages.append({"role": h[0], "content": h[1]})

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": messages,
                "max_tokens": 250
            },
            timeout=12
        )

        if r.status_code != 200:
            return "⚠️ AI недоступен"

        answer = r.json()["choices"][0]["message"]["content"]

        if is_repeat(user_id, answer):
            answer = "🤖 Я уже отвечал на это, попробуй уточнить вопрос."

        save_reply(user_id, answer)

        save_memory(user_id, "user", text)
        save_memory(user_id, "assistant", answer)

        return answer

    except:
        return "⚠️ AI error"

# =====================
# TELEGRAM SEND
# =====================
def send(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text}
    if keyboard:
        payload["reply_markup"] = keyboard

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=payload,
        timeout=8
    )

def send_image(chat_id, url):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        json={"chat_id": chat_id, "photo": url},
        timeout=8
    )

# =====================
# MENU
# =====================
def main_menu():
    return {
        "inline_keyboard": [
            [
                {"text": "💬 Чат", "callback_data": "chat"},
                {"text": "🖼 Картинка", "callback_data": "image"}
            ],
            [
                {"text": "👤 Профиль", "callback_data": "profile"},
                {"text": "ℹ️ Инфо", "callback_data": "info"}
            ]
        ]
    }

# =====================
# CALLBACK HANDLER
# =====================
def handle_callback(data, chat_id, user_id):

    if data == "profile":
        user = get_user(user_id)
        send(chat_id, f"👤 Профиль\n\n💬 Сообщения: {user[0]}")
        return

    if data == "info":
        send(chat_id,
            "🤖 NeoHelper\n\n"
            "💬 Чат AI\n"
            "🖼 Генерация картинок (1/день)\n"
            "🎤 Голос (Lite)\n"
            "⚡ Быстрый и стабильный бот"
        )
        return

    if data == "image":
        send(chat_id, "Напиши: 'нарисуй ...'")
        return

    if data == "chat":
        send(chat_id, "💬 Напиши сообщение и я отвечу как AI")
        return

# =====================
# ROUTER
# =====================
def router(text, user_id, chat_id):

    if is_image(text):
        if can_use_image(user_id):
            send_image(chat_id, make_image(text))
        else:
            send(chat_id, "🚫 Лимит: 1 изображение в день")
        return True

    return False

# =====================
# WEBHOOK
# =====================
@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json()
    if not data:
        return "ok"

    # callback buttons
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        user_id = str(chat_id)
        handle_callback(cq["data"], chat_id, user_id)
        return "ok"

    if "message" in data:

        msg = data["message"]
        chat_id = msg["chat"]["id"]
        user_id = str(chat_id)

        register(user_id)

        # show menu always on /start
        if msg.get("text", "") == "/start":
            send(chat_id, "🤖 Добро пожаловать в NeoHelper", main_menu())
            return "ok"

        # limits
        limit = check_limit(user_id)
        if limit:
            send(chat_id, limit)
            return "ok"

        text = msg.get("text", "")

        # router
        if router(text, user_id, chat_id):
            return "ok"

        # AI
        reply = ask_ai(user_id, text)
        send(chat_id, reply, main_menu())

        return "ok"

    return "ok"

# =====================
# HOME
# =====================
@app.route("/")
def home():
    return "NeoHelper online"

# =====================
# RUN
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)