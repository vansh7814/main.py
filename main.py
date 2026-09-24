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
# Structure: { "Worker1": {"created": 0, "done": 0, "login_failed": 0, "wrong_pass": 0, "manage": 0, "last_seen": timestamp} }
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
    # Agar pichhle 60 seconds mein signal aaya hai to Online, nahi to Offline
    if worker_name not in workers_stats:
        return "🔴 Offline (Watcher OFF)"
    last_seen = workers_stats[worker_name].get("last_seen", 0)
    if time.time() - last_seen <= 65:
        return "🟢 Active (Watcher ON)"
    return "🔴 Inactive (Watcher OFF)"

@app.route('/', methods=['GET'])
def home():
    return "Admin & Worker Control API is Live!"

# ==========================================
# 1. WORKER HEARTBEAT / PING ENDPOINT
# ==========================================
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

# ==========================================
# 2. WORKER LIVE EVENTS ENDPOINT
# ==========================================
@app.route('/event', methods=['POST'])
def handle_event():
    data = request.json or {}
    
    event_type = data.get('event', '')
    email = data.get('email', 'Unknown')
    worker = data.get('worker_name', 'Worker1')
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

    # Format exactly as requested
    msg = (
        f"⚡ <b>WORKER EVENT UPDATE</b>\n"
        f"👤 <b>Worker:</b> <code>{worker}</code>\n"
        f"📡 <b>Watcher Status:</b> {watcher_status}\n"
        f"📧 <b>Email:</b> <code>{email}</code>\n"
        f"🏷️ <b>Status:</b> <code>{status.upper()}</code>\n\n"
        f"📊 <b>Stats for {worker}:</b>\n"
        f"✅ Done: <code>{stats['done']}</code> | ❌ Wrong Pass: <code>{stats['wrong_pass']}</code>\n"
        f"⚠️ Login Failed: <code>{stats['login_failed']}</code> | 🛠️ Manage: <code>{stats['manage']}</code>"
    )
    send_telegram_msg(ADMIN_CHAT_ID, msg)
    return jsonify({"status": "success"})

# ==========================================
# 3. TELEGRAM ADMIN WEBHOOK CONTROL
# ==========================================
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
            send_telegram_msg(chat_id, "⚠️ <b>System Active!</b> Abhi kisi worker ka data active nahi hai.")
            return jsonify({"status": "ok"})

        report = "📊 <b>ALL WORKERS LIVE REPORT</b>\n───────────────────\n\n"
        total_done = 0
        for w_name, s in workers_stats.items():
            w_status = get_watcher_status(w_name)
            report += (
                f"👤 <b>Worker:</b> <code>{w_name}</code>\n"
                f"📡 <b>Watcher:</b> {w_status}\n"
                f" ├ ✅ Files Done: <code>{s['done']}</code>\n"
                f" ├ ❌ Wrong Pass: <code>{s['wrong_pass']}</code>\n"
                f" ├ ⚠️ Login Failed: <code>{s['login_failed']}</code>\n"
                f" ├ 🛠️ Manage: <code>{s['manage']}</code>\n"
                f" └ 🆕 Total Created: <code>{s['created']}</code>\n\n"
            )
            total_done += s['done']

        report += f"───────────────────\n🏆 <b>OVERALL TOTAL DONE:</b> <code>{total_done}</code>"
        send_telegram_msg(chat_id, report)

    elif text == '/reset' or text == '/clean':
        workers_stats.clear()
        send_telegram_msg(chat_id, "🧹 <b>Sabhi workers ke stats clear (0) kar diye gaye hain.</b>")

    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
