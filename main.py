import json
import os
import time
import threading
from flask import Flask, request, jsonify
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

ADMIN_BOT_TOKEN = "8351462114:AAER7HhrRJcYnvAj19CedKIkRK3ezuwvM-s"
ADMIN_CHAT_ID = 5831204930

bot = telebot.TeleBot(ADMIN_BOT_TOKEN)
app = Flask(__name__)

# Active data store
DATA = {
    "workers": {
        "vansh": {
            "mode": "Online 🟢",
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
    if not DATA["workers"]:
        return "⚠️ <b>Filhal koi worker active nahi hai!</b>"

    cards = []
    for worker_name, stats in DATA["workers"].items():
        card = (
            f"📊 <b>Live Monitor — {worker_name.upper()}</b>\n\n"
            f"🌐 <b>Network:</b> {stats.get('mode', 'Online 🟢')}\n"
            f"📥 <b>Taken:</b> {stats.get('taken', 0)}\n"
            f"────────────────────\n"
            f"      <b>Used Json</b>\n"
            f"✅ <b>Done:</b> {stats.get('done', 0)}\n"
            f"❌ <b>Login Failed:</b> {stats.get('login_failed', 0)}\n"
            f"🔑 <b>Wrong Pass:</b> {stats.get('wrong_pass', 0)}\n"
            f"🔧 <b>Manage:</b> {stats.get('manage', 0)}"
        )
        cards.append(card)

    return "\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(cards)

@app.route('/')
def home():
    return "Admin API Live!"

# Email Bot se silent data receive karna
@app.route('/event', methods=['POST'])
def handle_event():
    data = request.json or {}
    worker = str(data.get("worker_name", "vansh")).lower()
    event = data.get("event", "")
    status = data.get("status", "")

    if worker not in DATA["workers"]:
        DATA["workers"][worker] = {
            "mode": "Online 🟢",
            "taken": 0,
            "done": 0,
            "login_failed": 0,
            "wrong_pass": 0,
            "manage": 0
        }

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
    return jsonify({"success": True}), 200

# Telegram Handlers
@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    text = format_all_workers_card()
    bot.send_message(ADMIN_CHAT_ID, text, parse_mode="HTML", reply_markup=get_admin_keyboard())

@bot.message_handler(func=lambda msg: True)
def handle_menu_actions(message):
    text = message.text.strip()
    worker = "vansh"

    if "Status" in text:
        report_text = format_all_workers_card()
        bot.send_message(ADMIN_CHAT_ID, report_text, parse_mode="HTML", reply_markup=get_admin_keyboard())

    elif "Online" in text:
        if worker in DATA["workers"]:
            DATA["workers"][worker]["mode"] = "Online 🟢"
        bot.send_message(ADMIN_CHAT_ID, f"🟢 <b>Status Check:</b>\nWorker <code>{worker}</code> marked <b>ONLINE</b>.", parse_mode="HTML")

    elif "Offline" in text:
        if worker in DATA["workers"]:
            DATA["workers"][worker]["mode"] = "Offline 🔴"
        bot.send_message(ADMIN_CHAT_ID, f"🔴 <b>Status Check:</b>\nWorker <code>{worker}</code> marked <b>OFFLINE</b>.", parse_mode="HTML")

    elif "Cont. Work" in text:
        bot.send_message(ADMIN_CHAT_ID, "▶️ Worker <b>VANSH</b> work state: <b>Active</b>", parse_mode="HTML")

    elif "Stop Work" in text:
        bot.send_message(ADMIN_CHAT_ID, "⏸️ Worker <b>VANSH</b> work state: <b>Stopped</b>", parse_mode="HTML")

    elif "Clean RDP" in text:
        bot.send_message(ADMIN_CHAT_ID, "🧹 <b>Clean signal issued for Vansh.</b>", parse_mode="HTML")

def start_polling():
    # Conflict 409 se bachne ke liye pehle webhook permanently remove karein
    try:
        print("Removing conflicting Webhooks...")
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
