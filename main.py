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

DAILY_LIMIT = 30
COOLDOWN = 3.5
IMAGE_LIMIT = 1

# =====================
# DB
# =====================
conn = sqlite3.connect("neohelper.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    user_id TEXT,
    role TEXT,
    content TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    messages INTEGER DEFAULT 0,
    last_time REAL DEFAULT 0,
    images INTEGER DEFAULT 0,
    image_time REAL DEFAULT 0
)
""")

conn.commit()

# =====================
# UI
# =====================
def keyboard(user_id):
    is_admin = str(user_id) == ADMIN_ID

    buttons = [
        [
            {"text": "👤 Профиль", "callback_data": "profile"},
            {"text": "🆕 Новый чат", "callback_data": "new"}
        ]
    ]

    if is_admin:
        buttons.insert(0, [
            {"text": "📊 Админ панель", "callback_data": "admin"}
        ])

    return {"inline_keyboard": buttons}

# =====================
# SEND TEXT
# =====================
def send(chat_id, text, user_id):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "reply_markup": keyboard(user_id)
            },
            timeout=10
        )
    except:
        pass

# =====================
# SEND IMAGE
# =====================
def send_image(chat_id, url):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            json={
                "chat_id": chat_id,
                "photo": url,
                "caption": "🖼 NeoHelper AI"
            },
            timeout=10
        )
    except:
        pass

# =====================
# USER
# =====================
def get_user(user_id):
    cursor.execute(
        "SELECT messages, last_time, images, image_time FROM users WHERE user_id=?",
        (user_id,)
    )
    return cursor.fetchone()

def register(user_id):
    if not get_user(user_id):
        cursor.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
            (user_id, 0, 0, 0, 0)
        )
        conn.commit()

# =====================
# LIMITS
# =====================
def check_message_limit(user_id):

    if str(user_id) == ADMIN_ID:
        return None

    user = get_user(user_id)
    if not user:
        register(user_id)
        user = (0, 0, 0, 0)

    messages, last_time, images, img_time = user
    now = time.time()

    if now - last_time < COOLDOWN:
        return "⏳ Слишком быстро"

    if messages >= DAILY_LIMIT:
        return "🚫 Лимит сообщений исчерпан (30/день)"

    cursor.execute("""
        UPDATE users
        SET messages = messages + 1,
            last_time = ?
        WHERE user_id=?
    """, (now, user_id))

    conn.commit()

    return None


def check_image_limit(user_id):

    if str(user_id) == ADMIN_ID:
        return None

    user = get_user(user_id)
    if not user:
        register(user_id)
        user = (0, 0, 0, 0)

    messages, last_time, images, img_time = user
    now = time.time()

    if images >= IMAGE_LIMIT:
        return "🚫 Лимит картинок (1/день)"

    cursor.execute("""
        UPDATE users
        SET images = images + 1,
            image_time = ?
        WHERE user_id=?
    """, (now, user_id))

    conn.commit()

    return None

# =====================
# IMAGE AI
# =====================
def is_image(text):
    keys = ["нарисуй", "картинка", "рисунок", "изобрази"]
    return any(k in text.lower() for k in keys)

def make_image(prompt):
    prompt = prompt.replace(" ", "%20")
    return f"https://image.pollinations.ai/prompt/{prompt}"

# =====================
# AI
# =====================
def ask_ai(user_id, text):

    cursor.execute("""
        SELECT role, content FROM memory
        WHERE user_id=?
        ORDER BY rowid DESC
        LIMIT 12
    """, (user_id,))

    history = cursor.fetchall()[::-1]

    messages = [
        {
            "role": "system",
            "content": "Ты NeoHelper — умный, стабильный AI помощник."
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
                "messages": messages
            },
            timeout=20
        )

        if r.status_code != 200:
            return "⚠️ AI недоступен"

        answer = r.json()["choices"][0]["message"]["content"]

        cursor.execute(
            "INSERT INTO memory VALUES (?, ?, ?)",
            (user_id, "user", text)
        )
        cursor.execute(
            "INSERT INTO memory VALUES (?, ?, ?)",
            (user_id, "assistant", answer)
        )
        conn.commit()

        return f"🤖 NeoHelper\n\n{answer}"

    except:
        return "⚠️ Ошибка AI"

# =====================
# CALLBACK
# =====================
def handle_cb(data, chat_id, user_id):

    if data == "profile":
        send(chat_id, f"👤 ID: {user_id}", user_id)

    elif data == "new":
        cursor.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
        conn.commit()
        send(chat_id, "🆕 Новый чат создан", user_id)

    elif data == "admin":

        if str(user_id) != ADMIN_ID:
            send(chat_id, "⛔ Нет доступа", user_id)
            return

        cursor.execute("SELECT COUNT(*) FROM users")
        users = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(messages) FROM users")
        msgs = cursor.fetchone()[0] or 0

        send(chat_id,
            f"📊 ADMIN PANEL\n\n"
            f"👥 Users: {users}\n"
            f"💬 Messages: {msgs}",
            user_id
        )

# =====================
# WEBHOOK
# =====================
@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json()
    if not data:
        return "ok"

    if "message" in data:

        msg = data["message"]

        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        user_id = str(chat_id)

        register(user_id)

        # MESSAGE LIMIT
        limit = check_message_limit(user_id)
        if limit:
            send(chat_id, limit, user_id)
            return "ok"

        # IMAGE MODE
        if is_image(text):
            img_limit = check_image_limit(user_id)
            if img_limit:
                send(chat_id, img_limit, user_id)
                return "ok"

            prompt = text
            for w in ["нарисуй", "картинка", "рисунок", "изобрази"]:
                prompt = prompt.replace(w, "")

            img_url = make_image(prompt.strip())
            send_image(chat_id, img_url)
            return "ok"

        # AI MODE
        reply = ask_ai(user_id, text)
        send(chat_id, reply, user_id)

        return "ok"

    if "callback_query" in data:

        cq = data["callback_query"]

        chat_id = cq["message"]["chat"]["id"]
        user_id = str(chat_id)
        data_cb = cq["data"]

        handle_cb(data_cb, chat_id, user_id)

    return "ok"

# =====================
# HOME
# =====================
@app.route("/")
def home():
    return "🤖 NeoHelper v20 PRO STABLE ONLINE"

# =====================
# RUN
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)