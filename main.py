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
# Structure: { "Worker1": {"created": 0, "done": 0, "login_failed": 0, "wrong_pass": 0, "manage": 0} }
workers_stats = {}

# Folder paths for pending files
UPLOAD_FOLDER = 'worker_files'
REVERSE_FOLDER = 'reversed_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REVERSE_FOLDER, exist_ok=True)

def send_telegram_msg(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=payload, timeout=5)
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
        f"⚡ *WORKER EVENT UPDATE*\n"
        f"👤 *Worker:* `{worker}`\n"
        f"📧 *Email:* `{email}`\n"
        f"🏷️ *Status:* `{status.upper()}`\n\n"
        f"📊 *Stats for {worker}:*\n"
        f"✅ Done: `{stats['done']}` | ❌ Wrong Pass: `{stats['wrong_pass']}`\n"
        f"⚠️ Login Failed: `{stats['login_failed']}` | 🛠️ Manage: `{stats['manage']}`"
    )
    send_telegram_msg(ADMIN_CHAT_ID, msg)
    return jsonify({"status": "success"})

# ==========================================
# 2. FILE ALLOCATION & REVERSE ENDPOINTS
# ==========================================

# Worker calls this to fetch assigned pending files
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
        os.remove(file_path) # Move out once delivered
        
    return jsonify({"files": file_data})

# Worker calls this during "Reverse" action to send unprocessed files back
@app.route('/reverse-files', methods=['POST'])
def receive_reverse_files():
    data = request.json or {}
    worker = data.get('worker_name', 'Unknown')
    returned_files = data.get('files', []) # List of filenames/contents

    count = len(returned_files)
    msg = f"🔄 *REVERSE FILES RECEIVED*\n👤 *Worker:* `{worker}`\n📁 *Files Returned:* `{count}`"
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

    if chat_id != str(ADMIN_CHAT_ID):
        return jsonify({"status": "unauthorized"})

    # Command: /stats
    if text in ['/stats', '/start']:
        if not workers_stats:
            send_telegram_msg(chat_id, "⚠️ **Abhi kisi worker ka data active nahi hai.**")
            return jsonify({"status": "ok"})

        report = "📊 **ALL WORKERS LIVE REPORT**\n───────────────────\n\n"
        total_done = 0
        for w_name, s in workers_stats.items():
            report += (
                f"👤 **Worker:** `{w_name}`\n"
                f" ├ ✅ Files Done: `{s['done']}`\n"
                f" ├ ❌ Wrong Pass: `{s['wrong_pass']}`\n"
                f" ├ ⚠️ Login Failed: `{s['login_failed']}`\n"
                f" ├ 🛠️ Manage: `{s['manage']}`\n"
                f" └ 🆕 Total Created: `{s['created']}`\n\n"
            )
            total_done += s['done']

        report += f"───────────────────\n🏆 **OVERALL TOTAL DONE:** `{total_done}`"
        send_telegram_msg(chat_id, report)

    # Command: /reset
    elif text == '/reset':
        workers_stats.clear()
        send_telegram_msg(chat_id, "🧹 **Sabhi workers ke stats clear (0) kar diye gaye hain.**")

    # Command: /help
    elif text == '/help':
        help_msg = (
            "👑 **ADMIN CONTROL MENU**\n\n"
            "🔹 `/stats` - Live worker metrics dekhein\n"
            "🔹 `/reset` - Daily stats clear karein\n"
            "🔹 `/send <worker> <count>` - Files assign karein\n"
            "🔹 `/reverse <worker>` - Worker se bachi files wapas lein"
        )
        send_telegram_msg(chat_id, help_msg)

    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
