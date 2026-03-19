from flask import Flask, request
import requests
import os
import json
import threading
import time

app = Flask(__name__)

# =========================
# 🔥 Firebase
# =========================
db = None
try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred_json = json.loads(os.environ.get("FIREBASE_CREDENTIALS"))
        cred = credentials.Certificate(cred_json)
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    print("✅ Firebase OK")
except Exception as e:
    print("❌ Firebase error:", e)

# =========================
# 🔥 LINE
# =========================
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_TOKEN")

def reply_line(reply_token, text):
    requests.post(
        'https://api.line.me/v2/bot/message/reply',
        headers={
            'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={
            "replyToken": reply_token,
            "messages":[{"type":"text","text": text}]
        }
    )

def push_line(user_id, text):
    requests.post(
        'https://api.line.me/v2/bot/message/push',
        headers={
            'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
            'Content-Type': 'application/json'
        },
        json={
            "to": user_id,
            "messages":[{"type":"text","text": text}]
        }
    )

# =========================
# 🔥 Firebase CRUD
# =========================
def get_user_stocks(user_id):
    docs = db.collection("users").document(user_id).collection("stocks").stream()
    return {doc.id: doc.to_dict() for doc in docs}

def add_stock(user_id, stock_id, data):
    db.collection("users").document(user_id).collection("stocks").document(stock_id).set(data)

def delete_stock(user_id, stock_id):
    db.collection("users").document(user_id).collection("stocks").document(stock_id).delete()

# =========================
# 🔥 即時股價（TWSE）
# =========================
def get_price(stock_id):
    try:
        market = "tse" if int(stock_id) >= 1000 else "otc"

        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={market}_{stock_id}.tw"
        res = requests.get(url, timeout=5).json()

        if not res["msgArray"]:
            return None

        data = res["msgArray"][0]

        price = data.get("z")
        if price == "-" or price is None:
            price = data.get("b") or data.get("a")

        return float(price)

    except Exception as e:
        print("price error:", e)
        return None

# =========================
# 🔥 抓名稱
# =========================
def get_name(stock_id):
    try:
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw"
        res = requests.get(url).json()

        if res["msgArray"]:
            return res["msgArray"][0]["n"]
    except:
        pass

    return stock_id

# =========================
# 🧠 AI判斷
# =========================
def analyze(stock_id, config):
    price = get_price(stock_id)
    if price is None:
        return None

    cost = config["cost"]
    name = config["name"]

    profit = (price - cost) / cost * 100

    if price < config["stop_loss"]:
        decision = "🚨 停損"
    elif price > config["take_profit"]:
        decision = "💰 停利"
    else:
        decision = "✅ 持有"

    return price, profit, decision

# =========================
# 🔥 推播控制
# =========================
last_state = {}

# =========================
# 🔁 即時推播
# =========================
def realtime_loop():
    while True:
        try:
            users = db.collection("users").stream()

            for user in users:
                user_id = user.id
                stocks = get_user_stocks(user_id)

                for code, config in stocks.items():
                    stock_id = code.replace(".TW", "")
                    result = analyze(stock_id, config)

                    if result is None:
                        continue

                    price, profit, decision = result
                    state = f"{decision}-{round(price,1)}"

                    key = f"{user_id}-{code}"

                    if last_state.get(key) == state:
                        continue

                    last_state[key] = state

                    msg = f"""📊 {config['name']}
現價：{price}
報酬：{profit:.2f}%

👉 狀態：{decision}
"""
                    push_line(user_id, msg)

        except Exception as e:
            print("LOOP ERROR:", e)

        time.sleep(10)

threading.Thread(target=realtime_loop).start()

# =========================
# 🤖 指令
# =========================
def handle_command(text, user_id):
    text = text.strip()
    parts = text.split()

    try:
        # 🔥 新增（簡化 + 完整）
        if text.startswith("新增"):
            if len(parts) == 3:
                _, stock_id, cost = parts

                cost = float(cost)
                if cost == 0:
                    cost = get_price(stock_id)

                name = get_name(stock_id)

                tp = round(cost * 1.2, 2)
                sl = round(cost * 0.9, 2)

                add_stock(user_id, stock_id + ".TW", {
                    "name": name,
                    "cost": cost,
                    "take_profit": tp,
                    "stop_loss": sl
                })

                return f"""✅ 已新增 {name}
成本：{cost}
停利：{tp}
停損：{sl}
"""

            elif len(parts) == 6:
                _, stock_id, name, cost, tp, sl = parts

                add_stock(user_id, stock_id + ".TW", {
                    "name": name,
                    "cost": float(cost),
                    "take_profit": float(tp),
                    "stop_loss": float(sl)
                })

                return f"✅ 已新增 {name}"

            return "❌ 用法：新增 2330 600"

        elif text == "持股":
            stocks = get_user_stocks(user_id)
            if not stocks:
                return "目前沒有持股"

            msg = "📊 持股\n\n"
            for code, d in stocks.items():
                msg += f"{d['name']} ({code})\n成本:{d['cost']}\n\n"
            return msg

        elif text.startswith("刪除"):
            delete_stock(user_id, parts[1] + ".TW")
            return "❌ 已刪除"

        elif text.startswith("分析"):
            stock_id = parts[1]
            stocks = get_user_stocks(user_id)
            code = stock_id + ".TW"

            if code in stocks:
                result = analyze(stock_id, stocks[code])
                if result is None:
                    return "❌ 抓不到資料"

                price, profit, decision = result

                return f"""📊 {stocks[code]['name']}
現價：{price}
報酬：{profit:.2f}%

👉 建議：{decision}
"""
            else:
                price = get_price(stock_id)
                if price is None:
                    return "❌ 抓不到資料"

                return f"📊 {stock_id}\n現價：{price}"

        return "❌ 指令錯誤"

    except Exception as e:
        print("CMD ERROR:", e)
        return "❌ 系統錯誤"

# =========================
# 🔥 Webhook
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    for event in data.get("events", []):
        if event["type"] == "message":
            user_id = event["source"]["userId"]
            text = event["message"]["text"]

            reply = handle_command(text, user_id)
            reply_line(event["replyToken"], reply)

    return "OK"

# =========================
# 🔥 防睡眠
# =========================
def keep_alive():
    while True:
        try:
            requests.get("https://你的網址.onrender.com")
        except:
            pass
        time.sleep(300)

threading.Thread(target=keep_alive).start()

# =========================
# 🚀 啟動
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
