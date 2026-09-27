import json
import os
import threading
from flask import Flask, request, jsonify
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

ADMIN_BOT_TOKEN = "8351462114:AAER7HhrRJcYnvAj19CedKIkRK3ezuwvM-s"
ADMIN_CHAT_ID = 5831204930

bot = telebot.TeleBot(ADMIN_BOT_TOKEN)
app = Flask(__name__)

# State data in-memory taaki Render restart hone par bhi fast rahe
DATA = {
    "stats": {"taken": 0, "done": 0, "login_failed": 0, "wrong_pass": 0, "manage": 0},
    "workers": {
        "vansh": {"mode": "Online 🟢", "work": "Active ▶️", "last_active": "Just now"}
    },
    "card_msg_id": None
}

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("📊 Status"))
    markup.row(KeyboardButton("🟢 Online"), KeyboardButton("🔴 Offline"))
    markup.row(KeyboardButton("⏸️ Cont. Work"), KeyboardButton("▶️ Stop Work"))
    markup.row(KeyboardButton("🧹 Clean RDP"))
    return markup

def format_card(worker="vansh"):
    w_info = DATA["workers"].get(worker, {"mode": "Online 🟢", "work": "Active ▶️"})
    stats = DATA["stats"]
    return (
        f"📊 <b>Live Monitor — {worker.upper()}</b>\n\n"
        f"🌐 <b>Network:</b> {w_info['mode']}\n"
        f"⚙️ <b>Job State:</b> {w_info['work']}\n"
        f"────────────────────\n"
        f"📥 <b>Taken:</b> {stats['taken']}\n"
        f"✅ <b>Done:</b> {stats['done']}\n"
        f"❌ <b>Login Failed:</b> {stats['login_failed']}\n"
        f"🔑 <b>Wrong Pass:</b> {stats['wrong_pass']}\n"
        f"🔧 <b>Manage:</b> {stats['manage']}\n"
        f"────────────────────\n"
        f"⚡ <i>Render Sync: Live</i>"
    )

def refresh_card(force_new=False):
    text = format_card("vansh")
    
    # Purane message ko edit karne ki koshish karein taaki chat me spam na ho
    if DATA["card_msg_id"] and not force_new:
        try:
            bot.edit_message_text(text, chat_id=ADMIN_CHAT_ID, message_id=DATA["card_msg_id"], parse_mode="HTML")
            return
        except Exception:
            pass

    # Agar edit fail ho ya pehli bar ho, toh naya bhej kar ID save karein
    try:
        sent = bot.send_message(ADMIN_CHAT_ID, text, parse_mode="HTML", reply_markup=get_admin_keyboard())
        DATA["card_msg_id"] = sent.message_id
    except Exception as e:
        print(f"Error sending card: {e}")

@app.route('/')
def home():
    return "Admin & Worker API Live!"

@app.route('/event', methods=['POST'])
def handle_event():
    data = request.json or {}
    event = data.get("event", "")
    status = data.get("status", "")

    if event == "emailcreated":
        DATA["stats"]["taken"] += 1
    elif event == "emailused":
        if status == "done":
            DATA["stats"]["done"] += 1
        elif status == "login_failed":
            DATA["stats"]["login_failed"] += 1
        elif status == "wrong_pass":
            DATA["stats"]["wrong_pass"] += 1
        elif status == "manage":
            DATA["stats"]["manage"] += 1

    DATA["workers"]["vansh"]["mode"] = "Online 🟢"
    refresh_card(force_new=False)
    return jsonify({"success": True}), 200

# Watcher Bot ke liye endpoint (jab aap watcher attach karenge)
@app.route('/watcher_update', methods=['POST'])
def watcher_update():
    data = request.json or {}
    worker = data.get("worker", "vansh")
    status = data.get("status", "Online 🟢")
    if worker in DATA["workers"]:
        DATA["workers"][worker]["mode"] = status
    refresh_card(force_new=False)
    return jsonify({"success": True}), 200

# --- Telegram Handlers ---

@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    refresh_card(force_new=True)

@bot.message_handler(func=lambda msg: True)
def handle_menu_actions(message):
    text = message.text.strip()
    worker = "vansh"

    if "Status" in text:
        refresh_card(force_new=True)

    elif "Online" in text:
        DATA["workers"][worker]["mode"] = "Online 🟢"
        bot.send_message(ADMIN_CHAT_ID, f"🟢 <b>Status Check:</b>\nWorker <code>{worker}</code> is currently marked <b>ONLINE</b>.", parse_mode="HTML")
        refresh_card(force_new=False)

    elif "Offline" in text:
        DATA["workers"][worker]["mode"] = "Offline 🔴"
        bot.send_message(ADMIN_CHAT_ID, f"🔴 <b>Status Check:</b>\nWorker <code>{worker}</code> is marked <b>OFFLINE</b>.", parse_mode="HTML")
        refresh_card(force_new=False)

    elif "Cont. Work" in text:
        DATA["workers"][worker]["work"] = "Active ▶️"
        bot.send_message(ADMIN_CHAT_ID, "▶️ Worker <b>VANSH</b> work state set to: <b>Active</b>", parse_mode="HTML")
        refresh_card(force_new=False)

    elif "Stop Work" in text:
        DATA["workers"][worker]["work"] = "Stopped ⏸️"
        bot.send_message(ADMIN_CHAT_ID, "⏸️ Worker <b>VANSH</b> work state set to: <b>Stopped</b>", parse_mode="HTML")
        refresh_card(force_new=False)

    elif "Clean RDP" in text:
        bot.send_message(ADMIN_CHAT_ID, "🧹 <b>Signal Sent:</b> Vansh RDP will be reset.", parse_mode="HTML")

def start_polling():
    bot.infinity_polling(skip_pending=True)

if __name__ == '__main__':
    # Background Telegram Polling
    threading.Thread(target=start_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
