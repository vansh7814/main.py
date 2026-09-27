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

# State data aur card ID tracker
DATA = {
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
    },
    "active_card_msg_id": None
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

def silent_auto_edit_card():
    """Worker event ke waqt sirf exist karne wale card ko bina kisi awaz ke edit karega."""
    msg_id = DATA.get("active_card_msg_id")
    if not msg_id:
        return  # Agar card active nahi hai toh bilkul naya message send nahi karega

    text = format_all_workers_card()
    try:
        bot.edit_message_text(text, chat_id=ADMIN_CHAT_ID, message_id=msg_id, parse_mode="HTML")
    except Exception:
        # Text same hone par Telegram error ignore karein
        pass

def show_single_fresh_card():
    """Purane message ko delete karke ek hi fresh card banata hai."""
    old_msg_id = DATA.get("active_card_msg_id")
    if old_msg_id:
        try:
            bot.delete_message(chat_id=ADMIN_CHAT_ID, message_id=old_msg_id)
        except Exception:
            pass

    text = format_all_workers_card()
    try:
        sent = bot.send_message(
            ADMIN_CHAT_ID,
            text,
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(),
            disable_notification=True
        )
        DATA["active_card_msg_id"] = sent.message_id
    except Exception as e:
        print(f"Card error: {e}")

@app.route('/')
def home():
    return "Admin API Live!"

# Email Bot Event: 100% Silent Background Edit
@app.route('/event', methods=['POST'])
def handle_event():
    data = request.json or {}
    worker = str(data.get("worker_name", "vansh")).lower()
    event = data.get("event", "")
    status = data.get("status", "")
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

    # Wahi ek card silently live update hoga
    silent_auto_edit_card()
    return jsonify({"success": True}), 200

# Watcher Bot Endpoint
@app.route('/watcher_update', methods=['POST'])
def watcher_update():
    data = request.json or {}
    worker = str(data.get("worker", "vansh")).lower()
    status = data.get("status", "Online 🟢")

    if worker in DATA["workers"]:
        DATA["workers"][worker]["mode"] = status
    
    silent_auto_edit_card()
    return jsonify({"success": True}), 200

# --- Telegram User Actions ---

@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    show_single_fresh_card()

@bot.message_handler(func=lambda msg: True)
def handle_menu_actions(message):
    text = message.text.strip()
    worker = "vansh"

    # Status dabane par purana card hata kar single fresh card banega
    if "Status" in text:
        show_single_fresh_card()

    elif "Online" in text:
        if worker in DATA["workers"]:
            DATA["workers"][worker]["mode"] = "Online 🟢"
        bot.send_message(ADMIN_CHAT_ID, f"🟢 Worker <code>{worker}</code>: <b>ONLINE</b>", parse_mode="HTML")
        silent_auto_edit_card()

    elif "Offline" in text:
        if worker in DATA["workers"]:
            DATA["workers"][worker]["mode"] = "Offline 🔴"
        bot.send_message(ADMIN_CHAT_ID, f"🔴 Worker <code>{worker}</code>: <b>OFFLINE</b>", parse_mode="HTML")
        silent_auto_edit_card()

    elif "Cont. Work" in text:
        bot.send_message(ADMIN_CHAT_ID, "▶️ <b>VANSH</b>: Work Continued", parse_mode="HTML")
        silent_auto_edit_card()

    elif "Stop Work" in text:
        bot.send_message(ADMIN_CHAT_ID, "⏸️ <b>VANSH</b>: Work Stopped", parse_mode="HTML")
        silent_auto_edit_card()

    elif "Clean RDP" in text:
        bot.send_message(ADMIN_CHAT_ID, "🧹 <b>Clean command issued.</b>", parse_mode="HTML")

def start_polling():
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass
    bot.infinity_polling(skip_pending=True)

if __name__ == '__main__':
    threading.Thread(target=start_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
