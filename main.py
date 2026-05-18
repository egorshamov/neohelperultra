import os
import time
import sqlite3
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ADMIN_ID = str(os.getenv("ADMIN_ID", ""))

# ================= DB =================
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
    image_mode INTEGER DEFAULT 0,
    image_style TEXT DEFAULT 'realistic',
    subscription_end REAL DEFAULT 0
)
""")
conn.commit()

# ================= STATE =================
user_state = {}
admin_state = {}

# ================= PLANS =================
PLANS = {
    "basic": {"messages": 40, "images": 3},
    "lite": {"messages": 50, "images": 5},
    "pro": {"messages": 200, "images": 15},
    "ultra": {"messages": 999999, "images": 999999}
}

# ================= AUTO USER =================
def ensure_user(chat_id):
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (chat_id,))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (user_id, messages, images, last_reset, plan, chat_mode, image_mode, image_style)
            VALUES (?, 0, 0, ?, 'basic', 'smart', 0, 'realistic')
        """, (chat_id, time.time()))
        conn.commit()

# ================= RESET =================
def reset_limits_if_needed(chat_id):
    cursor.execute("SELECT last_reset FROM users WHERE user_id=?", (chat_id,))
    row = cursor.fetchone()
    if row and time.time() - row[0] > 86400:
        cursor.execute("""
            UPDATE users SET messages=0, images=0, last_reset=? WHERE user_id=?
        """, (time.time(), chat_id))
        conn.commit()

# ================= SPAM =================
def check_spam(chat_id, limit=2):
    now = time.time()
    if chat_id in user_state and now - user_state[chat_id] < limit:
        return False
    user_state[chat_id] = now
    return True

# ================= PLAN =================
def get_plan(chat_id):
    cursor.execute("SELECT plan FROM users WHERE user_id=?", (chat_id,))
    row = cursor.fetchone()
    return row[0] if row else "basic"

def is_admin(chat_id):
    return str(chat_id) == str(ADMIN_ID)

# ================= LIMITS =================
def check_message_limit(chat_id):
    plan = get_plan(chat_id)
    limit = PLANS[plan]["messages"]

    cursor.execute("SELECT messages FROM users WHERE user_id=?", (chat_id,))
    used = cursor.fetchone()[0]

    if used >= limit:
        return False

    cursor.execute("UPDATE users SET messages = messages + 1 WHERE user_id=?", (chat_id,))
    conn.commit()
    return True

def check_image_limit(chat_id):
    plan = get_plan(chat_id)
    limit = PLANS[plan]["images"]

    cursor.execute("SELECT images FROM users WHERE user_id=?", (chat_id,))
    used = cursor.fetchone()[0]

    if used >= limit:
        return False

    cursor.execute("UPDATE users SET images = images + 1 WHERE user_id=?", (chat_id,))
    conn.commit()
    return True

# ================= AI =================
def ask_ai(uid, text):

    cursor.execute("SELECT chat_mode FROM users WHERE user_id=?", (uid,))
    mode = cursor.fetchone()[0]

    system = "You are a Telegram assistant."

    if mode == "fast":
        system += " short answers"
    elif mode == "smart":
        system += " normal answers"
    elif mode == "deep":
        system += " detailed answers"
    elif mode == "pro_ai":
        system = "You are PRO AI. deep structured high quality answers."

    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
        json={
            "model": "openai/gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text}
            ],
            "temperature": 0.7,
            "max_tokens": 800
        }
    )

    return r.json()["choices"][0]["message"]["content"]

# ================= IMAGE =================
IMAGE_STYLES = {
    "anime": "anime style, detailed",
    "realistic": "ultra realistic, cinematic lighting",
    "3d": "3d render, octane render"
}

def clean_prompt(text):
    bad = ["картинка","нарисуй","сделай","создай","хочу","image","draw"]
    for w in bad:
        text = text.replace(w, "")
    return text.strip()

def enhance_prompt(text, style):
    return f"{text}, {IMAGE_STYLES.get(style)}"

def make_img(prompt):
    return "https://image.pollinations.ai/prompt/" + prompt.replace(" ", "%20")

# ================= SEND =================
def send(chat_id, text, kb=None):
    data = {"chat_id": chat_id, "text": text}
    if kb:
        data["reply_markup"] = kb
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=data)

def send_image(chat_id, url):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                  json={"chat_id": chat_id, "photo": url})

# ================= KEYBOARDS =================
def keyboard(chat_id):
    kb = [
        ["💬 Чат", "🧠 PRO AI"],
        ["🖼 Картинка", "💳 PRO ⭐"],
        ["📊 Лимиты"]
    ]
    if is_admin(chat_id):
        kb.append(["👑 Админ"])

    return {"keyboard": kb, "resize_keyboard": True}

def chat_keyboard():
    return {
        "keyboard": [
            ["⚡ Быстро", "🧠 Умно", "📚 Подробно"],
            ["🔙 Назад"]
        ],
        "resize_keyboard": True
    }

def image_keyboard():
    return {
        "keyboard": [
            ["🎨 anime", "📸 realistic", "🧊 3d"],
            ["🔙 Назад"]
        ],
        "resize_keyboard": True
    }

def admin_keyboard():
    return {
        "keyboard": [
            ["📊 Статистика"],
            ["💎 Выдать PRO (1)"],
            ["💎 Выдать PRO (2)"],
            ["💎 Выдать ULTRA (3)"],
            ["🔙 Выйти"]
        ],
        "resize_keyboard": True
    }

# ================= ROUTER =================
@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.json
    msg = data.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id"))
    text = msg.get("text", "")

    ensure_user(chat_id)
    reset_limits_if_needed(chat_id)

    if not check_spam(chat_id):
        send(chat_id, "⏳ слишком быстро")
        return "ok"

    # ================= PRO MENU =================
    if text == "💳 PRO ⭐":
        send(chat_id,
            "💎 PRO тарифы:",
            {
                "keyboard": [
                    ["🟢 Lite", "🔵 Pro", "🟣 Ultra"],
                    ["🔙 Назад"]
                ],
                "resize_keyboard": True
            }
        )
        return "ok"

    if text in ["🟢 Lite", "🔵 Pro", "🟣 Ultra"]:
        plan_map = {
            "🟢 Lite": "lite",
            "🔵 Pro": "pro",
            "🟣 Ultra": "ultra"
        }

        plan = plan_map[text]

        cursor.execute("UPDATE users SET plan=? WHERE user_id=?", (plan, chat_id))
        conn.commit()

        send(chat_id, f"💎 план активирован: {plan}", keyboard(chat_id))
        return "ok"

    # ================= BACK =================
    if text == "🔙 Назад":
        send(chat_id, "🏠 меню", keyboard(chat_id))
        return "ok"

    # ================= IMAGE =================
    if text == "🖼 Картинка":
        cursor.execute("UPDATE users SET image_mode=1 WHERE user_id=?", (chat_id,))
        conn.commit()
        send(chat_id, "🎨 стиль:", image_keyboard())
        return "ok"

    if text in ["🎨 anime","📸 realistic","🧊 3d"]:
        style = {"🎨 anime":"anime","📸 realistic":"realistic","🧊 3d":"3d"}[text]
        cursor.execute("UPDATE users SET image_style=? WHERE user_id=?", (style, chat_id))
        conn.commit()
        send(chat_id, f"🎯 {style}", image_keyboard())
        return "ok"

    if text == "🔙 Назад":
        cursor.execute("UPDATE users SET image_mode=0 WHERE user_id=?", (chat_id,))
        conn.commit()
        send(chat_id, "🏠 меню", keyboard(chat_id))
        return "ok"

    # ================= LIMITS =================
    if not check_message_limit(chat_id):
        send(chat_id, "🚫 лимит сообщений")
        return "ok"

    # ================= AI =================
    reply = ask_ai(chat_id, text)
    send(chat_id, reply, keyboard(chat_id))
    return "ok"

@app.route("/")
def home():
    return "v57 FULL SYSTEM READY"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))