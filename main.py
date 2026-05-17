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

# =====================
# DB
# =====================
conn = sqlite3.connect("neohelper.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    messages INTEGER DEFAULT 0,
    images INTEGER DEFAULT 0,
    last_time REAL DEFAULT 0,
    plan TEXT DEFAULT 'free'
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    user_id TEXT,
    role TEXT,
    content TEXT
)
""")

conn.commit()

# =====================
# LIMITS
# =====================
def limits(plan):
    if plan == "pro":
        return 9999, 9999
    return 40, 3

# =====================
# USERS
# =====================
def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def register(user_id):
    if not get_user(user_id):
        cursor.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
            (user_id, 0, 0, 0, "free")
        )
        conn.commit()

def set_plan(user_id, plan):
    cursor.execute("UPDATE users SET plan=? WHERE user_id=?", (plan, user_id))
    conn.commit()

# =====================
# MEMORY SYSTEM
# =====================
def save_memory(user_id, role, content):
    cursor.execute(
        "INSERT INTO memory VALUES (?, ?, ?)",
        (user_id, role, content)
    )
    conn.commit()

def load_memory(user_id, limit=6):
    cursor.execute(
        "SELECT role, content FROM memory WHERE user_id=? ORDER BY rowid DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()

    return list(reversed([
        {"role": r[0], "content": r[1]} for r in rows
    ]))

# =====================
# SAFE SEND
# =====================
def send(chat_id, text, keyboard=None):
    try:
        data = {"chat_id": chat_id, "text": text}
        if keyboard:
            data["reply_markup"] = keyboard

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=data,
            timeout=8
        )
    except:
        pass

def send_image(chat_id, url):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            json={"chat_id": chat_id, "photo": url},
            timeout=8
        )
    except:
        pass

# =====================
# UI
# =====================
def keyboard():
    return {
        "keyboard": [
            ["💬 Чат", "🖼 Картинка"],
            ["💳 PRO", "📊 Лимиты"],
            ["👑 Админ"]
        ],
        "resize_keyboard": True
    }

def admin_keyboard():
    return {
        "keyboard": [
            ["📊 Статистика"],
            ["🔙 Назад"]
        ],
        "resize_keyboard": True
    }

# =====================
# IMAGE
# =====================
def make_image(prompt):
    prompt = prompt.replace(" ", "%20")
    return f"https://image.pollinations.ai/prompt/{prompt}, cinematic, ultra realistic"

def is_image(text):
    return any(x in text.lower() for x in ["картинка", "нарисуй", "image"])

# =====================
# LIVE MONITORING
# =====================
def get_online_users():
    now = time.time()
    cursor.execute("SELECT last_time FROM users")
    rows = cursor.fetchall()

    online = 0
    for r in rows:
        if now - r[0] < 120:
            online += 1

    return online

# =====================
# AI WITH MEMORY
# =====================
def ask_ai(user_id, text):

    save_memory(user_id, "user", text)

    history = load_memory(user_id)

    messages = [
        {
            "role": "system",
            "content": "Ты умный ассистент. НЕ здоровайся каждый раз. Продолжай диалог естественно."
        }
    ] + history

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": messages,
                "temperature": 0.8,
                "max_tokens": 300
            },
            timeout=12
        )

        answer = r.json()["choices"][0]["message"]["content"]

        save_memory(user_id, "assistant", answer)

        return answer

    except:
        return "AI error"

# =====================
# LIMIT CHECK
# =====================
def check_limits(user):
    now = time.time()

    messages, images, last_time, plan = user[1:]

    msg_limit, _ = limits(plan)

    if messages >= msg_limit:
        return False

    cursor.execute("""
        UPDATE users
        SET messages = messages + 1,
            last_time = ?
        WHERE user_id=?
    """, (now, user[0]))

    conn.commit()
    return True

def check_image(user):
    now = time.time()

    _, messages, images, last_time, plan = user

    _, img_limit = limits(plan)

    if images >= img_limit:
        return False

    cursor.execute("""
        UPDATE users
        SET images = images + 1,
            last_time = ?
        WHERE user_id=?
    """, (now, user[0]))

    conn.commit()
    return True

# =====================
# ADMIN
# =====================
def is_admin(chat_id):
    return str(chat_id) == str(ADMIN_ID)

def admin_stats(chat_id):
    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE plan='pro'")
    pro = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(messages) FROM users")
    msg = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(images) FROM users")
    img = cursor.fetchone()[0] or 0

    online = get_online_users()

    send(chat_id,
        f"📊 STATS\n\n👥 users: {users}\n🟢 online: {online}\n💎 pro: {pro}\n💬 msgs: {msg}\n🖼 imgs: {img}",
        admin_keyboard()
    )

# =====================
# ROUTER
# =====================
def router(text, chat_id, user):

    if text == "/start":
        send(chat_id, "🤖 NeoHelper v42 CORE", keyboard())
        return True

    if text == "👑 Админ":
        if not is_admin(chat_id):
            send(chat_id, "⛔ нет доступа")
            return True
        send(chat_id, "👑 Админ панель", admin_keyboard())
        return True

    if text == "🔙 Назад":
        send(chat_id, "Главное меню", keyboard())
        return True

    if text == "📊 Статистика":
        if is_admin(chat_id):
            admin_stats(chat_id)
        return True

    if text == "💬 Чат":
        send(chat_id, "Пиши сообщение 👇", keyboard())
        return True

    if text == "🖼 Картинка":
        send(chat_id, "Опиши картинку 🎨", keyboard())
        return True

    if text == "💳 PRO":
        send(chat_id, "⭐ PRO через Telegram Stars (подключено логически)")
        return True

    if text == "📊 Лимиты":
        msg, img = limits(user[3])
        send(chat_id, f"💬 {msg}\n🖼 {img}", keyboard())
        return True

    return False

# =====================
# WEBHOOK
# =====================
@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json()
    if not data:
        return "ok"

    msg = data.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "")
    user_id = str(chat_id)

    if not chat_id:
        return "ok"

    register(user_id)
    user = get_user(user_id)

    if router(text, chat_id, user):
        return "ok"

    if is_image(text):
        if check_image(user):
            send_image(chat_id, make_image(text))
        else:
            send(chat_id, "🚫 лимит картинок")
        return "ok"

    if check_limits(user):
        reply = ask_ai(user_id, text)
        send(chat_id, reply, keyboard())
    else:
        send(chat_id, "🚫 лимит 40/день")

    return "ok"

# =====================
# HOME
# =====================
@app.route("/")
def home():
    return "NeoHelper v42 CORE ONLINE"

# =====================
# RUN
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)