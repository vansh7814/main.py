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

STATS_FILE = "stats.json"
MSG_IDS_FILE = "message_ids.json"
WORKER_STATE_FILE = "worker_state.json"

def load_json(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("📊 Status"))
    markup.row(KeyboardButton("🟢 Online"), KeyboardButton("🔴 Offline"))
    markup.row(KeyboardButton("⏸️ Cont. Work"), KeyboardButton("▶️ Stop Work"))
    markup.row(KeyboardButton("🧹 Clean RDP"))
    return markup

def format_card(worker, w_data, state_data):
    mode = state_data.get("mode", "Online 🟢")
    work_status = state_data.get("work", "Active ▶️")
    return (
        f"📊 <b>Live Monitor — {worker.upper()}</b>\n\n"
        f"🌐 <b>Network:</b> {mode}\n"
        f"⚙️ <b>Job State:</b> {work_status}\n"
        f"────────────────────\n"
        f"📥 <b>Taken:</b> {w_data.get('taken', 0)}\n"
        f"✅ <b>Done:</b> {w_data.get('done', 0)}\n"
        f"❌ <b>Login Failed:</b> {w_data.get('login_failed', 0)}\n"
        f"🔑 <b>Wrong Pass:</b> {w_data.get('wrong_pass', 0)}\n"
        f"🔧 <b>Manage:</b> {w_data.get('manage', 0)}\n"
        f"────────────────────\n"
        f"⚡ <i>Render Sync: Live</i>"
    )

def ensure_worker_card(worker="vansh"):
    msg_ids = load_json(MSG_IDS_FILE)
    stats = load_json(STATS_FILE)
    states = load_json(WORKER_STATE_FILE)

    if worker not in stats:
        stats[worker] = {"taken": 0, "done": 0, "login_failed": 0, "wrong_pass": 0, "manage": 0}
        save_json(STATS_FILE, stats)

    if worker not in states:
        states[worker] = {"mode": "Online 🟢", "work": "Active ▶️"}
        save_json(WORKER_STATE_FILE, states)

    text = format_card(worker, stats[worker], states[worker])

    if worker in msg_ids:
        chat_id, message_id = msg_ids[worker]
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
            return
        except Exception:
            pass

    try:
        sent = bot.send_message(ADMIN_CHAT_ID, text, parse_mode="HTML", reply_markup=get_admin_keyboard())
        msg_ids[worker] = [ADMIN_CHAT_ID, sent.message_id]
        save_json(MSG_IDS_FILE, msg_ids)
    except Exception as e:
        print(f"Send error: {e}")

@app.route('/')
def home():
    return "Admin & Worker Control API is Live on Render!"

@app.route('/event', methods=['POST'])
def handle_event():
    data = request.json or {}
    worker = str(data.get("worker_name", "vansh")).lower()
    event = data.get("event", "")
    status = data.get("status", "")

    stats = load_json(STATS_FILE)
    if worker not in stats:
        stats[worker] = {"taken": 0, "done": 0, "login_failed": 0, "wrong_pass": 0, "manage": 0}

    if event == "emailcreated":
        stats[worker]["taken"] += 1
    elif event == "emailused":
        if status == "done":
            stats[worker]["done"] += 1
        elif status == "login_failed":
            stats[worker]["login_failed"] += 1
        elif status == "wrong_pass":
            stats[worker]["wrong_pass"] += 1
        elif status == "manage":
            stats[worker]["manage"] += 1

    save_json(STATS_FILE, stats)
    ensure_worker_card(worker)
    return jsonify({"success": True}), 200

@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    bot.send_message(message.chat.id, "🎛️ <b>Admin Control Panel</b>", parse_mode="HTML", reply_markup=get_admin_keyboard())
    ensure_worker_card("vansh")

@bot.message_handler(func=lambda msg: True)
def handle_menu_actions(message):
    text = message.text.strip()
    states = load_json(WORKER_STATE_FILE)
    worker = "vansh"
    if worker not in states:
        states[worker] = {"mode": "Online 🟢", "work": "Active ▶️"}

    if "Status" in text:
        ensure_worker_card(worker)
    elif "Online" in text:
        states[worker]["mode"] = "Online 🟢"
        save_json(WORKER_STATE_FILE, states)
        bot.reply_to(message, "✅ Mode: <b>Online 🟢</b>", parse_mode="HTML")
        ensure_worker_card(worker)
    elif "Offline" in text:
        states[worker]["mode"] = "Offline 🔴"
        save_json(WORKER_STATE_FILE, states)
        bot.reply_to(message, "⛔ Mode: <b>Offline 🔴</b>", parse_mode="HTML")
        ensure_worker_card(worker)
    elif "Cont. Work" in text:
        states[worker]["work"] = "Active ▶️"
        save_json(WORKER_STATE_FILE, states)
        bot.reply_to(message, "▶️ Kaam continue kar diya gaya.", parse_mode="HTML")
        ensure_worker_card(worker)
    elif "Stop Work" in text:
        states[worker]["work"] = "Stopped ⏸️"
        save_json(WORKER_STATE_FILE, states)
        bot.reply_to(message, "⏸️ Kaam temporarily rok diya gaya.", parse_mode="HTML")
        ensure_worker_card(worker)
    elif "Clean RDP" in text:
        bot.reply_to(message, "🧹 <b>Clean signal issued.</b>", parse_mode="HTML")

def start_polling():
    print("Admin Bot Telegram Polling Active...")
    bot.infinity_polling(skip_pending=True)

threading.Thread(target=start_polling, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
