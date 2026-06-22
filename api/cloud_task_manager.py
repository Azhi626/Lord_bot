import os
import time
import requests
import re
import datetime

FIREBASE_URL = "https://gameoflife-9cd23-default-rtdb.firebaseio.com"

def read_tasks():
    url = f"{FIREBASE_URL}/tasks/active.json"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return {"data": [], "player": {"level": 1, "currentExp": 0, "nextLevelExp": 100, "silver_Z": 0, "fur_Y": 0, "banana_J": 0, "bitcoin_G": 0}}
        if "data" not in data or data["data"] is None:
            data["data"] = []
        # Firebase arrays can have None elements if sparse
        data["data"] = [t for t in data["data"] if t]
        return data
    except Exception as e:
        print("read_tasks error:", e)
        return {"data": [], "player": {"level": 1, "currentExp": 0, "nextLevelExp": 100, "silver_Z": 0, "fur_Y": 0, "banana_J": 0, "bitcoin_G": 0}}

def write_tasks(data):
    url = f"{FIREBASE_URL}/tasks/active.json"
    try:
        # Prevent sparse array issues in Firebase
        data["data"] = [t for t in data["data"] if t]
        requests.put(url, json=data, timeout=5)
    except Exception as e:
        print("write_tasks error:", e)

def read_player():
    url = f"{FIREBASE_URL}/player.json"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return {"hp": 100, "exp": 0, "level": 1, "points": 0}
        return data
    except:
        return {"hp": 100, "exp": 0, "level": 1, "points": 0}

def write_player(data):
    url = f"{FIREBASE_URL}/player.json"
    try:
        requests.put(url, json=data, timeout=5)
    except Exception as e:
        print("write_player error:", e)

def calculate_difficulty(text):
    score = 1
    high_diff_keywords = ["重構", "架構", "演算法", "系統", "底層", "API", "整合", "部署", "資料庫"]
    med_diff_keywords = ["開發", "功能", "測試", "修復", "bug", "更新", "新增", "調整"]
    
    for kw in high_diff_keywords:
        if kw in text:
            score += 2
    for kw in med_diff_keywords:
        if kw in text:
            score += 1
            
    if len(text) > 50:
        score += 1
        
    return min(max(score, 1), 5)

def add_task(title, description="", note="", continent_prefix="Z", deadline=None):
    difficulty = calculate_difficulty(title + " " + description + " " + note)
    tasks_data = read_tasks()
    
    max_id = 0
    pattern = re.compile(f"^{re.escape(continent_prefix)}(\\d{{3}})$")
    for t in tasks_data.get("data", []):
        tid = str(t.get("id") or t.get("taskId") or "")
        match = pattern.match(tid)
        if match:
            max_id = max(max_id, int(match.group(1)))
    task_id = f"{continent_prefix}{max_id + 1:03d}"

    if continent_prefix.startswith("Y"):
        currency = "fur_Y"
    elif continent_prefix.startswith("J"):
        currency = "banana_J"
    elif continent_prefix.startswith("G"):
        currency = "bitcoin_G"
    else:
        currency = "silver_Z"

    new_task = {
        "id": task_id,
        "title": title,
        "description": description,
        "note": note,
        "difficulty": difficulty,
        "status": "pending",
        "reward": {"exp": difficulty * 10, "currencies": {currency: difficulty * 10}},
        "created_at": time.time(),
        "deadline": deadline
    }
    
    tasks_data["data"].append(new_task)
    write_tasks(tasks_data)
        
    return new_task

def add_log(task_id, log_count=1, note_append=""):
    tasks_data = read_tasks()
    task_found = False
    for task in tasks_data.get("data", []):
        t_id = str(task.get("id") or task.get("taskId") or "")
        if t_id == task_id:
            current_log = task.get("taskLog", 0)
            task["taskLog"] = current_log + log_count
            if note_append:
                current_note = task.get("taskNotes", "")
                if current_note:
                    task["taskNotes"] = current_note + "\n" + note_append
                else:
                    task["taskNotes"] = note_append
            task_found = True
            break
    if task_found:
        write_tasks(tasks_data)
        return True
    return False

def update_task(task_id, updates: dict):
    tasks_data = read_tasks()
    task_found = False
    for task in tasks_data.get("data", []):
        if task.get("id") == task_id or task.get("taskId") == task_id:
            for k, v in updates.items():
                task[k] = v
            task_found = True
            break
    if task_found:
        write_tasks(tasks_data)
        return True
    return False

def delete_task(task_id):
    tasks_data = read_tasks()
    original_len = len(tasks_data.get("data", []))
    tasks_data["data"] = [t for t in tasks_data.get("data", []) if t.get("id") != task_id and t.get("taskId") != task_id]
    
    if len(tasks_data["data"]) < original_len:
        write_tasks(tasks_data)
        return True
    return False

def deduct_points(points):
    player_data = read_player()
    if "points" not in player_data:
        player_data["points"] = 0
    player_data["points"] = max(0, player_data["points"] - points)
    write_player(player_data)

def complete_task(task_id):
    tasks_data = read_tasks()
    player_data = read_player()
    
    task_found = False
    task_list = tasks_data.get("data", [])
    for task in task_list:
        if task.get("id") == task_id or task.get("taskId") == task_id:
            is_daily = task.get("is_daily", False)
            tz = datetime.timezone(datetime.timedelta(hours=8))
            today_str = datetime.datetime.now(tz).strftime("%Y-%m-%d")
            
            if is_daily:
                if today_str in task.get("daily_history", []):
                    return False
                task["status"] = "pending"
                task.setdefault("daily_history", []).append(today_str)
                task["completed_count"] = task.get("completed_count", 0) + 1
            else:
                if task.get("status") in ("completed", "完成"):
                    return False
                
                goal = task.get("taskGoal", 1)
                current_log = task.get("taskLog", 0)
                
                if goal > 1 and current_log + 1 < goal:
                    task["taskLog"] = current_log + 1
                    write_tasks(tasks_data)
                    return {"success": True, "message": f"⏳ 進度推進：目前 {task['taskLog']} / {goal}", "progress_only": True}
                
                task["taskLog"] = goal
                task["status"] = "完成"
                
            task["completed_at"] = time.time()
            
            unlocks = task.get("unlocks", [])
            if unlocks:
                for t in task_list:
                    t_id = str(t.get("id") or t.get("taskId") or "")
                    if t_id in unlocks and t.get("status") == "locked":
                        t["status"] = "pending"

            reward_exp = task.get("difficulty", 1) * 10
            reward_points = task.get("difficulty", 1) * 5
            
            player_data["exp"] += reward_exp
            player_data["points"] += reward_points
            
            if player_data["exp"] >= player_data["level"] * 100:
                player_data["level"] += 1
                player_data["hp"] = 100
                
            reward_data = task.get("reward")
            if isinstance(reward_data, dict):
                currencies = reward_data.get("currencies")
                if isinstance(currencies, dict):
                    if "player" not in tasks_data or not isinstance(tasks_data["player"], dict):
                        tasks_data["player"] = {
                            "level": 1, "currentExp": 0, "nextLevelExp": 100,
                            "silver_Z": 0, "fur_Y": 0, "banana_J": 0, "bitcoin_G": 0
                        }
                    player_currencies = tasks_data["player"]
                    for currency_name, currency_val in currencies.items():
                        if not isinstance(currency_val, (int, float)):
                            continue
                        if currency_name not in player_currencies or player_currencies[currency_name] in [None, ""]:
                            player_currencies[currency_name] = 0
                        player_currencies[currency_name] += currency_val
                
            task_found = True
            break
            
    if task_found:
        write_tasks(tasks_data)
        write_player(player_data)
        
        motivational_msg = ""
        if isinstance(task_id, str) and (task_id.startswith("G001_") or task_id.startswith("Z001_")):
            tz = datetime.timezone(datetime.timedelta(hours=8))
            yesterday_str = (datetime.datetime.now(tz) - datetime.timedelta(days=1)).strftime("%m%d")
            base_prefix = task_id[:5]
            
            yesterday_a = f"{base_prefix}{yesterday_str}_A"
            yesterday_b = f"{base_prefix}{yesterday_str}_B"
            yesterday_c = f"{base_prefix}{yesterday_str}_C"
            
            highest_stage = None
            for t in task_list:
                t_id = str(t.get("id") or t.get("taskId") or "")
                if t_id in [yesterday_a, yesterday_b, yesterday_c]:
                    if t.get("status") in ("completed", "完成"):
                        stage = t_id[-1]
                        if highest_stage is None or stage > highest_stage:
                            highest_stage = stage
                            
            current_stage = task_id[-1]
            if highest_stage:
                if current_stage > highest_stage:
                    motivational_msg = f"太神啦！昨天只到 {highest_stage} 階段，今天突破到 {current_stage} 階段了！"
                elif current_stage == highest_stage:
                    motivational_msg = f"穩如泰山！穩穩地拿下 {current_stage} 階段，保持節奏！"
                else:
                    motivational_msg = f"昨天拚到了 {highest_stage} 階段，今天也要繼續往上衝擊啊！"
            else:
                if current_stage == 'A':
                    motivational_msg = "昨天休息了一天，今天強勢回歸，順利拿下 A 階段！"
                else:
                    motivational_msg = f"昨天沒達標，但今天你直接衝到了 {current_stage} 階段，絕地大反攻！"
                
        return {"success": True, "message": motivational_msg}
    return {"success": False, "message": ""}
