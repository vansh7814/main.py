import json
import os
import time
import threading
from flask import Flask, request, jsonify
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

ADMIN_BOT_TOKEN = "8351462114:AAFTef0-nroxCS_sAP1SaTwHeWDzKJgljX0"
ADMIN_CHAT_ID = 5831204930  # Sirf yeh ID bot access kar sakti hai

bot = telebot.TeleBot(ADMIN_BOT_TOKEN)
app = Flask(__name__)

# State data
DATA = {
    "chat_id": ADMIN_CHAT_ID,
    "msg_id": None,
    "workers": {
        "vansh": {
            "mode": "Online 🟢",
            "data_type": "X",
            "allotted": 0,
            "taken": 0,
            "done": 0,
            "login_failed": 0,
            "wrong_pass": 0,
            "manage": 0
        }
    }
}

def is_admin(user_id):
    """Check karega ki request authorized admin se aayi hai ya nahi."""
    return str(user_id) == str(ADMIN_CHAT_ID)

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("📊 Status"))
    markup.row(KeyboardButton("🟢 Online"), KeyboardButton("🔴 Offline"))
    markup.row(KeyboardButton("⏸️ Cont. Work"), KeyboardButton("▶️ Stop Work"))
    markup.row(KeyboardButton("🧹 Clean RDP"))
    return markup

def format_all_workers_card():
    cards = []
    for worker_name, stats in DATA["workers"].items():
        data_type = stats.get("data_type", "X")
        allotted = stats.get("allotted", 0)
        taken = stats.get("taken", 0)
        done = stats.get("done", 0)
        failed = stats.get("login_failed", 0)
        wrong = stats.get("wrong_pass", 0)
        manage = stats.get("manage", 0)
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

def force_edit_only():
    chat_id = DATA.get("chat_id")
    msg_id = DATA.get("msg_id")

    if not chat_id or not msg_id:
        return

    text = format_all_workers_card()
    try:
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="HTML"
        )
    except Exception:
        pass

def recreate_single_card(chat_id):
    old_msg_id = DATA.get("msg_id")
    old_chat_id = DATA.get("chat_id") or chat_id

    if old_msg_id:
        try:
            bot.delete_message(chat_id=old_chat_id, message_id=old_msg_id)
        except Exception:
            pass

    text = format_all_workers_card()
    try:
        sent = bot.send_message(
            chat_id,
            text,
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(),
            disable_notification=True
        )
        DATA["chat_id"] = chat_id
        DATA["msg_id"] = sent.message_id
    except Exception as e:
        print(f"Error creating card: {e}")

@app.route('/')
def home():
    return "Admin API Live!"

# Email Bot Event
@app.route('/event', methods=['POST'])
def handle_event():
    req_data = request.json or {}
    worker = str(req_data.get("worker_name", "vansh")).lower()
    event = req_data.get("event", "")
    status = req_data.get("status", "")
    incoming_data_type = req_data.get("data_type")
    incoming_allotted = req_data.get("allotted")

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

    force_edit_only()
    return jsonify({"success": True}), 200

# Watcher Bot Endpoint
@app.route('/watcher_update', methods=['POST'])
def watcher_update():
    req_data = request.json or {}
    worker = str(req_data.get("worker", "vansh")).lower()
    status = req_data.get("status", "Online 🟢")

    if worker in DATA["workers"]:
        DATA["workers"][worker]["mode"] = status
        force_edit_only()

    return jsonify({"success": True}), 200

# --- Telegram Handlers ---

@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    # Sirf Admin access kar sakta hai
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "🚫 <b>Access Denied:</b> You are not authorized to use this bot.", parse_mode="HTML")
        return

    DATA["chat_id"] = message.chat.id
    bot.send_message(
        message.chat.id,
        "👋 <b>Welcome Admin!</b>\n\nNiche diye gaye buttons se bot control karein.",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )

@bot.message_handler(func=lambda msg: True)
def handle_menu_actions(message):
    # Sirf Admin access kar sakta hai
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "🚫 <b>Access Denied:</b> You are not authorized to use this bot.", parse_mode="HTML")
        return

    text = message.text.strip()
    chat_id = message.chat.id
    worker = "vansh"

    if "Status" in text:
        recreate_single_card(chat_id)

    elif "Online" in text:
        if worker in DATA["workers"]:
            DATA["workers"][worker]["mode"] = "Online 🟢"
        force_edit_only()

    elif "Offline" in text:
        if worker in DATA["workers"]:
            DATA["workers"][worker]["mode"] = "Offline 🔴"
        force_edit_only()

    elif "Cont. Work" in text:
        force_edit_only()

    elif "Stop Work" in text:
        force_edit_only()

    elif "Clean RDP" in text:
        bot.send_message(chat_id, "🧹 <b>Clean command issued.</b>", parse_mode="HTML")

def start_polling():
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass
    print("Telegram Polling Active...")
    bot.infinity_polling(skip_pending=True)

if __name__ == '__main__':
    threading.Thread(target=start_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
