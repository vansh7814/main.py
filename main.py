import json
import os
import time
import threading
from flask import Flask, request, jsonify
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

ADMIN_BOT_TOKEN = "8351462114:AAFOUc8Mr3K1SYezCp1_2-6kXomE4Vk0ZQs"
# STRICT ADMIN LOCK: Sirf is ID ko access milega
ALLOWED_ADMIN_ID = 5831204930

bot = telebot.TeleBot(ADMIN_BOT_TOKEN)
app = Flask(__name__)

DATA = {
    "chat_id": ALLOWED_ADMIN_ID,
    "msg_id": None,
    "clean_rdp_triggered": False,
    "work_paused": False,
    "workers": {
        "vansh": {
            "mode": "Offline 🔴",
            "last_seen": 0,
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

edit_lock = threading.Lock()

def is_authorized(message):
    """Check karta hai ki message sirf aapke account se aaya hai ya nahi."""
    user_id = message.from_user.id
    if user_id != ALLOWED_ADMIN_ID:
        try:
            bot.send_message(
                message.chat.id,
                "🚫 <b>Access Denied:</b> Aap is bot ke admin nahi hain.",
                parse_mode="HTML"
            )
        except Exception:
            pass
        return False
    return True

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
            f"🌐 <b>Network:</b> {stats.get('mode', 'Offline 🔴')}\n"
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
    with edit_lock:
        chat_id = DATA.get("chat_id")
        msg_id = DATA.get("msg_id")

        if not chat_id:
            return

        text = format_all_workers_card()

        if msg_id:
            try:
                bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
                return
            except Exception as e:
                if "message is not modified" in str(e).lower():
                    return
                print(f"Edit warning: {e}")

        try:
            sent = bot.send_message(
                chat_id,
                text,
                parse_mode="HTML",
                reply_markup=get_admin_keyboard(),
                disable_notification=True
            )
            DATA["msg_id"] = sent.message_id
        except Exception as e:
            print(f"Send card error: {e}")

def recreate_single_card(chat_id):
    with edit_lock:
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
            print(f"Recreate error: {e}")

@app.route('/')
def home():
    return "Admin & Watcher Central API Active!"

# ══════════════════════════════════════════════════════
# EVENT HANDLER (VisiHost & Watcher)
# ══════════════════════════════════════════════════════
@app.route('/event', methods=['GET', 'POST'])
def handle_event():
    if request.method == 'GET':
        req_data = request.args.to_dict()
    else:
        req_data = request.json or {}

    worker = str(req_data.get("user_id") or req_data.get("worker_name", "vansh")).lower()

    if worker not in DATA["workers"]:
        DATA["workers"][worker] = {
            "mode": "Online 🟢",
            "last_seen": time.time(),
            "data_type": "X",
            "allotted": 0,
            "taken": 0,
            "done": 0,
            "login_failed": 0,
            "wrong_pass": 0,
            "manage": 0
        }

    DATA["workers"][worker]["mode"] = "Online 🟢"
    DATA["workers"][worker]["last_seen"] = time.time()

    events_list = req_data.get("events", [])
    if isinstance(events_list, list) and events_list:
        for ev in events_list:
            ev_type = ev.get("type", "")
            if ev_type == "emailcreated":
                DATA["workers"][worker]["taken"] += 1
            elif ev_type in ["emailused", "done"]:
                DATA["workers"][worker]["done"] += 1
    else:
        ev_type = req_data.get("event", "")
        ev_status = req_data.get("status", "")
        if ev_type == "emailcreated":
            DATA["workers"][worker]["taken"] += 1
        elif ev_type == "emailused":
            if ev_status == "done":
                DATA["workers"][worker]["done"] += 1
            elif ev_status == "login_failed":
                DATA["workers"][worker]["login_failed"] += 1
            elif ev_status == "wrong_pass":
                DATA["workers"][worker]["wrong_pass"] += 1
            elif ev_status == "manage":
                DATA["workers"][worker]["manage"] += 1

    force_edit_only()
    return jsonify({"success": True}), 200

# ══════════════════════════════════════════════════════
# WATCHER POLL HANDLER
# ══════════════════════════════════════════════════════
@app.route('/poll', methods=['POST'])
def handle_poll():
    req_data = request.json or {}
    worker = str(req_data.get("user_id", "vansh")).lower()

    if worker in DATA["workers"]:
        DATA["workers"][worker]["mode"] = "Online 🟢"
        DATA["workers"][worker]["last_seen"] = time.time()

    do_clean = DATA.get("clean_rdp_triggered", False)
    DATA["clean_rdp_triggered"] = False

    return jsonify({
        "deletes": [],
        "pending_filenames": [],
        "pending_downloads": [],
        "work_paused": DATA.get("work_paused", False),
        "clean_downloads": do_clean,
        "stop_watcher": False,
        "delete_done_files": True,
        "delete_used_json": False,
        "bm2_change": None
    }), 200

# Watcher Heartbeat
def heartbeat_check_loop():
    while True:
        try:
            current_time = time.time()
            changed = False
            for worker, stats in DATA["workers"].items():
                if stats["mode"] == "Online 🟢" and (current_time - stats.get("last_seen", 0) > 25):
                    stats["mode"] = "Offline 🔴"
                    changed = True
            if changed:
                force_edit_only()
        except Exception:
            pass
        time.sleep(5)

# ══════════════════════════════════════════════════════
# SECURE TELEGRAM HANDLERS (ADMIN ONLY)
# ══════════════════════════════════════════════════════

@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    # Security check: Any non-admin is blocked
    if not is_authorized(message):
        return

    DATA["chat_id"] = message.chat.id
    bot.send_message(
        message.chat.id,
        "👋 <b>Welcome Admin!</b>\n\nNiche buttons se bot control karein.",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )

@bot.message_handler(func=lambda msg: True)
def handle_menu_actions(message):
    # Security check: Any non-admin is blocked
    if not is_authorized(message):
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
        DATA["work_paused"] = False
        bot.send_message(chat_id, "▶️ <b>Work Resumed:</b> Worker screen overlay removed.", parse_mode="HTML")
        force_edit_only()

    elif "Stop Work" in text:
        DATA["work_paused"] = True
        bot.send_message(chat_id, "🛑 <b>Stop Work Sent:</b> Fullscreen overlay will show on worker PC.", parse_mode="HTML")
        force_edit_only()

    elif "Clean RDP" in text:
        DATA["clean_rdp_triggered"] = True
        bot.send_message(chat_id, "🧹 <b>Clean Signal Sent:</b> RDP clean will run within 5 seconds.", parse_mode="HTML")

def start_polling():
    while True:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception:
            time.sleep(2)

if __name__ == '__main__':
    threading.Thread(target=heartbeat_check_loop, daemon=True).start()
    threading.Thread(target=start_polling, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
