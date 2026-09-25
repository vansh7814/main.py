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
# Har worker ke live message ki ID track karne ke liye: { "vansh": 12345 }
worker_messages = {}

UPLOAD_FOLDER = 'worker_files'
REVERSE_FOLDER = 'reversed_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REVERSE_FOLDER, exist_ok=True)

def send_or_edit_telegram_msg(worker, text):
    msg_id = worker_messages.get(worker)

    if msg_id:
        # Puraane message ko edit karne ki koshish karein
        edit_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
        payload = {
            "chat_id": str(ADMIN_CHAT_ID),
            "message_id": msg_id,
            "text": text,
            "parse_mode": "HTML"
        }
        try:
            res = requests.post(edit_url, json=payload, timeout=5).json()
            if res.get("ok"):
                return
            # Agar edit fail ho jaye (message deleted ya puraana ho), toh fall back to send
        except Exception:
            pass

    # Agar purana message nahi hai ya edit fail hua, toh naya message bhejein
    send_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": str(ADMIN_CHAT_ID),
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(send_url, json=payload, timeout=5).json()
        if res.get("ok"):
            worker_messages[worker] = res["result"]["message_id"]
    except Exception as e:
        print(f"Telegram Notification Error: {e}")

def get_watcher_status(worker_name):
    if worker_name not in workers_stats:
        return "Watcher OFF"
    last_seen = workers_stats[worker_name].get("last_seen", 0)
    if time.time() - last_seen <= 65:
        return "Watcher ON"
    return "Watcher OFF"

def build_message(worker, stats):
    watcher_status = get_watcher_status(worker)
    done = stats.get('done', 0)
    wrong_pass = stats.get('wrong_pass', 0)
    login_failed = stats.get('login_failed', 0)
    manage = stats.get('manage', 0)
    total_assigned = stats.get('total_assigned', 0)
    taken = stats.get('taken', 0)
    
    json_used = done + wrong_pass + login_failed + manage

    return (
        f"<b>Stats for {worker} |📦 X-Data {done}/{total_assigned}</b>\n"
        f"<b>Status :</b> <code>{watcher_status}</code>\n\n"
        f"✅ <b>json used : {json_used}</b> | 📧<b>{taken} taken</b> | ❌ <b>Wrong Pass:</b> {wrong_pass} | ⚠️ <b>Login Failed:</b> {login_failed} | 🛠️ <b>Manage:</b> {manage}"
    )

@app.route('/', methods=['GET'])
def home():
    return "Admin & Worker Control API is Live!"

@app.route('/ping', methods=['POST'])
def ping():
    data = request.json or {}
    worker = data.get('worker_name', 'vansh')

    if worker not in workers_stats:
        workers_stats[worker] = {
            "done": 0, "login_failed": 0, "wrong_pass": 0,
            "manage": 0, "taken": 0, "total_assigned": 0, "last_seen": time.time()
        }
    else:
        workers_stats[worker]["last_seen"] = time.time()

    return jsonify({"status": "pong"})

@app.route('/event', methods=['POST'])
def handle_event():
    data = request.json or {}
    
    event_type = data.get('event', '')
    worker = data.get('worker_name', 'vansh')
    status = data.get('status', 'done')
    
    total_assigned = data.get('total_assigned', None)
    taken_val = data.get('taken', None)

    if worker not in workers_stats:
        workers_stats[worker] = {
            "done": 0, "login_failed": 0, "wrong_pass": 0,
            "manage": 0, "taken": 0, "total_assigned": 0, "last_seen": time.time()
        }

    stats = workers_stats[worker]
    stats["last_seen"] = time.time()

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
    send_or_edit_telegram_msg(worker, msg)
    return jsonify({"status": "success"})

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.json or {}
    message = update.get('message', {})
    chat_id = str(message.get('chat', {}).get('id', ''))
    text = message.get('text', '').strip()

    if chat_id != str(ADMIN_CHAT_ID):
        return jsonify({"status": "unauthorized"})

    if text in ['/stats', '/start']:
        if not workers_stats:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                "chat_id": chat_id,
                "text": "⚠️ System Active! Abhi kisi worker ka data nahi hai.",
                "parse_mode": "HTML"
            })
            return jsonify({"status": "ok"})

        for w_name, s in workers_stats.items():
            msg = build_message(w_name, s)
            send_or_edit_telegram_msg(w_name, msg)

    elif text in ['/reset', '/clean']:
        workers_stats.clear()
        worker_messages.clear()
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
            "chat_id": chat_id,
            "text": "🧹 Sabhi workers ke stats clear kar diye gaye hain.",
            "parse_mode": "HTML"
        })

    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
