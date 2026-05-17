import os
import time
import requests
from flask import Flask, request

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# 🧠 лёгкая память (RAM)
memory = {}

# =======================
# SAFE LOG (без краша)
# =======================
def log(e):
    print("❌ ERROR:", e)


# =======================
# GEMINI AI (ULTRA SAFE)
# =======================
def ask_ai(user_id, text):
    if not GEMINI_API_KEY:
        return "❌ AI выключен (нет ключа)"

    history = memory.get(user_id, [])

    history.append({
        "role": "user",
        "parts": [{"text": text}]
    })

    history = history[-8:]  # защита памяти

    url = (
        "https://generativelanguage.googleapis.com/v1/"
        f"models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    )

    payload = {"contents": history}

    # 🔁 retry система (2 попытки)
    for _ in range(2):
        try:
            r = requests.post(url, json=payload, timeout=12)

            if r.status_code != 200:
                time.sleep(1)
                continue

            data = r.json()

            if "error" in data:
                time.sleep(1)
                continue

            answer = data["candidates"][0]["content"]["parts"][0]["text"]

            history.append({
                "role": "model",
                "parts": [{"text": answer}]
            })

            memory[user_id] = history

            return answer

        except Exception as e:
            log(e)
            time.sleep(1)

    # fallback (если Gemini умер)
    return fallback(text)


# =======================
# FALLBACK (ВАЖНО)
# =======================
def fallback(text):
    t = text.lower()

    if "привет" in t:
        return "Привет 👋 Я NeoHelper v6 (fallback режим)"
    if "как дела" in t:
        return "Я работаю, но AI сейчас недоступен ⚙️"
    if "что ты" in t:
        return "Я Telegram бот с Gemini AI 🤖"

    return "⚠️ AI временно недоступен, попробуй позже"


# =======================
# TELEGRAM SEND
# =======================
def send(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": text
        }, timeout=10)
    except:
        pass


# =======================
# COMMANDS
# =======================
def cmd(text, user_id):
    if text == "/start":
        return "🤖 NeoHelper v6 запущен\nНапиши сообщение"

    if text == "/help":
        return "/start\n/clear"

    if text == "/clear":
        memory[user_id] = []
        return "🧠 память очищена"

    return None


# =======================
# WEBHOOK CORE
# =======================
@app.route("/webhook", methods=["POST"])
def telegram():
    try:
        data = request.get_json()

        if not data or "message" not in data:
            return "ok"

        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        user_id = str(chat_id)

        c = cmd(text, user_id)
        if c:
            send(chat_id, c)
            return "ok"

        reply = ask_ai(user_id, text)
        send(chat_id, reply)

        return "ok"

    except Exception as e:
        log(e)
        return "ok"


# =======================
# SET WEBHOOK (AUTO FIX)
# =======================
@app.route("/set")
def set_webhook():
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"

        r = requests.get(url, params={
            "url": f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{BOT_TOKEN}"
        })

        return r.text
    except Exception as e:
        return str(e)


# =======================
# HOME
# =======================
@app.route("/")
def home():
    return "🤖 NeoHelper v6 ONLINE"


# =======================
# RUN (RENDER PORT)
# =======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)