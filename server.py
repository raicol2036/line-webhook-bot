from flask import Flask, request
import requests
import os
import json
import threading
import time
import yfinance as yf

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
# 📊 分析核心
# =========================
def analyze_decision(stock_id, config=None):
    try:
        code = stock_id + ".TW"
        df = yf.Ticker(code).history(period="1mo")

        if df.empty:
            return f"❌ 抓不到 {stock_id}"

        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        latest = df.iloc[-1]

        price = latest['Close']
        ma5 = latest['MA5']
        ma20 = latest['MA20']
        rsi = latest['RSI']

        decision = ""
        if config:
            cost = config["cost"]
            profit = (price - cost) / cost * 100

            if price < config["stop_loss"]:
                decision = "🚨 停損"
            elif price > config["take_profit"]:
                decision = "💰 停利"
            elif ma5 < ma20:
                decision = "⚠️ 轉弱"
            else:
                decision = "✅ 續抱"

            return f"""📊 {config['name']}
現價：{price:.2f}
報酬：{profit:.2f}%
RSI：{rsi:.1f}

👉 建議：{decision}
"""

        # 單純查詢
        if rsi > 80:
            decision = "⚠️ 過熱建議賣出"
        elif ma5 < ma20:
            decision = "⚠️ 轉弱"
        else:
            decision = "✅ 多頭續抱"

        return f"""📊 {stock_id}
現價：{price:.2f}
RSI：{rsi:.1f}

👉 建議：{decision}
"""

    except Exception as e:
        print(e)
        return "❌ 系統錯誤"

# =========================
# 🤖 指令
# =========================
def handle_command(text, user_id):
    text = text.strip()
    parts = text.split()

    try:
        # 新增
        if text.startswith("新增"):
            if len(parts) != 6:
                return "❌ 用法：新增 2330 台積電 600 700 550"

            _, stock_id, name, cost, tp, sl = parts

            add_stock(user_id, stock_id + ".TW", {
                "name": name,
                "cost": float(cost),
                "take_profit": float(tp),
                "stop_loss": float(sl)
            })

            return f"✅ 已新增 {name}"

        # 持股
        elif text == "持股":
            stocks = get_user_stocks(user_id)
            if not stocks:
                return "目前沒有持股"

            msg = "📊 持股\n\n"
            for code, d in stocks.items():
                msg += f"{d['name']} ({code})\n成本:{d['cost']}\n\n"
            return msg

        # 刪除
        elif text.startswith("刪除"):
            delete_stock(user_id, parts[1] + ".TW")
            return "❌ 已刪除"

        # 分析（🔥核心）
        elif text.startswith("分析"):
            stock_id = parts[1]

            stocks = get_user_stocks(user_id)
            code = stock_id + ".TW"

            if code in stocks:
                return analyze_decision(stock_id, stocks[code])
            else:
                return analyze_decision(stock_id)

        return "❌ 指令錯誤"

    except Exception as e:
        print("CMD ERROR:", e)
        return "❌ 系統錯誤"

# =========================
# 🔁 自動監控
# =========================
last_status = {}

def auto_loop():
    while True:
        try:
            users = db.collection("users").stream()

            for user in users:
                user_id = user.id
                stocks = get_user_stocks(user_id)

                for code, data in stocks.items():
                    msg = analyze_decision(code.replace(".TW", ""), data)

                    key = user_id + code
                    if last_status.get(key) != msg:
                        last_status[key] = msg
                        push_line(user_id, msg)

        except Exception as e:
            print("LOOP ERROR:", e)

        time.sleep(600)

threading.Thread(target=auto_loop).start()

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
