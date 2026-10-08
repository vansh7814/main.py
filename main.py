import json
import os
import time
import re
import threading
from flask import Flask, request, jsonify
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

ADMIN_BOT_TOKEN = "8351462114:AAFOUc8Mr3K1SYezCp1_2-6kXomE4Vk0ZQs"
ALLOWED_ADMIN_ID = 5831204930

bot = telebot.TeleBot(ADMIN_BOT_TOKEN)
app = Flask(__name__)

DEFAULT_END_DAY_MSG = "⏸️ Abhi din shuru nahi hua bhidu, thoda ruk — admin start karega tabhi kaam milega."
CLEAN_7H_MSG = "ajj ka din khatm bhidu, kal admin start karega tabhi kaam milega."

DATA = {
    "chat_id": ALLOWED_ADMIN_ID,
    "msg_id": None,
    "see_data_msg_id": None,
    "clean_rdp_triggered": False,
    "clean_7h_until": 0,           # 7 Hours timer track karne ke liye
    "day_started": False,
    "block_message": DEFAULT_END_DAY_MSG,
    "day_token": str(int(time.time())),
    "paused_workers": set(),
    "workers": {
        "vansh": {
            "mode": "Offline 🔴",
            "last_seen_watcher": 0,
            "data_type": None,
            "allotted": None,
            "taken": 0,
            "used_json": 0,
            "done": 0,
            "login_failed": 0,
            "wrong_pass": 0,
            "manage": 0
        }
    }
}

SELECTIONS = {}
ADMIN_STATE = {}
TEMP_CUSTOM_MSG = {}
CUSTOM_PROMPT_MSG = {}
edit_lock = threading.Lock()

def auto_correct_text(text):
    text = text.strip()
    corrections = {
        r"\bdim\b": "din",
        r"\bkam\b": "kaam",
        r"\bshru\b": "shuru",
        r"\bsart\b": "start",
        r"\bstrt\b": "start",
        r"\bcancle\b": "cancel",
        r"\badminn\b": "admin",
        r"\bwrk\b": "work",
        r"\bbhiddu\b": "bhidu",
        r"\bmesaage\b": "message",
        r"\bmsg\b": "message",
        r"\bplz\b": "please",
        r"\btym\b": "time",
        r"\bwaitng\b": "waiting",
        r"\bofflinee\b": "offline",
        r"\bonn\b": "on",
        r"\bofff\b": "off"
    }
    for pattern, repl in corrections.items():
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    return text

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
    markup.row(KeyboardButton("▶️ Start. Work"), KeyboardButton("⏸️ End Day"))
    markup.row(KeyboardButton("🔎 See Worker. Data"))
    markup.row(KeyboardButton("🟢 Online"), KeyboardButton("🔴 Offline"))
    markup.row(KeyboardButton("⏸️ Cont. Work"), KeyboardButton("▶️ Pause Work"))
    markup.row(KeyboardButton("⏸️ End Day + 🧹 Clean RDP"))
    return markup

def format_all_workers_card():
    cards = []
    for worker_name, stats in DATA["workers"].items():
        data_type = stats.get("data_type")
        allotted = stats.get("allotted")

        if data_type and allotted is not None:
            allotted_line = f"📦 <b>{data_type} allotted:</b> {allotted}"
        else:
            allotted_line = "📦 <b>No Data Prov.</b>"

        taken = stats.get("taken", 0)
        used_json = stats.get("used_json", 0)
        done = stats.get("done", 0)
        failed = stats.get("login_failed", 0)
        wrong = stats.get("wrong_pass", 0)
        manage = stats.get("manage", 0)
        status_mode = stats.get('mode', 'Offline 🔴')
        day_text = "🟢 STARTED" if DATA.get("day_started") else "⏸️ NOT STARTED"

        card = (
            f"📊 <b>Live Monitor — {worker_name.upper()}</b>\n\n"
            f"🌐 <b>Network:</b> {status_mode} | <b>Email Day:</b> {day_text}\n"
            f"{allotted_line}\n"
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
            DATA["msg_id"] = None

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

def get_online_workers():
    current_time = time.time()
    online = []
    for w, stats in DATA["workers"].items():
        if stats.get("mode") == "Online 🟢" and (current_time - stats.get("last_seen_watcher", 0) <= 20):
            online.append(w)
    return online

def build_worker_selection_markup(action_type, selected_workers):
    markup = InlineKeyboardMarkup()
    online_workers = get_online_workers()

    for w_name in online_workers:
        is_checked = w_name in selected_workers
        box = "☑️" if is_checked else "⬜"
        state_icon = "⏸️" if w_name in DATA["paused_workers"] else "🟢"
        btn_text = f"{box} {state_icon} {w_name.upper()}"
        callback_data = f"toggle:{action_type}:{w_name}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=callback_data))

    if action_type == "stop":
        markup.row(
            InlineKeyboardButton("🔴 All Pause", callback_data="exec:stop:all"),
            InlineKeyboardButton("🔴 Sel. Pause", callback_data="exec:stop:sel")
        )
    else:
        markup.row(
            InlineKeyboardButton("▶️ All Cont.", callback_data="exec:cont:all"),
            InlineKeyboardButton("▶️ Sel. Cont.", callback_data="exec:cont:sel")
        )
    return markup

def auto_delete_after_7s(chat_id, message_id):
    time.sleep(7)
    try:
        bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

def delayed_shorten_default_msg(chat_id, message_id):
    time.sleep(10)
    try:
        bot.edit_message_text(
            "⏸️ <b>DIN END KAR DIYA GAYA HAI!</b>",
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="HTML"
        )
    except Exception:
        pass

# ACTIVE BLOCK MESSAGE CALCULATION (7 Hours Check)
def get_current_block_message():
    current_time = time.time()
    if DATA.get("clean_7h_until", 0) > current_time:
        return CLEAN_7H_MSG
    return DATA.get("block_message", DEFAULT_END_DAY_MSG)

@app.route('/')
def home():
    return "Admin & Watcher Central API Active!"

# Email Bot is API ko call karega
@app.route('/check_day', methods=['GET', 'POST'])
def check_day():
    req_data = request.args if request.method == 'GET' else (request.json or {})
    raw_worker = req_data.get("user_id") or req_data.get("worker_name") or "vansh"
    worker = normalize_worker_name(raw_worker)

    is_day_started = DATA.get("day_started", False)
    active_msg = get_current_block_message()

    return jsonify({
        "day_started": is_day_started,
        "clean_rdp": DATA.get("clean_rdp_triggered", False),
        "block_message": active_msg
    }), 200

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
            "mode": "Offline 🔴",
            "last_seen_watcher": 0,
            "data_type": None,
            "allotted": None,
            "taken": 0,
            "used_json": 0,
            "done": 0,
            "login_failed": 0,
            "wrong_pass": 0,
            "manage": 0
        }

    incoming_data_type = req_data.get("data_type")
    if incoming_data_type:
        DATA["workers"][worker]["data_type"] = incoming_data_type

    events_list = req_data.get("events", [])
    if isinstance(events_list, list) and events_list:
        for ev in events_list:
            ev_type = ev.get("type", "")
            if ev_type == "emailused":
                DATA["workers"][worker]["used_json"] += 1
            elif ev_type == "done":
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

@app.route('/poll', methods=['POST'])
def handle_poll():
    req_data = request.json or {}
    raw_worker = req_data.get("user_id") or "vansh"
    worker = normalize_worker_name(raw_worker)

    if worker not in DATA["workers"]:
        DATA["workers"][worker] = {
            "mode": "Offline 🔴",
            "last_seen_watcher": 0,
            "data_type": None,
            "allotted": None,
            "taken": 0,
            "used_json": 0,
            "done": 0,
            "login_failed": 0,
            "wrong_pass": 0,
            "manage": 0
        }

    DATA["workers"][worker]["mode"] = "Online 🟢"
    DATA["workers"][worker]["last_seen_watcher"] = time.time()

    do_clean = DATA.get("clean_rdp_triggered", False)
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
        "day_token": DATA.get("day_token"),
        "day_started": DATA.get("day_started", False),
        "bm2_change": None
    }), 200

def heartbeat_check_loop():
    while True:
        try:
            current_time = time.time()
            changed = False
            for worker, stats in DATA["workers"].items():
                if stats["mode"] == "Online 🟢" and (current_time - stats.get("last_seen_watcher", 0) > 20):
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
        "⌨️ Menu Open",
        reply_markup=get_admin_keyboard()
    )

@bot.message_handler(func=lambda msg: True)
def handle_menu_actions(message):
    if not is_authorized(message):
        return

    text = message.text.strip()
    text_lower = text.lower()
    chat_id = message.chat.id

    if ADMIN_STATE.get(chat_id) == "WAITING_FOR_CUSTOM_MSG":
        ADMIN_STATE[chat_id] = None
        CUSTOM_PROMPT_MSG[f"{chat_id}_user_input"] = message.message_id
        
        corrected = auto_correct_text(text)
        TEMP_CUSTOM_MSG[chat_id] = corrected

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✅ Haan, Bhejo", callback_data="confirm_custom:yes"),
            InlineKeyboardButton("❌ Cancel", callback_data="confirm_custom:no")
        )
        conf_msg = bot.send_message(
            chat_id,
            f"❓ <b>Kya yahi custom message set karna hai?</b>\n\n"
            f"<i>\"{corrected}\"</i>\n\n"
            f"(Spelling check kar li gayi hai)",
            parse_mode="HTML",
            reply_markup=markup
        )
        CUSTOM_PROMPT_MSG[f"{chat_id}_confirm_msg"] = conf_msg.message_id
        return

    # 1. STATUS
    if "status" in text_lower:
        recreate_single_card(chat_id)

    # 2. START. WORK
    elif "start. work" in text_lower or text_lower == "▶️ start. work":
        if DATA.get("day_started", False):
            warn_msg = bot.send_message(chat_id, "⚠️ <b>Aap na  Kaam already start kar diya hai!</b>", parse_mode="HTML")
            threading.Thread(target=
