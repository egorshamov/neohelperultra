import os
import time
import sqlite3
import requests
from flask import Flask, request

app = Flask(__name__)

# =====================
# ENV
# =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

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
    mode TEXT DEFAULT 'normal'
)
""")

conn.commit()

# =====================
# SETTINGS
# =====================
DAILY_LIMIT = 30
COOLDOWN = 4

# =====================
# UI BUTTONS
# =====================
def keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "👤 Профиль", "callback_data": "profile"},
                {"text": "ℹ️ Инфо", "callback_data": "info"}
            ],
            [
                {"text": "🆕 Новый чат", "callback_data": "newchat"},
                {"text": "⚙️ Режим", "callback_data": "mode"}
            ]
        ]
    }

# =====================
# TELEGRAM SEND
# =====================
def send(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

        requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "reply_markup": keyboard()
        })
    except:
        pass

# =====================
# USER SYSTEM
# =====================
def get_user(user_id):
    cursor.execute(
        "SELECT messages, last_time, mode FROM users WHERE user_id=?",
        (user_id,)
    )
    return cursor.fetchone()

def register(user_id):
    if not get_user(user_id):
        cursor.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            (user_id, 0, 0, "normal")
        )
        conn.commit()

# =====================
# LIMIT + ANTI SPAM
# =====================
def check_limits(user_id):

    user = get_user(user_id)

    if not user:
        register(user_id)
        user = (0, 0, "normal")

    messages, last_time, mode = user
    now = time.time()

    if now - last_time < COOLDOWN:
        return "⏳ Слишком быстро"

    if messages >= DAILY_LIMIT:
        return "🚫 Лимит 30/день исчерпан"

    cursor.execute("""
        UPDATE users
        SET messages = messages + 1,
            last_time = ?
        WHERE user_id=?
    """, (now, user_id))

    conn.commit()

    return None

# =====================
# AI ENGINE
# =====================
def ask_ai(user_id, text):

    user = get_user(user_id)
    mode = user[2] if user else "normal"

    # save user msg
    cursor.execute(
        "INSERT INTO memory VALUES (?, ?, ?)",
        (user_id, "user", text)
    )
    conn.commit()

    cursor.execute("""
        SELECT role, content FROM memory
        WHERE user_id=?
        ORDER BY rowid DESC
        LIMIT 12
    """, (user_id,))

    rows = cursor.fetchall()[::-1]

    # SYSTEM PROMPT (mode based)
    if mode == "fast":
        style = "Отвечай очень коротко."
    elif mode == "smart":
        style = "Отвечай подробно и умно."
    else:
        style = "Отвечай нормально, понятно и дружелюбно."

    messages = [
        {
            "role": "system",
            "content": f"Ты NeoHelper AI. {style}"
        }
    ]

    for r in rows:
        messages.append({"role": r[0], "content": r[1]})

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
            timeout=25
        )

        if r.status_code != 200:
            return "⚠️ AI временно недоступен"

        answer = r.json()["choices"][0]["message"]["content"]

        cursor.execute(
            "INSERT INTO memory VALUES (?, ?, ?)",
            (user_id, "assistant", answer)
        )
        conn.commit()

        return f"🤖 NeoHelper\n\n{answer}"

    except:
        return "⚠️ Ошибка AI"

# =====================
# CALLBACKS
# =====================
def handle_cb(data, chat_id, user_id):

    if data == "profile":
        u = get_user(user_id)
        send(chat_id, f"👤 ID: {user_id}\n💬 Msg: {u[0]}")

    elif data == "info":
        send(chat_id,
            "ℹ️ NeoHelper v16\n"
            "🤖 AI бот\n"
            "🧠 память\n"
            "⚡ режимы\n"
            "🚫 лимиты"
        )

    elif data == "newchat":
        cursor.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
        conn.commit()
        send(chat_id, "🆕 Новый чат создан")

    elif data == "mode":
        u = get_user(user_id)
        new_mode = "smart" if u[2] == "normal" else "fast" if u[2] == "smart" else "normal"

        cursor.execute(
            "UPDATE users SET mode=? WHERE user_id=?",
            (new_mode, user_id)
        )
        conn.commit()

        send(chat_id, f"⚙️ Режим: {new_mode}")

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

        limit = check_limits(user_id)

        if limit:
            send(chat_id, limit)
            return "ok"

        if text == "/clear":
            cursor.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
            conn.commit()
            send(chat_id, "🧠 очищено")
            return "ok"

        reply = ask_ai(user_id, text)
        send(chat_id, reply)

        return "ok"

    if "callback_query" in data:
        cq = data["callback_query"]

        chat_id = cq["message"]["chat"]["id"]
        user_id = str(chat_id)
        action = cq["data"]

        handle_cb(action, chat_id, user_id)

    return "ok"

# =====================
# HOME
# =====================
@app.route("/")
def home():
    return "🤖 NeoHelper v16 STABLE ONLINE"

# =====================
# RUN
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)