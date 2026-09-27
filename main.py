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

DATA_FILE = "live_data.json"
counter_lock = threading.Lock()

def load_data():
    default_data = {
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
    if not os.path.exists(DATA_FILE):
        return default_data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_data

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Save error: {e}")

def get_admin_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("📊 Status"))
    markup.row(KeyboardButton("🟢 Online"), KeyboardButton("🔴 Offline"))
    markup.row(KeyboardButton("⏸️ Cont. Work"), KeyboardButton("▶️ Stop Work"))
    markup.row(KeyboardButton("🧹 Clean RDP"))
    return markup

def format_all_workers_card(workers):
    if not workers:
        return "⚠️ <b>Filhal koi worker active nahi hai!</b>"

    cards = []
    for worker_name, stats in workers.items():
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

def live_inplace_refresh():
    """Video 2 ki tarah bina naya message banaye card ke numbers ko live smooth update karega."""
    with counter_lock:
        data = load_data()
        chat_id = data.get("chat_id") or ADMIN_CHAT_ID
        msg_id = data.get("msg_id")

        text = format_all_workers_card(data["workers"])

        # Agar pehle se card screen par hai toh direct in-place edit karein
        if msg_id:
            try:
                bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode="HTML"
                )
                return
            except telebot.apihelper.ApiTelegramException as e:
                err_msg = str(e).lower()
                if "message is not modified" in err_msg:
                    return
                if "message to edit not found" in err_msg or "message can't be edited" in err_msg:
                    data["msg_id"] = None
            except Exception as e:
                print(f"Edit warning: {e}")

        # Agar message exist nahi karta, pehli baar create karein
        try:
            sent = bot.send_message(
                chat_id,
                text,
                parse_mode="HTML",
                reply_markup=get_admin_keyboard(),
                disable_notification=True
            )
            data["chat_id"] = chat_id
            data["msg_id"] = sent.message_id
            save_data(data)
        except Exception as e:
            print(f"Initial send error: {e}")

def create_fresh_card(chat_id):
    """Status dabane par purana card delete karega aur bilkul fresh single card banayega."""
    with counter_lock:
        data = load_data()
        old_msg_id = data.get("msg_id")
        target_chat = data.get("chat_id") or chat_id

        if old_msg_id:
            try:
                bot.delete_message(chat_id=target_chat, message_id=old_msg_id)
            except Exception:
                pass

        text = format_all_workers_card(data["workers"])
        try:
            sent = bot.send_message(
                chat_id,
                text,
                parse_mode="HTML",
                reply_markup=get_admin_keyboard(),
                disable_notification=True
            )
            data["chat_id"] = chat_id
            data["msg_id"] = sent.message_id
            save_data(data)
        except Exception as e:
            print(f"Send fresh card error: {e}")

@app.route('/')
def home():
    return "Admin API Live!"

# Email Bot Event: Live smoothly count update karega
@app.route('/event', methods=['POST'])
def handle_event():
    req_data = request.json or {}
    worker = str(req_data.get("worker_name", "vansh")).lower()
    event = req_data.get("event", "")
    status = req_data.get("status", "")
    incoming_data_type = req_data.get("data_type")
    incoming_allotted = req_data.get("allotted")

    data = load_data()
    if worker not in data["workers"]:
        data["workers"][worker] = {
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
        data["workers"][worker]["data_type"] = incoming_data_type
    if incoming_allotted is not None:
        data["workers"][worker]["allotted"] = incoming_allotted

    if event == "emailcreated":
        data["workers"][worker]["taken"] += 1
    elif event == "emailused":
        if status == "done":
            data["workers"][worker]["done"] += 1
        elif status == "login_failed":
            data["workers"][worker]["login_failed"] += 1
        elif status == "wrong_pass":
            data["workers"][worker]["wrong_pass"] += 1
        elif status == "manage":
            data["workers"][worker]["manage"] += 1

    data["workers"][worker]["mode"] = "Online 🟢"
    save_data(data)

    # In-place real-time smooth update trigger
    live_inplace_refresh()
    return jsonify({"success": True}), 200

# Watcher Bot Endpoint
@app.route('/watcher_update', methods=['POST'])
def watcher_update():
    req_data = request.json or {}
    worker = str(req_data.get("worker", "vansh")).lower()
    status = req_data.get("status", "Online 🟢")

    data = load_data()
    if worker in data["workers"]:
        data["workers"][worker]["mode"] = status
        save_data(data)
        live_inplace_refresh()

    return jsonify({"success": True}), 200

# --- Telegram Handlers ---

@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    create_fresh_card(message.chat.id)

@bot.message_handler(func=lambda msg: True)
def handle_menu_actions(message):
    text = message.text.strip()
    chat_id = message.chat.id
    worker = "vansh"
    data = load_data()

    # Status dabane par: purana card delete hokar single active card banega
    if "Status" in text:
        create_fresh_card(chat_id)

    elif "Online" in text:
        if worker in data["workers"]:
            data["workers"][worker]["mode"] = "Online 🟢"
            save_data(data)
        live_inplace_refresh()

    elif "Offline" in text:
        if worker in data["workers"]:
            data["workers"][worker]["mode"] = "Offline 🔴"
            save_data(data)
        live_inplace_refresh()

    elif "Cont. Work" in text:
        live_inplace_refresh()

    elif "Stop Work" in text:
        live_inplace_refresh()

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
