import json
import os
import time
import threading
from flask import Flask, request, jsonify
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

ADMIN_BOT_TOKEN = "8351462114:AAFOUc8Mr3K1SYezCp1_2-6kXomE4Vk0ZQs"
ALLOWED_ADMIN_ID = 5831204930

bot = telebot.TeleBot(ADMIN_BOT_TOKEN)
app = Flask(__name__)

# State data: used_json ko independent rakha hai jo sirf watcher badhayega
DATA = {
    "chat_id": ALLOWED_ADMIN_ID,
    "msg_id": None,
    "clean_rdp_triggered": False,
    "paused_workers": set(),
    "workers": {
        "vansh": {
            "mode": "Offline 🔴",
            "last_seen": 0,
            "data_type": "X",
            "allotted": 0,
            "taken": 0,
            "used_json": 0,       # Sirf Watcher ke *_used.json aane par badhega
            "done": 0,
            "login_failed": 0,
            "wrong_pass": 0,
            "manage": 0
        }
    }
}

SELECTIONS = {}
edit_lock = threading.Lock()

def normalize_worker_name(raw_name):
    if not raw_name:
        return "vansh"
    name_str = str(raw_name).strip().lower()
    if name_str in ["8854743478", "vansh", "administrator", "default"]:
        return "vansh"
    return name_str

def is_authorized(message_or_call):
    user_id = message_or_call.from_user.id
    if user_id != ALLOWED_ADMIN_ID:
        try:
            if hasattr(message_or_call, 'message'):
                bot.answer_callback_query(message_or_call.id, "🚫 Access Denied", show_alert=True)
            else:
                bot.send_message(message_or_call.chat.id, "🚫 <b>Access Denied:</b> Not authorized.", parse_mode="HTML")
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
        used_json = stats.get("used_json", 0)  # Watcher se calculated
        done = stats.get("done", 0)
        failed = stats.get("login_failed", 0)
        wrong = stats.get("wrong_pass", 0)
        manage = stats.get("manage", 0)
        status_mode = stats.get('mode', 'Offline 🔴')

        card = (
            f"📊 <b>Live Monitor — {worker_name.upper()}</b>\n\n"
            f"🌐 <b>Network:</b> {status_mode}\n"
            f"📦 <b>{data_type} allotted:</b> {allotted}\n"
            f"────────────────────\n"
            f"📥 <b>Taken:</b> {taken}\n"
            f"📝 <b>Used Json:</b> {used_json}\n"
            f"✅ <b>Done:</b> {done}\n"
            f"❌ <b>Login Failed:</b> {failed}\n"
            f"🔑 <b>Wrong Pass:</b> {wrong}\n"
            f"🔧 <b>Manage:</b> {manage}"
        )
        cards.append(card)

    return "\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(cards) if cards else "⚠️ <b>Koi worker add nahi hai.</b>"

def force_edit_only():
    with edit_lock:
        chat_id = DATA.get("chat_id")
        msg_id = DATA.get("msg_id")

        if not chat_id or not msg_id:
            return

        text = format_all_workers_card()
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="HTML")
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" in str(e).lower():
                return
            if "message to edit not found" in str(e).lower():
                DATA["msg_id"] = None
        except Exception:
            pass

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

def build_worker_selection_markup(action_type, selected_workers):
    markup = InlineKeyboardMarkup()
    for w_name in DATA["workers"].keys():
        is_checked = w_name in selected_workers
        box = "☑️" if is_checked else "⬜"
        btn_text = f"{box} {w_name.upper()}"
        callback_data = f"toggle:{action_type}:{w_name}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=callback_data))

    if action_type == "stop":
        markup.row(
            InlineKeyboardButton("🛑 All Stop", callback_data="exec:stop:all"),
            InlineKeyboardButton("🛑 Sel. Stop", callback_data="exec:stop:sel")
        )
    else:
        markup.row(
            InlineKeyboardButton("▶️ All Cont.", callback_data="exec:cont:all"),
            InlineKeyboardButton("▶️ Sel. Cont.", callback_data="exec:cont:sel")
        )
    return markup

@app.route('/')
def home():
    return "Admin & Watcher Central API Active!"

# ══════════════════════════════════════════════════════
# EVENT HANDLER (Taken vs Used JSON logic separated)
# ══════════════════════════════════════════════════════
@app.route('/event', methods=['GET', 'POST'])
def handle_event():
    if request.method == 'GET':
        req_data = request.args.to_dict()
    else:
        req_data = request.json or {}

    raw_worker = req_data.get("user_id") or req_data.get("worker_name") or "vansh"
    worker = normalize_worker_name(raw_worker)

    if worker not in DATA["workers"]:
        DATA["workers"][worker] = {
            "mode": "Online 🟢",
            "last_seen": time.time(),
            "data_type": "X",
            "allotted": 0,
            "taken": 0,
            "used_json": 0,
            "done": 0,
            "login_failed": 0,
            "wrong_pass": 0,
            "manage": 0
        }

    DATA["workers"][worker]["mode"] = "Online 🟢"
    DATA["workers"][worker]["last_seen"] = time.time()

    # 1. Watcher Batch Event (Watcher se aane wala event)
    events_list = req_data.get("events", [])
    if isinstance(events_list, list) and events_list:
        for ev in events_list:
            ev_type = ev.get("type", "")
            # Watcher jab email_used.json detect karta hai to 'emailused' bhejta hai
            if ev_type == "emailused":
                DATA["workers"][worker]["used_json"] += 1
            # File jab processing ke baad done hoti hai
            elif ev_type == "done":
                DATA["workers"][worker]["done"] += 1
            # Agar watcher emailcreated bhej raha ho
            elif ev_type == "emailcreated":
                pass

    # 2. VisiHost Email Bot se single event
    else:
        ev_type = req_data.get("event", "")
        ev_status = req_data.get("status", "")
        
        # Email Bot se jab worker email take karega -> sirf Taken badhega
        if ev_type == "emailcreated":
            DATA["workers"][worker]["taken"] += 1
        
        # Email Bot ke result reports
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
    raw_worker = req_data.get("user_id") or "vansh"
    worker = normalize_worker_name(raw_worker)

    if worker not in DATA["workers"]:
        DATA["workers"][worker] = {
            "mode": "Online 🟢",
            "last_seen": time.time(),
            "data_type": "X",
            "allotted": 0,
            "taken": 0,
            "used_json": 0,
            "done": 0,
            "login_failed": 0,
            "wrong_pass": 0,
            "manage": 0
        }

    DATA["workers"][worker]["mode"] = "Online 🟢"
    DATA["workers"][worker]["last_seen"] = time.time()

    do_clean = DATA.get("clean_rdp_triggered", False)
    DATA["clean_rdp_triggered"] = False

    is_paused = (worker in DATA["paused_workers"])

    return jsonify({
        "deletes": [],
        "pending_filenames": [],
        "pending_downloads": [],
        "work_paused": is_paused,
        "clean_downloads": do_clean,
        "stop_watcher": False,
        "delete_done_files": True,
        "delete_used_json": False,
        "bm2_change": None
    }), 200

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

# --- Telegram Handlers ---

@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
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
    if not is_authorized(message):
        return

    text = message.text.strip()
    chat_id = message.chat.id

    if "Status" in text:
        recreate_single_card(chat_id)

    elif "🟢 Online" in text or text == "Online":
        online_list = [w.upper() for w, stats in DATA["workers"].items() if "Online" in stats.get("mode", "")]
        if online_list:
            msg = "<b>🟢 ONLINE WORKERS:</b>\n\n" + "\n".join([f"🟢 {w}" for w in online_list])
        else:
            msg = "⚠️ <b>Filhal koi worker online nahi hai!</b>"
        bot.send_message(chat_id, msg, parse_mode="HTML")

    elif "🔴 Offline" in text or text == "Offline":
        offline_list = [w.upper() for w, stats in DATA["workers"].items() if "Offline" in stats.get("mode", "")]
        if offline_list:
            msg = "<b>🔴 OFFLINE WORKERS:</b>\n\n" + "\n".join([f"🔴 {w}" for w in offline_list])
        else:
            msg = "✅ <b>Sabhi workers online hain!</b>"
        bot.send_message(chat_id, msg, parse_mode="HTML")

    elif "Stop Work" in text:
        SELECTIONS[chat_id] = set()
        markup = build_worker_selection_markup("stop", SELECTIONS[chat_id])
        bot.send_message(chat_id, "🛑 <b>Kiska kaam rokna hai select karein:</b>", parse_mode="HTML", reply_markup=markup)

    elif "Cont. Work" in text:
        SELECTIONS[chat_id] = set()
        markup = build_worker_selection_markup("cont", SELECTIONS[chat_id])
        bot.send_message(chat_id, "▶️ <b>Kiska kaam resume karna hai select karein:</b>", parse_mode="HTML", reply_markup=markup)

    elif "Clean RDP" in text:
        DATA["clean_rdp_triggered"] = True
        bot.send_message(chat_id, "🧹 <b>Clean Signal Sent:</b> RDP clean will run within 5 seconds on all active watchers.", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if not is_authorized(call):
        return

    chat_id = call.message.chat.id
    data_parts = call.data.split(":")
    cmd = data_parts[0]

    if chat_id not in SELECTIONS:
        SELECTIONS[chat_id] = set()

    if cmd == "toggle":
        action_type = data_parts[1]
        worker_name = data_parts[2]

        if worker_name in SELECTIONS[chat_id]:
            SELECTIONS[chat_id].remove(worker_name)
        else:
            SELECTIONS[chat_id].add(worker_name)

        new_markup = build_worker_selection_markup(action_type, SELECTIONS[chat_id])
        try:
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=new_markup)
        except Exception:
            pass
        bot.answer_callback_query(call.id)

    elif cmd == "exec":
        action_type = data_parts[1]
        target = data_parts[2]

        if action_type == "stop":
            if target == "all":
                for w in DATA["workers"].keys():
                    DATA["paused_workers"].add(w)
                bot.edit_message_text("🛑 <b>Sabhi workers ka kaam STOP kar diya gaya hai!</b>", chat_id, call.message.message_id, parse_mode="HTML")
            elif target == "sel":
                selected = SELECTIONS.get(chat_id, set())
                if not selected:
                    bot.answer_callback_query(call.id, "⚠️ Pehle kisi worker ko select karein!", show_alert=True)
                    return
                for w in selected:
                    DATA["paused_workers"].add(w)
                names = ", ".join([s.upper() for s in selected])
                bot.edit_message_text(f"🛑 <b>In workers ka kaam STOP kar diya gaya hai:</b>\n{names}", chat_id, call.message.message_id, parse_mode="HTML")

        elif action_type == "cont":
            if target == "all":
                DATA["paused_workers"].clear()
                bot.edit_message_text("▶️ <b>Sabhi workers ka kaam RESUME kar diya gaya hai!</b>", chat_id, call.message.message_id, parse_mode="HTML")
            elif target == "sel":
                selected = SELECTIONS.get(chat_id, set())
                if not selected:
                    bot.answer_callback_query(call.id, "⚠️ Pehle kisi worker ko select karein!", show_alert=True)
                    return
                for w in selected:
                    DATA["paused_workers"].discard(w)
                names = ", ".join([s.upper() for s in selected])
                bot.edit_message_text(f"▶️ <b>In workers ka kaam RESUME kar diya gaya hai:</b>\n{names}", chat_id, call.message.message_id, parse_mode="HTML")

        bot.answer_callback_query(call.id)

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
