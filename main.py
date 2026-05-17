import os
import sqlite3
import requests

from flask import Flask, request

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

app = Flask(__name__)

# ====================================
# ENV VARIABLES
# ====================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# ====================================
# DATABASE
# ====================================
conn = sqlite3.connect(
    "neohelper.db",
    check_same_thread=False
)

cursor = conn.cursor()

# MEMORY TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    user_id TEXT,
    role TEXT,
    content TEXT
)
""")

# USERS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT,
    messages INTEGER
)
""")

conn.commit()

# ====================================
# MAIN MENU
# ====================================
def main_menu():

    keyboard = [

        [
            InlineKeyboardButton(
                "💬 Новый чат",
                callback_data="new_chat"
            )
        ],

        [
            InlineKeyboardButton(
                "🧠 Очистить память",
                callback_data="clear_memory"
            )
        ],

        [
            InlineKeyboardButton(
                "👤 Профиль",
                callback_data="profile"
            ),

            InlineKeyboardButton(
                "ℹ️ Помощь",
                callback_data="help"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# ====================================
# REGISTER USER
# ====================================
def register_user(user_id):

    cursor.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user_id,)
    )

    user = cursor.fetchone()

    if not user:

        cursor.execute(
            "INSERT INTO users VALUES (?, ?)",
            (user_id, 0)
        )

        conn.commit()


# ====================================
# SEND MESSAGE
# ====================================
def send_message(chat_id, text):

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendMessage"
        )

        response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "reply_markup": main_menu().to_dict()
            },
            timeout=10
        )

        print("TELEGRAM:", response.text)

    except Exception as e:

        print("SEND ERROR:", e)


# ====================================
# TYPING EFFECT
# ====================================
def send_typing(chat_id):

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendChatAction"
        )

        requests.post(
            url,
            json={
                "chat_id": chat_id,
                "action": "typing"
            },
            timeout=5
        )

    except:
        pass


# ====================================
# AI FUNCTION
# ====================================
def ask_ai(user_id, text):

    if not OPENROUTER_API_KEY:
        return "❌ OPENROUTER_API_KEY not found"

    register_user(user_id)

    cursor.execute(
        """
        UPDATE users
        SET messages = messages + 1
        WHERE user_id=?
        """,
        (user_id,)
    )

    conn.commit()

    # SAVE USER MESSAGE
    cursor.execute(
        "INSERT INTO memory VALUES (?, ?, ?)",
        (user_id, "user", text)
    )

    conn.commit()

    # LOAD HISTORY
    cursor.execute(
        """
        SELECT role, content
        FROM memory
        WHERE user_id=?
        ORDER BY rowid DESC
        LIMIT 10
        """,
        (user_id,)
    )

    rows = cursor.fetchall()

    rows.reverse()

    messages = []

    # SYSTEM PROMPT
    messages.append({
        "role": "system",
        "content": (
            "Ты NeoHelper — умный AI помощник. "
            "Отвечай дружелюбно, красиво и полезно."
        )
    })

    # MEMORY
    for role, content in rows:

        messages.append({
            "role": role,
            "content": content
        })

    headers = {
        "Authorization": (
            f"Bearer {OPENROUTER_API_KEY}"
        ),
        "Content-Type": "application/json"
    }

    data = {
        "model": "openai/gpt-3.5-turbo",
        "messages": messages
    }

    try:

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )

        print("AI STATUS:", response.status_code)

        if response.status_code != 200:

            print(response.text)

            return (
                f"⚠️ AI Error {response.status_code}"
            )

        result = response.json()

        answer = (
            result["choices"][0]
            ["message"]["content"]
        )

        # SAVE AI RESPONSE
        cursor.execute(
            "INSERT INTO memory VALUES (?, ?, ?)",
            (user_id, "assistant", answer)
        )

        conn.commit()

        return f"🤖 NeoHelper\n\n{answer}"

    except Exception as e:

        print("AI ERROR:", e)

        return f"⚠️ AI ERROR: {e}"


# ====================================
# COMMANDS
# ====================================
def handle_commands(text, user_id):

    if text == "/start":

        return (
            "┏━━━━━━━━━━━━━┓\n"
            "   🤖 NeoHelper AI\n"
            "┗━━━━━━━━━━━━━┛\n\n"
            "🧠 Умный Telegram AI\n"
            "⚡ Powered by OpenRouter\n"
            "🌐 Render Cloud Online\n\n"
            "Выберите действие 👇"
        )

    if text == "/help":

        return (
            "ℹ️ HELP\n\n"
            "/start - запуск\n"
            "/help - помощь\n"
            "/clear - очистить память\n"
            "/profile - профиль"
        )

    if text == "/clear":

        cursor.execute(
            "DELETE FROM memory WHERE user_id=?",
            (user_id,)
        )

        conn.commit()

        return "🧠 Память очищена"

    if text == "/profile":

        register_user(user_id)

        cursor.execute(
            "SELECT messages FROM users WHERE user_id=?",
            (user_id,)
        )

        result = cursor.fetchone()

        messages = result[0]

        return (
            "╔══ 👤 PROFILE ══╗\n\n"
            f"🆔 ID: {user_id}\n"
            f"💬 Messages: {messages}\n"
            "⭐ Status: User\n\n"
            "╚═══════════════╝"
        )

    return None


# ====================================
# WEBHOOK
# ====================================
@app.route("/webhook", methods=["POST"])
def webhook():

    try:

        data = request.get_json()

        print("WEBHOOK:", data)

        if not data:
            return "ok", 200

        if "message" not in data:
            return "ok", 200

        message = data["message"]

        chat_id = message["chat"]["id"]

        text = message.get("text", "")

        print("USER:", text)

        user_id = str(chat_id)

        # TYPING EFFECT
        send_typing(chat_id)

        # COMMANDS
        cmd = handle_commands(
            text,
            user_id
        )

        if cmd:

            send_message(chat_id, cmd)

            return "ok", 200

        # AI RESPONSE
        reply = ask_ai(user_id, text)

        send_message(chat_id, reply)

        return "ok", 200

    except Exception as e:

        print("WEBHOOK ERROR:", e)

        return "ok", 200


# ====================================
# HOME PAGE
# ====================================
@app.route("/")
def home():

    return "🤖 NeoHelper v11 ONLINE"


# ====================================
# RUN SERVER
# ====================================
if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )