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

DATA = {
    "chat_id": ALLOWED_ADMIN_ID,
    "msg_id": None,
    "see_data_msg_id": None,  # See worker data ke message tracking ke liye
    "clean_rdp_triggered": False,
    "day_started": False,
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
        day_text = "🟢 ACTIVE" if DATA.get("day_started") else "⏸️ STOPPED"

        card = (
            f"📊 <b>Live Monitor — {worker_name.upper()}</b>\n\n"
            f"🌐 <b>Network:</b> {status_mode} | <b>Day:</b> {day_text}\n"
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

@app.route('/')
def home():
    return "Admin & Watcher Central API Active!"

@app.route('/check_day', methods=['GET', 'POST'])
def check_day():
    req_data = request.args if request.method == 'GET' else (request.json or {})
    raw_worker = req_data.get("user_id") or req_data.get("worker_name") or "vansh"
    worker = normalize_worker_name(raw_worker)

    is_paused = (worker in DATA["paused_workers"])
    is_allowed = DATA.get("day_started", False) and not is_paused

    return jsonify({
        "day_started": DATA.get("day_started", False),
        "work_allowed": is_allowed,
        "clean_rdp": DATA.get("clean_rdp_triggered", False)
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
    is_paused = (worker in DATA["paused_workers"]) or not DATA.get("day_started", False)

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

    # 1. STATUS
    if "status" in text_lower:
        recreate_single_card(chat_id)

    # 2. START. WORK
    elif "start. work" in text_lower or text_lower == "▶️ start. work":
        DATA["day_started"] = True
        DATA["clean_rdp_triggered"] = False
        DATA["paused_workers"].clear()
        bot.send_message(
            chat_id,
            "▶️ <b>DIN SHURU HO GAYA HAI!</b>\n\nWorkers ab email bot use kar sakte hain, din shuru ho chuka hai.",
            parse_mode="HTML"
        )
        force_edit_only()

    # 3. END DAY + CLEAN RDP
    elif "clean rdp" in text_lower or "end day +" in text_lower or "end day+ clean rdp" in text_lower:
        DATA["day_started"] = False
        DATA["clean_rdp_triggered"] = True
        bot.send_message(
            chat_id,
            "🧹 <b>DIN END + RDP CLEAN SIGNAL SENT!</b>\n\nDin band kar diya gaya hai aur worker RDP clean ho jayegi.",
            parse_mode="HTML"
        )
        force_edit_only()

    # 4. END DAY (Normal)
    elif "end day" in text_lower:
        DATA["day_started"] = False
        bot.send_message(
            chat_id,
            "⏸️ <b>DIN END KAR DIYA GAYA HAI!</b>\n\nWorkers ke liye access stop kar diya gaya hai.",
            parse_mode="HTML"
        )
        force_edit_only()

    # 5. SEE WORKER. DATA (PURANA MESSAGE DELETE HOGA AGAR PEHLE SE HAI)
    elif "see worker. data" in text_lower or "see worker" in text_lower:
        # Purana data report delete karo agar pehle se bheja hua tha
        old_see_msg_id = DATA.get("see_data_msg_id")
        if old_see_msg_id:
            try:
                bot.delete_message(chat_id=chat_id, message_id=old_see_msg_id)
            except Exception:
                pass
            DATA["see_data_msg_id"] = None

        report_lines = ["🔎 <b>WORKER DATA & ASSIGNMENT REPORT:</b>\n"]
        for worker_name, stats in DATA["workers"].items():
            data_type = stats.get("data_type") or "Not Specified"
            allotted = stats.get("allotted") if stats.get("allotted") is not None else "N/A"
            taken = stats.get("taken", 0)
            used_json = stats.get("used_json", 0)
            done = stats.get("done", 0)
            failed = stats.get("login_failed", 0)
            wrong = stats.get("wrong_pass", 0)
            manage = stats.get("manage", 0)
            status_mode = stats.get("mode", "Offline 🔴")

            report_lines.append(
                f"👤 <b>Worker:</b> {worker_name.upper()} ({status_mode})\n"
                f"📁 <b>Current Working Data:</b> {data_type}\n"
                f"📦 <b>Allotted:</b> {allotted}\n"
                f"📥 <b>Taken:</b> {taken} | 📝 <b>Used Json:</b> {used_json}\n"
                f"✅ <b>Done:</b> {done} | ❌ <b>Failed:</b> {failed} | 🔑 <b>Wrong:</b> {wrong} | 🔧 <b>Manage:</b> {manage}\n"
                f"────────────────────"
            )

        sent = bot.send_message(chat_id, "\n".join(report_lines), parse_mode="HTML")
        DATA["see_data_msg_id"] = sent.message_id

    # 6. ONLINE
    elif "online" in text_lower:
        online_list = [w.upper() for w in get_online_workers()]
        if online_list:
            msg = "<b>🟢 ONLINE WORKERS:</b>\n\n" + "\n".join([f"🟢 {w}" for w in online_list])
        else:
            msg = "⚠️ <b>Filhal koi worker online nahi hai!</b>"
        bot.send_message(chat_id, msg, parse_mode="HTML")

    # 7. OFFLINE
    elif "offline" in text_lower:
        online_set = set(get_online_workers())
        offline_list = [w.upper() for w in DATA["workers"].keys() if w not in online_set]
        if offline_list:
            msg = "<b>🔴 OFFLINE WORKERS:</b>\n\n" + "\n".join([f"🔴 {w}" for w in offline_list])
        else:
            msg = "✅ <b>Sabhi workers online hain!</b>"
        bot.send_message(chat_id, msg, parse_mode="HTML")

    # 8. CONT. WORK
    elif "cont. work" in text_lower or "cont" in text_lower:
        online_workers = get_online_workers()
        if not online_workers:
            bot.send_message(
                chat_id,
                "⚠️ <b>Filhal koi worker online nahi hai!</b>\nWorker offline hai toh kiska kaam continue karoge?",
                parse_mode="HTML"
            )
            return

        SELECTIONS[chat_id] = set()
        markup = build_worker_selection_markup("cont", SELECTIONS[chat_id])
        bot.send_message(chat_id, "▶️ <b>Kiska kaam resume karna hai select karein:</b>", parse_mode="HTML", reply_markup=markup)

    # 9. PAUSE WORK
    elif "pause work" in text_lower or "pause" in text_lower:
        online_workers = get_online_workers()
        if not online_workers:
            bot.send_message(
                chat_id,
                "⚠️ <b>Filhal koi worker online nahi hai!</b>\nWorker offline hai toh kiska kaam pause karoge?",
                parse_mode="HTML"
            )
            return

        SELECTIONS[chat_id] = set()
        markup = build_worker_selection_markup("stop", SELECTIONS[chat_id])
        bot.send_message(chat_id, "⏸️ <b>Kiska kaam pause karna hai select karein:</b>", parse_mode="HTML", reply_markup=markup)

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
        online_workers = get_online_workers()

        if action_type == "stop":
            if target == "all":
                for w in online_workers:
                    DATA["paused_workers"].add(w)
                bot.edit_message_text("⏸️ <b>Sabhi ONLINE workers ka kaam PAUSE kar diya gaya hai!</b>", chat_id, call.message.message_id, parse_mode="HTML")
            elif target == "sel":
                selected = SELECTIONS.get(chat_id, set())
                if not selected:
                    bot.answer_callback_query(call.id, "⚠️ Pehle kisi worker ko select karein!", show_alert=True)
                    return
                for w in selected:
                    DATA["paused_workers"].add(w)
                names = ", ".join([s.upper() for s in selected])
                bot.edit_message_text(f"⏸️ <b>In workers ka kaam PAUSE kar diya gaya hai:</b>\n{names}", chat_id, call.message.message_id, parse_mode="HTML")

        elif action_type == "cont":
            if target == "all":
                for w in online_workers:
                    DATA["paused_workers"].discard(w)
                bot.edit_message_text("▶️ <b>Sabhi ONLINE workers ka kaam RESUME kar diya gaya hai!</b>", chat_id, call.message.message_id, parse_mode="HTML")
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
