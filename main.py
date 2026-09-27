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

# State data
DATA = {
    "msg_id": None,
    "needs_update": False,
    "last_text": "",
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

def send_fresh_card():
    """Purane card ko safely delete karega aur bilkul ek naya card banayega."""
    old_id = DATA["msg_id"]
    if old_id:
        try:
            bot.delete_message(chat_id=ADMIN_CHAT_ID, message_id=old_id)
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
        DATA["msg_id"] = sent.message_id
        DATA["last_text"] = text
        DATA["needs_update"] = False
    except Exception as e:
        print(f"Send Error: {e}")

# Video 2 wala smooth real-time update loop
def smooth_updater_thread():
    while True:
        try:
            if DATA["needs_update"] and DATA["msg_id"]:
                text = format_all_workers_card()
                if text != DATA["last_text"]:
                    try:
                        bot.edit_message_text(
                            text,
                            chat_id=ADMIN_CHAT_ID,
                            message_id=DATA["msg_id"],
                            parse_mode="HTML"
                        )
                        DATA["last_text"] = text
                        DATA["needs_update"] = False
                    except telebot.apihelper.ApiTelegramException as te:
                        if "message to edit not found" in str(te).lower():
                            send_fresh_card()
                        elif "message is not modified" in str(te).lower():
                            DATA["needs_update"] = False
                    except Exception as ex:
                        print(f"Edit warning: {ex}")
        except Exception as e:
            print(f"Loop error: {e}")
        time.sleep(0.5)  # Telegram API smooth rate limit (no freezing, no flood limit)

@app.route('/')
def home():
    return "Admin API Live!"

# Email Bot Event
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

    if not DATA["msg_id"]:
        send_fresh_card()
    else:
        DATA["needs_update"] = True  # Smooth queue ko update bhejta hai (no duplicate message)

    return jsonify({"success": True}), 200

# Watcher Bot Endpoint
@app.route('/watcher_update', methods=['POST'])
def watcher_update():
    data = request.json or {}
    worker = str(data.get("worker", "vansh")).lower()
    status = data.get("status", "Online 🟢")

    if worker in DATA["workers"]:
        DATA["workers"][worker]["mode"] = status
        DATA["needs_update"] = True

    return jsonify({"success": True}), 200

# --- Telegram Commands ---

@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    send_fresh_card()

@bot.message_handler(func=lambda msg: True)
def handle_menu_actions(message):
    text = message.text.strip()
    worker = "vansh"

    # Status dabane par: purana card REMOVE hoga aur ek single fresh card banega
    if "Status" in text:
        send_fresh_card()

    elif "Online" in text:
        if worker in DATA["workers"]:
            DATA["workers"][worker]["mode"] = "Online 🟢"
        DATA["needs_update"] = True

    elif "Offline" in text:
        if worker in DATA["workers"]:
            DATA["workers"][worker]["mode"] = "Offline 🔴"
        DATA["needs_update"] = True

    elif "Cont. Work" in text:
        DATA["needs_update"] = True

    elif "Stop Work" in text:
        DATA["needs_update"] = True

    elif "Clean RDP" in text:
        bot.send_message(ADMIN_CHAT_ID, "🧹 <b>Clean command issued.</b>", parse_mode="HTML")

def start_polling():
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass
    print("Telegram Polling Started...")
    bot.infinity_polling(skip_pending=True)

if __name__ == '__main__':
    # 1. Background live smooth update thread
    threading.Thread(target=smooth_updater_thread, daemon=True).start()
    # 2. Telegram polling thread
    threading.Thread(target=start_polling, daemon=True).start()
    # 3. Webhook/API Flask Server
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
