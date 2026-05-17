import os
import requests
from flask import Flask, request

app = Flask(__name__)

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# =========================
# MEMORY
# =========================
memory = {}

# =========================
# SEND TELEGRAM MESSAGE
# =========================
def send_message(chat_id, text):

    try:

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

        r = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text
            },
            timeout=10
        )

        print("TELEGRAM RESPONSE:", r.text)

    except Exception as e:

        print("SEND ERROR:", e)


# =========================
# GEMINI AI
# =========================
def ask_ai(user_id, text):

    if not GEMINI_API_KEY:
        return "❌ GEMINI_API_KEY not found"

    history = memory.get(user_id, [])

    history.append({
        "role": "user",
        "parts": [
            {
                "text": text
            }
        ]
    })

    # ограничение памяти
    history = history[-10:]

    # ✅ ПРАВИЛЬНЫЙ GEMINI URL
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    )

    data = {
        "contents": history
    }

    try:

        r = requests.post(
            url,
            json=data,
            timeout=20
        )

        print("GEMINI STATUS:", r.status_code)
        print("GEMINI RAW:", r.text)

        if r.status_code != 200:
            return f"⚠️ Gemini HTTP Error {r.status_code}"

        result = r.json()

        if "error" in result:
            return f"⚠️ Gemini Error: {result['error']}"

        candidates = result.get("candidates", [])

        if not candidates:
            return "⚠️ Empty AI response"

        answer = (
            candidates[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "⚠️ No text")
        )

        print("AI ANSWER:", answer)

        # память
        history.append({
            "role": "model",
            "parts": [
                {
                    "text": answer
                }
            ]
        })

        memory[user_id] = history

        return answer

    except Exception as e:

        print("AI ERROR:", e)

        return f"⚠️ AI ERROR: {e}"


# =========================
# COMMANDS
# =========================
def handle_commands(text, user_id):

    if text == "/start":

        return (
            "🤖 NeoHelper v7\n\n"
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

        memory[user_id] = []

        return "🧠 Память очищена"

    return None


# =========================
# WEBHOOK
# =========================
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


# =========================
# HOME
# =========================
@app.route("/")
def home():

    return "🤖 NeoHelper v7 ONLINE"


# =========================
# RUN
# =========================
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )