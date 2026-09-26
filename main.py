import os
import json
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "8351462114:AAER7HhrRJcYnvAj19CedKIkRK3ezuwvM-s"
ADMIN_CHAT_ID = "5831204930"

# In-Memory Storage
workers_stats = {}
worker_messages = {}

# Session selections for Checklist
# Structure: { "admin_chat_id": { "action": "clean|stop", "selected": set() } }
admin_selections = {}

def send_telegram_msg(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        res = requests.post(url, json=payload, timeout=5).json()
        return res.get("result", {}).get("message_id")
    except Exception as e:
        print(f"Telegram Send Error: {e}")
        return None

def edit_telegram_msg(chat_id, message_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": str(chat_id),
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram Edit Error: {e}")

def is_worker_online(worker_name):
    if worker_name not in workers_stats:
        return False
    last_seen = workers_stats[worker_name].get("last_seen", 0)
    return (time.time() - last_seen <= 65)

def get_watcher_status(worker_name):
    return "Watcher ON" if is_worker_online(worker_name) else "Watcher OFF"

def build_message(worker, stats):
    watcher_status = get_watcher_status(worker)
    user_id = stats.get('user_id', 'N/A')
    done = stats.get('done', 0)
    wrong_pass = stats.get('wrong_pass', 0)
    login_failed = stats.get('login_failed', 0)
    manage = stats.get('manage', 0)
    total_assigned = stats.get('total_assigned', 0)
    taken = stats.get('taken', 0)
    json_used = done + wrong_pass + login_failed + manage

    id_part = f" (ID: {user_id})" if user_id != 'N/A' else ""
    return (
        f"<b>Stats for {worker}{id_part} |📦 X-Data {done}/{total_assigned}</b>\n"
        f"<b>Status :</b> <code>{watcher_status}</code>\n\n"
        f"✅ <b>json used : {json_used}</b> | 📧<b>{taken} taken</b> | ❌ <b>Wrong Pass:</b> {wrong_pass} | ⚠️ <b>Login Failed:</b> {login_failed} | 🛠️ <b>Manage:</b> {manage}"
    )

def generate_checklist_keyboard(action, selected_workers):
    online_workers = [w for w in workers_stats.keys() if is_worker_online(w)]
    keyboard = []
    
    for w in online_workers:
        mark = "☑️" if w in selected_workers else "☐"
        keyboard.append([{"text": f"{w} {mark}", "callback_data": f"toggle_{action}_{w}"}])

    if action == "clean":
        keyboard.append([
            {"text": "🧹 Clean ALL", "callback_data": "confirm_clean_all"},
            {"text": "🧹 Clean", "callback_data": "confirm_clean_sel"}
        ])
    elif action == "stop":
        keyboard.append([
            {"text": "🛑 ALL", "callback_data": "stop_all"},
            {"text": "🛑 Stop Work", "callback_data": "stop_sel"}
        ])

    return {"inline_keyboard": keyboard}

@app.route('/', methods=['GET'])
def home():
    return "Admin & Worker Control API is Live!"

@app.route('/ping', methods=['POST'])
def ping():
    data = request.json or {}
    worker = data.get('worker_name', 'vansh')
    user_id = data.get('user_id', 'N/A')

    if worker not in workers_stats:
        workers_stats[worker] = {
            "user_id": user_id,
            "done": 0, "login_failed": 0, "wrong_pass": 0,
            "manage": 0, "taken": 0, "total_assigned": 0, "last_seen": time.time()
        }
    else:
        workers_stats[worker]["last_seen"] = time.time()
        if user_id != 'N/A':
            workers_stats[worker]["user_id"] = user_id

    return jsonify({"status": "pong"})

@app.route('/event', methods=['POST'])
def handle_event():
    data = request.json or {}
    event_type = data.get('event', '')
    worker = data.get('worker_name', 'vansh')
    user_id = data.get('user_id', None)
    status = data.get('status', 'done')
    
    total_assigned = data.get('total_assigned', None)
    taken_val = data.get('taken', None)

    if worker not in workers_stats:
        workers_stats[worker] = {
            "user_id": user_id if user_id else 'N/A',
            "done": 0, "login_failed": 0, "wrong_pass": 0,
            "manage": 0, "taken": 0, "total_assigned": 0, "last_seen": time.time()
        }

    stats = workers_stats[worker]
    stats["last_seen"] = time.time()

    if user_id:
        stats["user_id"] = user_id
    if total_assigned is not None:
        stats["total_assigned"] = total_assigned
    if taken_val is not None:
        stats["taken"] = taken_val

    if event_type == 'emailcreated':
        stats["taken"] += 1
    elif event_type == 'emailused':
        if status == 'login_failed':
            stats["login_failed"] += 1
        elif status == 'wrong_pass':
            stats["wrong_pass"] += 1
        elif status == 'manage':
            stats["manage"] += 1
        else:
            stats["done"] += 1

    msg = build_message(worker, stats)
    send_telegram_msg(ADMIN_CHAT_ID, msg)
    return jsonify({"status": "success"})

# ==========================================
# TELEGRAM BOT WEBHOOK (BUTTONS & CALLBACKS)
# ==========================================
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.json or {}
    
    # 1. HANDLE INLINE BUTTON CLICKS (CALLBACK QUERIES)
    if "callback_query" in update:
        query = update["callback_query"]
        cb_id = query["id"]
        chat_id = str(query["message"]["chat"]["id"])
        msg_id = query["message"]["message_id"]
        cb_data = query.get("data", "")

        # Acknowledge callback to stop loader
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cb_id})

        session = admin_selections.get(chat_id, {"action": "", "selected": set()})

        # CHECKBOX TOGGLE
        if cb_data.startswith("toggle_"):
            parts = cb_data.split("_")
            action = parts[1]
            worker_name = parts[2]
            
            if worker_name in session["selected"]:
                session["selected"].remove(worker_name)
            else:
                session["selected"].add(worker_name)

            session["action"] = action
            admin_selections[chat_id] = session
            kb = generate_checklist_keyboard(action, session["selected"])
            title = "<b>🧹 Clean RDP Workers Select Karein:</b>" if action == "clean" else "<b>🛑 Stop Work Workers Select Karein:</b>"
            edit_telegram_msg(chat_id, msg_id, title, kb)

        # CONFIRMATION PROMPT FOR CLEAN
        elif cb_data in ["confirm_clean_all", "confirm_clean_sel"]:
            if cb_data == "confirm_clean_all":
                session["selected"] = set([w for w in workers_stats.keys() if is_worker_online(w)])
            
            admin_selections[chat_id] = session
            confirm_kb = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Haan, sab reset kare", "callback_data": "exec_clean"},
                        {"text": "❌ Cancel", "callback_data": "cancel_clean"}
                    ]
                ]
            }
            edit_telegram_msg(chat_id, msg_id, "aaji sub clean kar raha hu", confirm_kb)

        # EXECUTE CLEAN
        elif cb_data == "exec_clean":
            edit_telegram_msg(chat_id, msg_id, "sub clean kar diya hai")
            admin_selections.pop(chat_id, None)

        # CANCEL CLEAN
        elif cb_data == "cancel_clean":
            edit_telegram_msg(chat_id, msg_id, "cancel kar diya hai kuch delete nhi hua")
            admin_selections.pop(chat_id, None)

        # EXECUTE STOP WORK
        elif cb_data in ["stop_all", "stop_sel"]:
            if cb_data == "stop_all":
                target_workers = [w for w in workers_stats.keys() if is_worker_online(w)]
            else:
                target_workers = list(session.get("selected", []))

            if target_workers:
                stopped_names = ", ".join(target_workers)
                edit_telegram_msg(chat_id, msg_id, f"in sabka work stop kar diya hai:\n<b>{stopped_names}</b>")
            else:
                edit_telegram_msg(chat_id, msg_id, "⚠️ Koi worker select nahi kiya gaya tha.")
            admin_selections.pop(chat_id, None)

        return jsonify({"status": "ok"})

    # 2. HANDLE TEXT MENU COMMANDS
    message = update.get('message', {})
    chat_id = str(message.get('chat', {}).get('id', ''))
    text = message.get('text', '').strip()

    if chat_id != str(ADMIN_CHAT_ID):
        return jsonify({"status": "unauthorized"})

    # MENU: 📊 Status
    if 'status' in text.lower() or text == '/stats':
        if not workers_stats:
            send_telegram_msg(chat_id, "⚠️ System Active! Abhi kisi worker ka data nahi hai.")
        else:
            for w_name, s in workers_stats.items():
                msg = build_message(w_name, s)
                send_telegram_msg(chat_id, msg)

    # MENU: 🟢 Online
    elif 'online' in text.lower():
        online_list = [f"{w_name} 🟢 Online" for w_name in workers_stats.keys() if is_worker_online(w_name)]
        if online_list:
            send_telegram_msg(chat_id, "\n".join(online_list))
        else:
            send_telegram_msg(chat_id, "⚠️ Abhi koi bhi worker online nahi hai.")

    # MENU: 🔴 Offline
    elif 'offline' in text.lower():
        offline_list = [f"{w_name} 🛑 offline" for w_name in workers_stats.keys() if not is_worker_online(w_name)]
        if offline_list:
            send_telegram_msg(chat_id, "\n".join(offline_list))
        else:
            send_telegram_msg(chat_id, "✅ Sabhi workers online hain!")

    # MENU: 🧹 Clear RDP
    elif 'clear rdp' in text.lower():
        admin_selections[chat_id] = {"action": "clean", "selected": set()}
        online_workers = [w for w in workers_stats.keys() if is_worker_online(w)]
        if not online_workers:
            send_telegram_msg(chat_id, "⚠️ Abhi koi online worker nahi hai jiska RDP clear kiya ja sake.")
        else:
            kb = generate_checklist_keyboard("clean", set())
            send_telegram_msg(chat_id, "<b>🧹 Clean RDP Workers Select Karein:</b>", kb)

    # MENU: 🛑 Stop Work
    elif 'stop work' in text.lower():
        admin_selections[chat_id] = {"action": "stop", "selected": set()}
        online_workers = [w for w in workers_stats.keys() if is_worker_online(w)]
        if not online_workers:
            send_telegram_msg(chat_id, "⚠️ Abhi koi online worker nahi hai jiska work stop kiya ja sake.")
        else:
            kb = generate_checklist_keyboard("stop", set())
            send_telegram_msg(chat_id, "<b>🛑 Stop Work Workers Select Karein:</b>", kb)

    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
