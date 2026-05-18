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

# ================= USER INIT =================
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
        system = "You are PRO AI. deep structured answers, high quality reasoning."

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

# ================= SEND =================
def send(chat_id, text, kb=None):
    data = {"chat_id": chat_id, "text": text}
    if kb:
        data["reply_markup"] = kb
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=data)

# ================= KEYBOARDS =================
def keyboard(chat_id):
    kb = [
        ["💬 Чат", "🧠 PRO AI"],
        ["📊 Лимиты"]
    ]
    if is_admin(chat_id):
        kb.append(["👑 Админ"])
    return {"keyboard": kb, "resize_keyboard": True}

def admin_keyboard():
    return {
        "keyboard": [
            ["📊 Статистика"],
            ["💎 Выдать PRO"],
            ["💎 Выдать LITE"],
            ["💎 Выдать ULTRA"],
            ["🔙 Выйти"]
        ],
        "resize_keyboard": True
    }

# ================= LIMIT INFO =================
def get_stats():
    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE plan!='basic'")
    pro = cursor.fetchone()[0]

    return f"📊 USERS: {users}\n💎 PRO USERS: {pro}"

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

    # ================= ADMIN ENTRY =================
    if text == "👑 Админ" and is_admin(chat_id):
        admin_state[chat_id] = "menu"
        send(chat_id, "👑 админ панель", admin_keyboard())
        return "ok"

    # ================= ADMIN MENU =================
    if chat_id in admin_state:

        if text == "🔙 Выйти":
            admin_state.pop(chat_id)
            send(chat_id, "🏠 меню", keyboard(chat_id))
            return "ok"

        if text == "📊 Статистика":
            send(chat_id, get_stats(), admin_keyboard())
            return "ok"

        if text in ["💎 Выдать PRO", "💎 Выдать LITE", "💎 Выдать ULTRA"]:
            admin_state[chat_id] = text
            send(chat_id, "👤 введи ID пользователя")
            return "ok"

        if admin_state[chat_id] in ["💎 Выдать PRO", "💎 Выдать LITE", "💎 Выдать ULTRA"]:
            plan = admin_state[chat_id].split()[-1].lower()

            cursor.execute("""
                UPDATE users SET plan=? WHERE user_id=?
            """, (plan, text))
            conn.commit()

            send(chat_id, f"💎 выдано: {plan}", admin_keyboard())
            admin_state.pop(chat_id)
            return "ok"

    # ================= PRO AI =================
    if text == "🧠 PRO AI":
        if get_plan(chat_id) == "basic":
            send(chat_id, "🚫 только PRO")
            return "ok"

        cursor.execute("UPDATE users SET chat_mode='pro_ai' WHERE user_id=?", (chat_id,))
        conn.commit()

        send(chat_id, "🧠 PRO AI включён", keyboard(chat_id))
        return "ok"

    # ================= CHAT =================
    if not check_message_limit(chat_id):
        send(chat_id, "🚫 лимит сообщений")
        return "ok"

    reply = ask_ai(chat_id, text)
    send(chat_id, reply, keyboard(chat_id))
    return "ok"

@app.route("/")
def home():
    return "v55 ADMIN FULL SYSTEM READY"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))