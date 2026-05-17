import os
import time
import sqlite3
import requests
from flask import Flask, request

app = Flask(__name__)

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# =========================
# DB
# =========================
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
    last_time REAL DEFAULT 0
)
""")

conn.commit()

# =========================
# SETTINGS
# =========================
DAILY_LIMIT = 30
COOLDOWN = 4

# =========================
# MENU (ALWAYS SHOWN)
# =========================
def menu():
    return {
        "inline_keyboard": [
            [
                {"text": "🤖 AI", "callback_data": "ai"},
                {"text": "👤 Профиль", "callback_data": "profile"}
            ],
            [
                {"text": "🧠 Очистить", "callback_data": "clear"},
                {"text": "ℹ️ Инфо", "callback_data": "info"}
            ]
        ]
    }

# =========================
# TELEGRAM SEND
# =========================
def send(chat_id, text):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "reply_markup": menu()
        }
    )

# =========================
# USER SYSTEM
# =========================
def get_user(user_id):
    cursor.execute(
        "SELECT messages, last_time FROM users WHERE user_id=?",
        (user_id,)
    )
    return cursor.fetchone()

def register(user_id):
    if not get_user(user_id):
        cursor.execute(
            "INSERT INTO users VALUES (?, ?, ?)",
            (user_id, 0, 0)
        )
        conn.commit()

# =========================
# LIMIT SYSTEM
# =========================
def check_limits(user_id):

    user = get_user(user_id)

    if not user:
        register(user_id)
        user = (0, 0)

    messages, last_time = user
    now = time.time()

    if now - last_time < COOLDOWN:
        return "⏳ Слишком быстро"

    if messages >= DAILY_LIMIT:
        return "🚫 Лимит 30 сообщений/день"

    cursor.execute("""
        UPDATE users
        SET messages = messages + 1,
            last_time = ?
        WHERE user_id=?
    """, (now, user_id))

    conn.commit()

    return None

# =========================
# AI
# =========================
def ask_ai(user_id, text):

    cursor.execute(
        "INSERT INTO memory VALUES (?, ?, ?)",
        (user_id, "user", text)
    )
    conn.commit()

    cursor.execute("""
        SELECT role, content FROM memory
        WHERE user_id=?
        ORDER BY rowid DESC
        LIMIT 10
    """, (user_id,))

    rows = cursor.fetchall()[::-1]

    messages = [
        {
            "role": "system",
            "content": "Ты NeoHelper — умный, краткий и дружелюбный AI ассистент."
        }
    ]

    for r in rows:
        messages.append({"role": r[0], "content": r[1]})

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "openai/gpt-3.5-turbo",
        "messages": messages
    }

    try:
        r = requests.post(url, headers=headers, json=data)

        if r.status_code != 200:
            return "⚠️ AI error"

        answer = r.json()["choices"][0]["message"]["content"]

        cursor.execute(
            "INSERT INTO memory VALUES (?, ?, ?)",
            (user_id, "assistant", answer)
        )
        conn.commit()

        return answer

    except Exception as e:
        return f"⚠️ AI ERROR: {e}"

# =========================
# CALLBACKS
# =========================
def handle_callback(action, chat_id, user_id):

    if action == "profile":

        cursor.execute(
            "SELECT messages FROM users WHERE user_id=?",
            (user_id,)
        )

        res = cursor.fetchone()
        count = res[0] if res else 0

        send(chat_id,
            f"👤 Профиль\n\n"
            f"🆔 ID: {user_id}\n"
            f"💬 Запросов: {count}\n"
            f"🚀 Лимит: {DAILY_LIMIT}/день"
        )

    elif action == "info":

        send(chat_id,
            "ℹ️ NeoHelper v15\n\n"
            "🤖 AI ассистент\n"
            "🧠 Память включена\n"
            "🚫 30 запросов/день\n"
            "⏳ Антиспам активен"
        )

    elif action == "clear":

        cursor.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
        conn.commit()

        send(chat_id, "🧠 Память очищена")

    elif action == "ai":

        send(chat_id, "🤖 Напиши сообщение — я отвечу через AI")

# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json()

    if not data:
        return "ok", 200

    # MESSAGE
    if "message" in data:

        msg = data["message"]

        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        user_id = str(chat_id)

        register(user_id)

        limit = check_limits(user_id)

        if limit:
            send(chat_id, limit)
            return "ok", 200

        # AI or system commands
        if text == "/clear":
            cursor.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
            conn.commit()
            send(chat_id, "🧠 Память очищена")
            return "ok", 200

        reply = ask_ai(user_id, text)
        send(chat_id, reply)

        return "ok", 200

    # BUTTONS
    if "callback_query" in data:

        cq = data["callback_query"]

        chat_id = cq["message"]["chat"]["id"]
        user_id = str(chat_id)
        action = cq["data"]

        handle_callback(action, chat_id, user_id)

        return "ok", 200

    return "ok", 200

# =========================
# HOME
# =========================
@app.route("/")
def home():
    return "🤖 NeoHelper v15 MENU MODE ONLINE"

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)