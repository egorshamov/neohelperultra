import os
import requests
from flask import Flask, request

app = Flask(__name__)

# ====================================
# ENV VARIABLES
# ====================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# ====================================
# MEMORY
# ====================================
memory = {}

# ====================================
# SEND MESSAGE TO TELEGRAM
# ====================================
def send_message(chat_id, text):

    try:

        telegram_url = (
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        )

        response = requests.post(
            telegram_url,
            json={
                "chat_id": chat_id,
                "text": text
            },
            timeout=10
        )

        print("TELEGRAM RESPONSE:", response.text)

    except Exception as e:

        print("SEND ERROR:", e)


# ====================================
# AI FUNCTION (OPENROUTER)
# ====================================
def ask_ai(user_id, text):

    if not OPENROUTER_API_KEY:
        return "❌ OPENROUTER_API_KEY not found"

    history = memory.get(user_id, [])

    history.append({
        "role": "user",
        "content": text
    })

    # ограничение памяти
    history = history[-10:]

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "openai/gpt-3.5-turbo",
        "messages": history
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=30
        )

        print("AI STATUS:", response.status_code)
        print("AI RAW:", response.text)

        if response.status_code != 200:
            return f"⚠️ AI HTTP Error {response.status_code}"

        result = response.json()

        answer = (
            result["choices"][0]
            ["message"]["content"]
        )

        print("AI ANSWER:", answer)

        # сохраняем память
        history.append({
            "role": "assistant",
            "content": answer
        })

        memory[user_id] = history

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
            "🤖 NeoHelper v8\n\n"
            "AI бот успешно работает.\n"
            "Напиши любое сообщение."
        )

    if text == "/help":

        return (
            "/start - запуск\n"
            "/help - помощь\n"
            "/clear - очистить память"
        )

    if text == "/clear":

        memory[user_id] = []

        return "🧠 Память очищена"

    return None


# ====================================
# WEBHOOK
# ====================================
@app.route("/webhook", methods=["POST"])
def webhook():

    try:

        data = request.get_json()

        print("WEBHOOK DATA:", data)

        if not data:
            return "ok", 200

        if "message" not in data:
            return "ok", 200

        message = data["message"]

        chat_id = message["chat"]["id"]

        text = message.get("text", "")

        print("USER MESSAGE:", text)

        user_id = str(chat_id)

        # команды
        cmd = handle_commands(text, user_id)

        if cmd:

            send_message(chat_id, cmd)

            return "ok", 200

        # AI ответ
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

    return "🤖 NeoHelper v8 ONLINE"


# ====================================
# RUN SERVER
# ====================================
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )