import os
import json
import zipfile
import requests
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

# Telegram Bot Configurations
TELEGRAM_BOT_TOKEN = "8351462114:AAER7HhrRJcYnvAj19CedKIkRK3ezuwvM-s"
ADMIN_CHAT_ID = "8854743478"

# In-Memory Storage
workers_stats = {}

# Folder paths for pending files
UPLOAD_FOLDER = 'worker_files'
REVERSE_FOLDER = 'reversed_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REVERSE_FOLDER, exist_ok=True)

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
        res = requests.post(url, json=payload, timeout=5)
        print(f"Telegram API Status: {res.status_code}, Response: {res.text}")
    except Exception as e:
        print(f"Telegram Notification Error: {e}")

@app.route('/', methods=['GET'])
def home():
    return "Admin & Worker Control API is Live!"

# ==========================================
# 1. WORKER LIVE EVENTS ENDPOINT
# ==========================================
@app.route('/event', methods=['POST'])
def handle_event():
    data = request.json or {}
    
    event_type = data.get('event', '')          # emailcreated, emailused
    email = data.get('email', 'Unknown')
    worker = data.get('worker_name', 'Worker1')
    status = data.get('status', 'done')          # done, login_failed, wrong_pass, manage

    if worker not in workers_stats:
        workers_stats[worker] = {
            "created": 0, "done": 0, 
            "login_failed": 0, "wrong_pass": 0, "manage": 0
        }

    stats = workers_stats[worker]

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

    # Live Event Notification to Admin
    msg = (
        f"⚡ <b>WORKER EVENT UPDATE</b>\n"
        f"👤 <b>Worker:</b> <code>{worker}</code>\n"
        f"📧 <b>Email:</b> <code>{email}</code>\n"
        f"🏷️ <b>Status:</b> <code>{status.upper()}</code>\n\n"
        f"📊 <b>Stats for {worker}:</b>\n"
        f"✅ Done: <code>{stats['done']}</code> | ❌ Wrong Pass: <code>{stats['wrong_pass']}</code>\n"
        f"⚠️ Login Failed: <code>{stats['login_failed']}</code> | 🛠️ Manage: <code>{stats['manage']}</code>"
    )
    send_telegram_msg(ADMIN_CHAT_ID, msg)
    return jsonify({"status": "success"})

# ==========================================
# 2. FILE ALLOCATION & REVERSE ENDPOINTS
# ==========================================

@app.route('/get-files/<worker_name>', methods=['GET'])
def get_files(worker_name):
    worker_dir = os.path.join(UPLOAD_FOLDER, worker_name)
    if not os.path.exists(worker_dir):
        return jsonify({"files": []})
    
    files = [f for f in os.listdir(worker_dir) if f.endswith('.json')]
    file_data = []
    for f in files:
        file_path = os.path.join(worker_dir, f)
        with open(file_path, 'r', encoding='utf-8') as fname:
            try:
                file_data.append({"filename": f, "content": json.load(fname)})
            except:
                pass
        os.remove(file_path)
        
    return jsonify({"files": file_data})

@app.route('/reverse-files', methods=['POST'])
def receive_reverse_files():
    data = request.json or {}
    worker = data.get('worker_name', 'Unknown')
    returned_files = data.get('files', [])

    count = len(returned_files)
    msg = f"🔄 <b>REVERSE FILES RECEIVED</b>\n👤 <b>Worker:</b> <code>{worker}</code>\n📁 <b>Files Returned:</b> <code>{count}</code>"
    send_telegram_msg(ADMIN_CHAT_ID, msg)
    
    return jsonify({"status": "success", "received": count})

# ==========================================
# 3. TELEGRAM ADMIN WEBHOOK CONTROL
# ==========================================
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.json or {}
    message = update.get('message', {})
    chat_id = str(message.get('chat', {}).get('id', ''))
    text = message.get('text', '').strip()

    print(f"Received Message from Chat ID: {chat_id}, Text: {text}")

    if chat_id != str(ADMIN_CHAT_ID):
        print(f"Unauthorized access attempt by Chat ID: {chat_id}")
        return jsonify({"status": "unauthorized"})

    # Command: /stats or /start
    if text in ['/stats', '/start']:
        if not workers_stats:
            send_telegram_msg(chat_id, "⚠️ <b>System Active!</b> Abhi kisi worker ka data active nahi hai.")
            return jsonify({"status": "ok"})

        report = "📊 <b>ALL WORKERS LIVE REPORT</b>\n───────────────────\n\n"
        total_done = 0
        for w_name, s in workers_stats.items():
            report += (
                f"👤 <b>Worker:</b> <code>{w_name}</code>\n"
                f" ├ ✅ Files Done: <code>{s['done']}</code>\n"
                f" ├ ❌ Wrong Pass: <code>{s['wrong_pass']}</code>\n"
                f" ├ ⚠️ Login Failed: <code>{s['login_failed']}</code>\n"
                f" ├ 🛠️ Manage: <code>{s['manage']}</code>\n"
                f" └ 🆕 Total Created: <code>{s['created']}</code>\n\n"
            )
            total_done += s['done']

        report += f"───────────────────\n🏆 <b>OVERALL TOTAL DONE:</b> <code>{total_done}</code>"
        send_telegram_msg(chat_id, report)

    # Command: /reset
    elif text == '/reset':
        workers_stats.clear()
        send_telegram_msg(chat_id, "🧹 <b>Sabhi workers ke stats clear (0) kar diye gaye hain.</b>")

    # Command: /help
    elif text == '/help':
        help_msg = (
            "👑 <b>ADMIN CONTROL MENU</b>\n\n"
            "🔹 <code>/stats</code> - Live worker metrics dekhein\n"
            "🔹 <code>/reset</code> - Daily stats clear karein\n"
            "🔹 <code>/send &lt;worker&gt; &lt;count&gt;</code> - Files assign karein\n"
            "🔹 <code>/reverse &lt;worker&gt;</code> - Worker se bachi files wapas lein"
        )
        send_telegram_msg(chat_id, help_msg)

    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
