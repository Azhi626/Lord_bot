from flask import Flask, request, jsonify
import requests
import datetime
import os
import json
import re
import google.generativeai as genai
import cloud_task_manager

app = Flask(__name__)

FIREBASE_URL = "https://gameoflife-9cd23-default-rtdb.firebaseio.com"
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

SOUL_PROMPT = """身分：小奇分身。請以 JSON 格式回傳 reply 與 action。
[
  {
    "reply": "你對阿智說的話",
    "action": { "type": "none" }
  }
]
"""

try:
    # 嘗試讀取 SOUL.md 如果存在
    with open("SOUL.md", "r", encoding="utf-8") as f:
        SOUL_PROMPT = f.read()
except FileNotFoundError:
    pass

def safe_send_message(chat_id, text):
    if not TG_BOT_TOKEN:
        print("TG_BOT_TOKEN not set")
        return
    text = text.replace('<br>', '\n').replace('<br/>', '\n')
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        resp = requests.post(url, json=payload, timeout=5)
        if not resp.ok:
            payload["parse_mode"] = ""
            payload["text"] = re.sub('<[^<]+?>', '', text) + "\n\n⚠️ [系統提示] 標籤未閉合，已轉純文字。"
            requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("send_message error:", e)

def sort_pending_tasks(pending):
    tz = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(tz)
    hour = now.hour
    is_work_mode = 8 <= hour < 17
    
    def get_sort_key(t):
        tid = str(t.get("id") or t.get("taskId") or "").upper()
        if tid.startswith("J"):
            world = "J"
        elif tid.startswith("G"):
            world = "G"
        elif tid.startswith("ZD"):
            world = "ZD"
        elif tid.startswith("Z"):
            world = "Z"
        else:
            world = "Z"
            
        if is_work_mode:
            priority = {"J": 0, "G": 1, "Z": 2, "ZD": 3}.get(world, 4)
        else:
            priority = {"Z": 0, "G": 1, "ZD": 2, "J": 3}.get(world, 4)
            
        diff = t.get('difficulty', 1)
        try:
            diff = float(diff)
        except:
            diff = 1.0
            
        return (priority, -diff, tid)

    pending.sort(key=get_sort_key)
    return pending

def get_tasks_summary():
    tasks_data = cloud_task_manager.read_tasks()
    all_tasks = tasks_data.get("data", [])
    
    pending = [t for t in all_tasks if t.get("status") in ("pending", "進行中", "未開始")]
    
    tz = datetime.timezone(datetime.timedelta(hours=8))
    now = datetime.datetime.now(tz)
    today_str_date = now.strftime("%Y-%m-%d")
    today_str_md = now.strftime("%m%d")
    
    completed_today = []
    for t in all_tasks:
        if t.get("status") in ("completed", "完成"):
            is_completed_today = False
            comp_at = t.get("completed_at")
            if comp_at:
                try:
                    comp_dt = datetime.datetime.fromtimestamp(float(comp_at), tz)
                    if comp_dt.strftime("%Y-%m-%d") == today_str_date:
                        is_completed_today = True
                except: pass
            if not is_completed_today:
                tid = str(t.get("id") or t.get("taskId") or "")
                title = str(t.get("title") or t.get("taskName") or "")
                desc = str(t.get("description") or t.get("note") or t.get("taskNotes") or "")
                if today_str_md in tid or today_str_md in title or today_str_md in desc:
                    is_completed_today = True
            
            if is_completed_today:
                tid = str(t.get("id") or t.get("taskId") or "")
                title = str(t.get("title") or t.get("taskName") or "")
                completed_today.append(f"- [{tid}] {title}")

    if not pending and not completed_today:
        return "目前沒有待辦任務。"
        
    lines = []
    if not pending:
        lines.append("目前沒有待辦任務。")
    else:
        pending = sort_pending_tasks(pending)
        
        today_urgent = []
        no_deadline = []
        
        for t in pending:
            title = str(t.get("title") or t.get("taskName") or "")
            tid = str(t.get("id") or t.get("taskId") or "")
            desc = str(t.get("description") or t.get("note") or t.get("taskNotes") or "")
            deadline = str(t.get("deadline") or t.get("timeTo") or "")
            
            item_str = f"- [{tid}] {title}"
            is_today = False
            if t.get("is_daily") or "G001_" in tid or "Z001_" in tid:
                is_today = True
            elif deadline and today_str_date in deadline:
                is_today = True
            elif "今天" in desc or "今日" in desc or "今天" in title or "今日" in title or "下班" in title:
                is_today = True
                
            if is_today:
                today_urgent.append(item_str)
            else:
                no_deadline.append(item_str)
                
        lines.append("【今天一定要做完的】")
        if today_urgent:
            lines.extend(today_urgent)
        else:
            lines.append("- (目前全數通關！)")
            
        lines.append("\n【沒有時效性的任務】")
        if no_deadline:
            lines.extend(no_deadline)
        else:
            lines.append("- (目前無待辦)")

    lines.append("\n【今日已完成任務】")
    if completed_today:
        lines.extend(completed_today)
    else:
        lines.append("- (尚未有完成紀錄)")
        
    return "\n".join(lines)


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
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        msg_id = message.get("message_id")
        text = message.get("text") or message.get("caption") or ""
        
        has_media = "photo" in message or "document" in message
        is_collect = "#蒐集" in text
        
        if has_media or is_collect:
            # 放進 Firebase pending_jobs 等待本地抓取
            date_unix = message.get("date", 0)
            timestamp = datetime.datetime.fromtimestamp(date_unix, datetime.timezone.utc).isoformat()
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
            url = f"{FIREBASE_URL}/tasks/pending_jobs/{source}_{msg_id}.json"
            requests.put(url, json=task_data, timeout=5)
            
            safe_send_message(chat_id, "【系統回報】已將資料放入 Firebase pending_jobs 佇列，等待本地端處理。")
            return jsonify({'status': 'success'}), 200

        if not text:
            return jsonify({'status': 'ignored'}), 200

        # Vercel 有 10 秒硬限制，呼叫 Gemini 並處理
        if not GEMINI_API_KEY:
            safe_send_message(chat_id, "【系統回報】未設定 GEMINI_API_KEY。")
            return jsonify({'status': 'error'}), 200

        # 組裝 prompt
        tasks_summary = get_tasks_summary()
        player_data = cloud_task_manager.read_player()
        tasks_data = cloud_task_manager.read_tasks()
        currencies_data = tasks_data.get("player", {})
        
        player_status = f"【玩家狀態】\n等級: {player_data.get('level', 1)} | HP: {player_data.get('hp', 100)} | EXP: {player_data.get('exp', 0)}\n點數: {player_data.get('points', 0)}\n"
        for k, v in currencies_data.items():
            if k not in ["level", "currentExp", "nextLevelExp"]:
                player_status += f"- {k}: {v}\n"

        tz = datetime.timezone(datetime.timedelta(hours=8))
        now_str = datetime.datetime.now(tz).isoformat()
        
        context_prompt = f"{player_status}\n當下時間：{now_str}\n目前任務狀態：\n{tasks_summary}\n\n【最新指令】{text}\n請嚴格回傳符合格式的 JSON。"

        try:
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash-lite",
                system_instruction=SOUL_PROMPT
            )
            # 限制超時時間以防 Vercel 斷線
            response = model.generate_content(
                context_prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json"
                ),
                request_options={"timeout": 8.0}
            )
            
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
                
            try:
                parsed_data = json.loads(raw_text)
            except:
                parsed_data = [{"reply": raw_text, "action": {"type": "none"}}]

            if isinstance(parsed_data, str):
                try:
                    parsed_data = json.loads(parsed_data)
                except:
                    pass
            if isinstance(parsed_data, dict):
                parsed_data = [parsed_data]
            elif not isinstance(parsed_data, list):
                parsed_data = [{"reply": str(parsed_data), "action": {"type": "none"}}]
                
            reply_texts = []
            actions = []
            for item in parsed_data:
                if not isinstance(item, dict):
                    item = {"reply": str(item), "action": {"type": "none"}}
                r_text = item.get("reply", "")
                if r_text:
                    reply_texts.append(r_text)
                action = item.get("action", {})
                if not isinstance(action, dict):
                    action = {"type": str(action), "details": {}}
                actions.append(action)
                
            reply_text = "\n\n".join(reply_texts) if reply_texts else "【🤖 主神宣告】處理完成。"
            
            # 處理 Actions
            for action in actions:
                action_type = action.get("type", "none")
                details = action.get("details", {})
                
                if action_type == "add_task":
                    title = details.get("task_title", "未命名任務")
                    note = details.get("note", "")
                    continent_prefix = details.get("continent_prefix", "Z")
                    deadline = details.get("deadline", None)
                    new_task = cloud_task_manager.add_task(title, note=note, continent_prefix=continent_prefix, deadline=deadline)
                    reply_text = reply_text.replace("[NEW]", f"<code>[{new_task['id']}]</code>", 1)
                    
                elif action_type == "update_task":
                    task_title = details.get("task_title")
                    
                    target_id = None
                    tasks_data_local = cloud_task_manager.read_tasks()
                    for t in tasks_data_local.get("data", []):
                        if str(t.get("id")) == str(task_title) or str(t.get("title")) == str(task_title):
                            target_id = t.get("id")
                            break
                            
                    if target_id:
                        cloud_task_manager.update_task(target_id, details)
                        reply_text += f"\n\n🔧 任務更新訊號已發送。"
                    
                elif action_type == "complete_task":
                    task_title = details.get("task_title")
                    
                    target_id = None
                    tasks_data_local = cloud_task_manager.read_tasks()
                    for t in tasks_data_local.get("data", []):
                        if str(t.get("id")) == str(task_title) or str(t.get("title")) == str(task_title):
                            target_id = t.get("id")
                            break
                            
                    if target_id:
                        res = cloud_task_manager.complete_task(target_id)
                        if isinstance(res, dict) and res.get("success"):
                            reply_text += f"\n\n✅ 任務 {task_title} 已打卡！"
                        
            safe_send_message(chat_id, reply_text)
            
        except Exception as e:
            if "Deadline Exceeded" in str(e) or "timeout" in str(e).lower() or "504" in str(e):
                safe_send_message(chat_id, "【系統回報】主神運算逾時，請稍後再試。")
            else:
                safe_send_message(chat_id, f"【系統回報】發生錯誤：{e}")
            return jsonify({'status': 'error', 'message': str(e)}), 200

        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        print(f"Error handling update: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 200

if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get("PORT", 3000)))
