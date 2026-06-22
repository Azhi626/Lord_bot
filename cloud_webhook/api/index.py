from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, db
import os
import datetime
import json

app = Flask(__name__)

# 初始化 Firebase Admin SDK
# 因為部署到 Vercel，金鑰會存放在環境變數中
# 為了避免在 Vercel 多次執行時重複初始化，做個檢查
if not firebase_admin._apps:
    try:
        # 假設環境變數 FIREBASE_CREDENTIALS 存放 JSON 格式的金鑰
        cred_json = os.environ.get('FIREBASE_CREDENTIALS')
        if cred_json:
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {
                'databaseURL': os.environ.get('FIREBASE_DATABASE_URL')
            })
        else:
            print("Warning: FIREBASE_CREDENTIALS env var not set.")
    except Exception as e:
        print(f"Firebase Init Error: {e}")

@app.route('/', methods=['GET'])
def home():
    return "Kururu's Webhook is running. Kukuku...", 200

@app.route('/webhook/lord_bot', methods=['POST'])
def webhook_lord_bot():
    return handle_telegram_update(request, source='lord_bot')

@app.route('/webhook/niouuu', methods=['POST'])
def webhook_niouuu():
    return handle_telegram_update(request, source='Niouuu')

def handle_telegram_update(req, source):
    """
    處理來自 Telegram 的 Webhook 請求
    """
    try:
        update = req.get_json()
        if not update:
            return "No JSON", 400

        if "message" not in update:
            return jsonify({'status': 'ignored', 'reason': 'not a message'}), 200

        message = update["message"]
        
        # 提取基本資訊
        msg_id = message.get("message_id")
        date_unix = message.get("date", 0)
        
        # 處理時區，改為 UTC 或本機時間 (這裡使用 UTC)
        timestamp = datetime.datetime.fromtimestamp(date_unix, datetime.timezone.utc).isoformat()
        
        text = message.get("text") or message.get("caption") or ""
        
        # 提取檔案 (如果有圖片或文件)
        file_id = None
        if "photo" in message:
            # photo 是陣列，取解析度最高的最後一張
            file_id = message["photo"][-1]["file_id"]
        elif "document" in message:
            file_id = message["document"]["file_id"]
            
        # 準備寫入 Firebase 的資料
        task_data = {
            'source': source,
            'message_id': msg_id,
            'timestamp': timestamp,
            'text': text,
            'file_id': file_id,
            'status': 'pending',
            'raw_update': update # 保留原始資料以防萬一
        }
        
        # 寫入 Firebase Realtime Database
        if firebase_admin._apps:
            # 以 source 和 msg_id 組合成 key
            ref = db.reference(f'tasks/pending/{source}_{msg_id}')
            ref.set(task_data)
        else:
            print(f"[{source}] Firebase not initialized. Would write: {task_data}")
            
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        print(f"Error handling update: {e}")
        # Telegram Webhook 遇到非 200 回應會一直重試，所以我們還是回傳 200，但記錄錯誤
        return jsonify({'status': 'error', 'message': str(e)}), 200

# 支援 Vercel Serverless
if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get("PORT", 3000)))
