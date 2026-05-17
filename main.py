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
    last_time REAL DEFAULT 0,
    plan TEXT DEFAULT 'basic',
    chat_mode TEXT DEFAULT 'smart',
    image_mode INTEGER DEFAULT 0,
    subscription_end REAL DEFAULT 0
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

# ================= PLANS =================
PLANS = {
    "basic": {"messages": 40, "images": 3, "price": 0},
    "pro": {"messages": 9999, "images": 9999, "price": 100},
    "ultra": {"messages": 9999, "images": 9999, "price": 300}
}

# ================= USER =================
def register(uid):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit()

def get_user(uid):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cursor.fetchone()

def is_sub_active(user):
    return time.time() < user[7]

def get_plan(user):
    if is_sub_active(user):
        return user[4]
    return "basic"

# ================= MEMORY =================
def save_memory(uid, role, text):
    cursor.execute("INSERT INTO memory VALUES (?,?,?)", (uid, role, text))
    conn.commit()

def load_memory(uid):
    cursor.execute("SELECT role,content FROM memory WHERE user_id=? ORDER BY rowid DESC LIMIT 6", (uid,))
    rows = cursor.fetchall()
    return list(reversed([{"role": r[0], "content": r[1]} for r in rows]))

# ================= SEND =================
def send(chat_id, text, kb=None):
    data = {"chat_id": chat_id, "text": text}
    if kb:
        data["reply_markup"] = kb
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=data)

def send_image(chat_id, url):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                  json={"chat_id": chat_id, "photo": url})

# ================= KEYBOARD =================
def keyboard():
    return {
        "keyboard": [["💬 Чат", "🖼 Картинка"], ["💳 PRO ⭐", "👑 Админ"]],
        "resize_keyboard": True
    }

def chat_keyboard():
    return {
        "keyboard": [["⚡ Быстро","🧠 Умно","📚 Подробно"],["🔙 Назад"]],
        "resize_keyboard": True
    }

# ================= IMAGE =================
STYLES = {
    "anime": "anime style, detailed",
    "realistic": "ultra realistic, cinematic",
    "3d": "3d render, octane"
}

def enhance_prompt(text, style="realistic"):
    return f"{text}, {STYLES.get(style)}, high quality"

def make_img(prompt):
    prompt = prompt.replace(" ", "%20")
    return f"https://image.pollinations.ai/prompt/{prompt}"

# ================= AI =================
def ask_ai(uid, text):
    save_memory(uid, "user", text)
    hist = load_memory(uid)

    cursor.execute("SELECT chat_mode FROM users WHERE user_id=?", (uid,))
    mode = cursor.fetchone()[0]

    style = {
        "fast": "short answer",
        "smart": "normal answer",
        "deep": "very detailed explanation"
    }

    system = f"You are AI assistant. no greetings. {style.get(mode)}"

    messages = [{"role":"system","content":system}] + hist

    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
        json={
            "model":"openai/gpt-3.5-turbo",
            "messages":messages,
            "temperature":0.8,
            "max_tokens":300
        }
    )

    ans = r.json()["choices"][0]["message"]["content"]
    save_memory(uid, "assistant", ans)
    return ans

# ================= LIMITS =================
def check_limits(user):
    plan = get_plan(user)
    msg_limit = PLANS[plan]["messages"]

    if user[1] >= msg_limit:
        return False

    cursor.execute("UPDATE users SET messages=messages+1 WHERE user_id=?", (user[0],))
    conn.commit()
    return True

def check_img(user):
    plan = get_plan(user)
    img_limit = PLANS[plan]["images"]

    if user[2] >= img_limit:
        return False

    cursor.execute("UPDATE users SET images=images+1 WHERE user_id=?", (user[0],))
    conn.commit()
    return True

# ================= PAYMENT =================
def send_invoice(chat_id, plan="pro"):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice",
        json={
            "chat_id": chat_id,
            "title": f"{plan.upper()} plan",
            "description": "AI access",
            "payload": plan,
            "currency": "XTR",
            "prices":[{"label":plan,"amount":PLANS[plan]["price"]}]
        }
    )

# ================= ADMIN =================
def is_admin(uid):
    return str(uid) == ADMIN_ID

def give_pro(uid, plan="pro"):
    end = time.time() + 30*86400
    cursor.execute("UPDATE users SET plan=?, subscription_end=? WHERE user_id=?",
                   (plan, end, uid))
    conn.commit()

# ================= ROUTER =================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    msg = data.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id"))
    text = msg.get("text", "")

    register(chat_id)
    user = get_user(chat_id)

    # PAYMENT
    if "successful_payment" in msg:
        payload = msg["successful_payment"]["invoice_payload"]
        give_pro(chat_id, payload)
        send(chat_id, "💎 PRO активирован!")
        return "ok"

    if text == "/start":
        send(chat_id, "🤖 v43 SaaS", keyboard())
        return "ok"

    if text == "💳 PRO ⭐":
        send_invoice(chat_id, "pro")
        return "ok"

    if text == "💬 Чат":
        send(chat_id, "чат режим", chat_keyboard())
        return "ok"

    if text == "🖼 Картинка":
        cursor.execute("UPDATE users SET image_mode=1 WHERE user_id=?", (chat_id,))
        conn.commit()
        send(chat_id, "режим картинки включён", keyboard())
        return "ok"

    if text == "👑 Админ" and is_admin(chat_id):
        send(chat_id, "admin panel")
        return "ok"

    # IMAGE MODE
    cursor.execute("SELECT image_mode FROM users WHERE user_id=?", (chat_id,))
    im = cursor.fetchone()[0]

    if im == 1:
        if check_img(user):
            prompt = enhance_prompt(text)
            send_image(chat_id, make_img(prompt))
            cursor.execute("UPDATE users SET image_mode=0 WHERE user_id=?", (chat_id,))
            conn.commit()
        return "ok"

    # CHAT
    if check_limits(user):
        reply = ask_ai(chat_id, text)
        send(chat_id, reply, keyboard())
    else:
        send(chat_id, "limit")

    return "ok"

@app.route("/")
def home():
    return "v43 SaaS ONLINE"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))