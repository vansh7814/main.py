import json
import os
import time
import threading
from flask import Flask, request, jsonify
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

ADMIN_BOT_TOKEN = "8351462114:AAFTef0-nroxCS_sAP1SaTwHeWDzKJgljX0"
ADMIN_CHAT_ID = 5831204930

bot = telebot.TeleBot(ADMIN_BOT_TOKEN)
app = Flask(__name__)

# Active data store
DATA = {
    "workers": {
        "vansh": {
            "mode": "Online 🟢",
            "data_type": "X",      # Data type: X, A, M, T etc.
            "allotted": 0,         # Allotted count
            "taken": 0,
            "done": 0,
            "login_failed": 0,
            "wrong_pass": 0,
            "manage": 0
        }
    },
    "last_card_msg_id": None
}

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("📊 Status"))
    markup.row(KeyboardButton("🟢 Online"), KeyboardButton("🔴 Offline"))
    markup.row(KeyboardButton("⏸️ Cont. Work"), KeyboardButton("▶️ Stop Work"))
    markup.row(KeyboardButton("🧹 Clean RDP"))
    return markup

def format_all_workers_card():
    if not DATA["workers"]:
        return "⚠️ <b>Filhal koi worker active nahi hai!</b>"

    cards = []
    for worker_name, stats in DATA["workers"].items():
        data_type = stats.get("data_type", "X")
        allotted = stats.get("allotted", 0)
        taken = stats.get("taken", 0)
        done = stats.get("done", 0)
        failed = stats.get("login_failed", 0)
        wrong = stats.get("wrong_pass", 0)
        manage = stats.get("manage", 0)
        
        # Used Json ka total sum
        used_total = done + failed + wrong + manage

        card = (
            f"📊 <b>Live Monitor — {worker_name.upper()}</b>\n\n"
            f"🌐 <b>Network:</b> {stats.get('mode', 'Online 🟢')}\n"
            f"📦 <b>{data_type} allotted:</b> {allotted}\n"
            f"────────────────────\n"
            f"📥 <b>Taken:</b> {taken}\n"
            f"📝 <b>Used Json:</b> {used_total}\n"
            f"✅ <b>Done:</b> {done}\n"
            f"❌ <b>Login Failed:</b> {failed}\n"
            f"🔑 <b>Wrong Pass:</b> {wrong}\n"
            f"🔧 <b>Manage:</b> {manage}"
        )
        cards.append(card)

    return "\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(cards)

def update_or_send_card(force_new=False):
    text = format_all_workers_card()
    msg_id = DATA.get("last_card_msg_id")

    if msg_id and not force_new:
        try:
            bot.edit_message_text(text, chat_id=ADMIN_CHAT_ID, message_id=msg_id, parse_mode="HTML")
            return
        except Exception:
            pass

    try:
        sent = bot.send_message(
            ADMIN_CHAT_ID,
            text,
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(),
            disable_notification=True
        )
        DATA["last_card_msg_id"] = sent.message_id
    except Exception as e:
        print(f"Error sending card: {e}")

@app.route('/')
def home():
    return "Admin API Live!"

# Email Bot se event data aane par
@app.route('/event', methods=['POST'])
def handle_event():
    data = request.json or {}
    worker = str(data.get("worker_name", "vansh")).lower()
    event = data.get("event", "")
    status = data.get("status", "")
    
    # Email Bot se data_type ya allotted bhi bheja ja sakta hai
    incoming_data_type = data.get("data_type")
    incoming_allotted = data.get("allotted")

    if worker not in DATA["workers"]:
        DATA["workers"][worker] = {
            "mode": "Online 🟢",
            "data_type": incoming_data_type or "X",
            "allotted": incoming_allotted or 0,
            "taken": 0,
            "done": 0,
            "login_failed": 0,
            "wrong_pass": 0,
            "manage": 0
        }

    # Data Type / Allotted update agar payload me aaya ho
    if incoming_data_type:
        DATA["workers"][worker]["data_type"] = incoming_data_type
    if incoming_allotted is not None:
        DATA["workers"][worker]["allotted"] = incoming_allotted

    if event == "emailcreated":
        DATA["workers"][worker]["taken"] += 1
    elif event == "emailused":
        if status == "done":
            DATA["workers"][worker]["done"] += 1
        elif status == "login_failed":
            DATA["workers"][worker]["login_failed"] += 1
        elif status == "wrong_pass":
            DATA["workers"][worker]["wrong_pass"] += 1
        elif status == "manage":
            DATA["workers"][worker]["manage"] += 1

    DATA["workers"][worker]["mode"] = "Online 🟢"

    # Silent Auto-Refresh Live Card
    update_or_send_card(force_new=False)
    return jsonify({"success": True}), 200

# Watcher Bot connection endpoint
@app.route('/watcher_update', methods=['POST'])
def watcher_update():
    data = request.json or {}
    worker = str(data.get("worker", "vansh")).lower()
    status = data.get("status", "Online 🟢")

    if worker not in DATA["workers"]:
        DATA["workers"][worker] = {
            "mode": status,
            "data_type": "X",
            "allotted": 0,
            "taken": 0, "done": 0, "login_failed": 0, "wrong_pass": 0, "manage": 0
        }
    else:
        DATA["workers"][worker]["mode"] = status

    update_or_send_card(force_new=False)
    return jsonify({"success": True}), 200

# --- Telegram Commands ---

@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    update_or_send_card(force_new=True)

@bot.message_handler(func=lambda msg: True)
def handle_menu_actions(message):
    text = message.text.strip()
    worker = "vansh"

    if "Status" in text:
        update_or_send_card(force_new=True)

    elif "Online" in text:
        if worker in DATA["workers"]:
            DATA["workers"][worker]["mode"] = "Online 🟢"
        bot.send_message(ADMIN_CHAT_ID, f"🟢 <b>Status Check:</b>\nWorker <code>{worker}</code> marked <b>ONLINE</b>.", parse_mode="HTML")
        update_or_send_card(force_new=False)

    elif "Offline" in text:
        if worker in DATA["workers"]:
            DATA["workers"][worker]["mode"] = "Offline 🔴"
        bot.send_message(ADMIN_CHAT_ID, f"🔴 <b>Status Check:</b>\nWorker <code>{worker}</code> marked <b>OFFLINE</b>.", parse_mode="HTML")
        update_or_send_card(force_new=False)

    elif "Cont. Work" in text:
        bot.send_message(ADMIN_CHAT_ID, "▶️ Worker <b>VANSH</b> work state: <b>Active</b>", parse_mode="HTML")

    elif "Stop Work" in text:
        bot.send_message(ADMIN_CHAT_ID, "⏸️ Worker <b>VANSH</b> work state: <b>Stopped</b>", parse_mode="HTML")

    elif "Clean RDP" in text:
        bot.send_message(ADMIN_CHAT_ID, "🧹 <b>Clean signal issued for Vansh.</b>", parse_mode="HTML")

def start_polling():
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        print(f"Webhook remove warning: {e}")

    print("Admin Bot Telegram Polling Active...")
    bot.infinity_polling(skip_pending=True)

if __name__ == '__main__':
    threading.Thread(target=start_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
