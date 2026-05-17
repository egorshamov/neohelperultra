import os
import sqlite3
import requests

from flask import Flask, request

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

cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    user_id TEXT,
    role TEXT,
    content TEXT
)
""")

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
                "text": text
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

    # сохраняем сообщение пользователя
    cursor.execute(
        "INSERT INTO memory VALUES (?, ?, ?)",
        (user_id, "user", text)
    )

    conn.commit()

    # загружаем историю
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
            "Ты NeoHelper — умный Telegram AI помощник. "
            "Отвечай кратко, дружелюбно и полезно."
        )
    })

    # память
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

        print("AI ANSWER:", answer)

        # сохраняем ответ AI
        cursor.execute(
            "INSERT INTO memory VALUES (?, ?, ?)",
            (user_id, "assistant", answer)
        )

        conn.commit()

        return answer

    except Exception as e:

        print("AI ERROR:", e)

        return f"⚠️ AI ERROR: {e}"


# ====================================
# COMMANDS
# ====================================
def handle_commands(text, user_id):

    if text == "/start":

        return (
            "🤖 NeoHelper v9\n\n"
            "AI бот работает.\n"
            "Напиши сообщение."
        )

    if text == "/help":

        return (
            "/start - запуск\n"
            "/help - помощь\n"
            "/clear - очистить память"
        )

    if text == "/clear":

        cursor.execute(
            "DELETE FROM memory WHERE user_id=?",
            (user_id,)
        )

        conn.commit()

        return "🧠 Память очищена"

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

        # typing effect
        send_typing(chat_id)

        # commands
        cmd = handle_commands(
            text,
            user_id
        )

        if cmd:

            send_message(chat_id, cmd)

            return "ok", 200

        # AI answer
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

    return "🤖 NeoHelper v9 ONLINE"


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