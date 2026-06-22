from flask import Flask, request, jsonify
import requests
import datetime
import os

app = Flask(__name__)

# 直接使用 Firebase REST API
FIREBASE_URL = "https://gameoflife-9cd23-default-rtdb.firebaseio.com"

@app.route('/', methods=['GET'])
def home():
    return "Webhook is running. Kukuku...", 200

@app.route('/webhook/lord_bot', methods=['POST'])
def webhook_lord_bot():
    return handle_telegram_update(request, source='lord_bot')

@app.route('/webhook/niouuu', methods=['POST'])
def webhook_niouuu():
    return handle_telegram_update(request, source='Niouuu')

def handle_telegram_update(req, source):
    try:
        update = req.get_json()
        if not update or "message" not in update:
            return jsonify({'status': 'ignored'}), 200

        message = update["message"]
        msg_id = message.get("message_id")
        date_unix = message.get("date", 0)
        timestamp = datetime.datetime.fromtimestamp(date_unix, datetime.timezone.utc).isoformat()
        text = message.get("text") or message.get("caption") or ""
        
        file_id = None
        if "photo" in message:
            file_id = message["photo"][-1]["file_id"]
        elif "document" in message:
            file_id = message["document"]["file_id"]
            
        task_data = {
            'source': source,
            'message_id': msg_id,
            'timestamp': timestamp,
            'text': text,
            'file_id': file_id,
            'status': 'pending',
            'raw_update': update
        }
        
        # 寫入 Firebase
        url = f"{FIREBASE_URL}/tasks/pending/{source}_{msg_id}.json"
        requests.put(url, json=task_data)
            
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        print(f"Error handling update: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 200

if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get("PORT", 3000)))
