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

STATE_FILE = "state.json"

def get_state():
    default_state = {
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
    if not os.path.exists(STATE_FILE):
        return default_state
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return default_state

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Error saving state: {e}")

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

def update_or_create_card(force_new=False):
    state = get_state()
    text = format_all_workers_card(state["workers"])
    msg_id = state.get("msg_id")

    # Agar naya card nahi mangwaya aur purana card hai, toh direct edit karein
    if msg_id and not force_new:
        try:
            bot.edit_message_text(text, chat_id=ADMIN_CHAT_ID, message_id=msg_id, parse_mode="HTML")
            return
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e).lower():
                return
            print(f"Edit failed, creating fresh card: {e}")
        except Exception as e:
            print(f"Edit error: {e}")

    # Purana message delete karke fresh send karein (agar force_new ho)
    if msg_id:
        try:
            bot.delete_message(chat_id=ADMIN_CHAT_ID, message_id=msg_id)
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
        state["msg_id"] = sent.message_id
        save_state(state)
    except Exception as e:
        print(f"Send error: {e}")

@app.route('/')
def home():
    return "Admin API Live!"

# Email Bot se live update aane par
@app.route('/event', methods=['POST'])
def handle_event():
    data = request.json or {}
    worker = str(data.get("worker_name", "vansh")).lower()
    event = data.get("event", "")
    status = data.get("status", "")
    incoming_data_type = data.get("data_type")
    incoming_allotted = data.get("allotted")

    state = get_state()
    if worker not in state["workers"]:
        state["workers"][worker] = {
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
        state["workers"][worker]["data_type"] = incoming_data_type
    if incoming_allotted is not None:
        state["workers"][worker]["allotted"] = incoming_allotted

    if event == "emailcreated":
        state["workers"][worker]["taken"] += 1
    elif event == "emailused":
        if status == "done":
            state["workers"][worker]["done"] += 1
        elif status == "login_failed":
            state["workers"][worker]["login_failed"] += 1
        elif status == "wrong_pass":
            state["workers"][worker]["wrong_pass"] += 1
        elif status == "manage":
            state["workers"][worker]["manage"] += 1

    state["workers"][worker]["mode"] = "Online 🟢"
    save_state(state)

    # Turant existing card edit hoga
    update_or_create_card(force_new=False)
    return jsonify({"success": True}), 200

# Watcher Bot Endpoint
@app.route('/watcher_update', methods=['POST'])
def watcher_update():
    data = request.json or {}
    worker = str(data.get("worker", "vansh")).lower()
    status = data.get("status", "Online 🟢")

    state = get_state()
    if worker in state["workers"]:
        state["workers"][worker]["mode"] = status
        save_state(state)
        update_or_create_card(force_new=False)

    return jsonify({"success": True}), 200

# --- Telegram Handlers ---

@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    update_or_create_card(force_new=True)

@bot.message_handler(func=lambda msg: True)
def handle_menu_actions(message):
    text = message.text.strip()
    worker = "vansh"
    state = get_state()

    if "Status" in text:
        update_or_create_card(force_new=True)

    elif "Online" in text:
        if worker in state["workers"]:
            state["workers"][worker]["mode"] = "Online 🟢"
            save_state(state)
        bot.send_message(ADMIN_CHAT_ID, f"🟢 Worker <code>{worker}</code>: <b>ONLINE</b>", parse_mode="HTML")
        update_or_create_card(force_new=False)

    elif "Offline" in text:
        if worker in state["workers"]:
            state["workers"][worker]["mode"] = "Offline 🔴"
            save_state(state)
        bot.send_message(ADMIN_CHAT_ID, f"🔴 Worker <code>{worker}</code>: <b>OFFLINE</b>", parse_mode="HTML")
        update_or_create_card(force_new=False)

    elif "Cont. Work" in text:
        bot.send_message(ADMIN_CHAT_ID, "▶️ <b>VANSH</b>: Work Continued", parse_mode="HTML")
        update_or_create_card(force_new=False)

    elif "Stop Work" in text:
        bot.send_message(ADMIN_CHAT_ID, "⏸️ <b>VANSH</b>: Work Stopped", parse_mode="HTML")
        update_or_create_card(force_new=False)

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
