import os
import json
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Telegram Configurations
TELEGRAM_BOT_TOKEN = "8351462114:AAER7HhrRJcYnvAj19CedKIkRK3ezuwvM-s"
ADMIN_CHAT_ID = "8854743478"

# In-Memory Storage
workers_stats = {}

UPLOAD_FOLDER = 'worker_files'
REVERSE_FOLDER = 'reversed_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REVERSE_FOLDER, exist_ok=True)

def send_telegram_msg(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram Notification Error: {e}")

def get_watcher_status(worker_name):
    if worker_name not in workers_stats:
        return "Watcher OFF"
    last_seen = workers_stats[worker_name].get("last_seen", 0)
    # Agar 65 seconds ke andar ping aaya hai to ON, nahi to OFF
    if time.time() - last_seen <= 65:
        return "Watcher ON"
    return "Watcher OFF"

@app.route('/', methods=['GET'])
def home():
    return "Admin & Worker Control API is Live!"

# Heartbeat Ping endpoint
@app.route('/ping', methods=['POST'])
def ping():
    data = request.json or {}
    worker = data.get('worker_name', 'Worker1')

    if worker not in workers_stats:
        workers_stats[worker] = {
            "created": 0, "done": 0,
            "login_failed": 0, "wrong_pass": 0, "manage": 0,
            "last_seen": time.time()
        }
    else:
        workers_stats[worker]["last_seen"] = time.time()

    return jsonify({"status": "pong"})

# Event update handler
@app.route('/event', methods=['POST'])
def handle_event():
    data = request.json or {}
    
    event_type = data.get('event', '')
    worker = data.get('worker_name', 'vansh')
    status = data.get('status', 'done')

    if worker not in workers_stats:
        workers_stats[worker] = {
            "created": 0, "done": 0, 
            "login_failed": 0, "wrong_pass": 0, "manage": 0,
            "last_seen": time.time()
        }

    stats = workers_stats[worker]
    stats["last_seen"] = time.time()

    if event_type == 'emailcreated':
        stats["created"] += 1
    elif event_type == 'emailused':
        if status == 'login_failed':
            stats["login_failed"] += 1
        elif status == 'wrong_pass':
            stats["wrong_pass"] += 1
        elif status == 'manage':
            stats["manage"] += 1
        else:
            stats["done"] += 1

    watcher_status = get_watcher_status(worker)

    # Aapke format ke hisab se simple message
    msg = (
        f"<b>Stats for {worker}</b>\n"
        f"<b>Status :</b> <code>{watcher_status}</code>\n\n"
        f"✅ <b>Done:</b> {stats['done']} | ❌ <b>Wrong Pass:</b> {stats['wrong_pass']} | ⚠️ <b>Login Failed:</b> {stats['login_failed']} | 🛠️ <b>Manage:</b> {stats['manage']}"
    )
    send_telegram_msg(ADMIN_CHAT_ID, msg)
    return jsonify({"status": "success"})

# Telegram Webhook endpoint (/stats, /reset)
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
            send_telegram_msg(chat_id, "⚠️ System Active! Abhi kisi worker ka data nahi hai.")
            return jsonify({"status": "ok"})

        report = ""
        for w_name, s in workers_stats.items():
            w_status = get_watcher_status(w_name)
            report += (
                f"<b>Stats for {w_name}</b>\n"
                f"<b>Status :</b> <code>{w_status}</code>\n"
                f"Done: {s['done']} | Wrong Pass: {s['wrong_pass']} | Login Failed: {s['login_failed']} | Manage: {s['manage']}\n\n"
            )
        send_telegram_msg(chat_id, report.strip())

    elif text in ['/reset', '/clean']:
        workers_stats.clear()
        send_telegram_msg(chat_id, "🧹 Sabhi workers ke stats clear (0) kar diye gaye hain.")

    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
