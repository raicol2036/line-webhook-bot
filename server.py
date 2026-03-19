from flask import Flask, request
import requests
import os
import json
import threading
import time
import yfinance as yf

app = Flask(__name__)

# =========================
# 🔥 Firebase 初始化（100%穩）
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
# 🔥 LINE 設定
# =========================
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_TOKEN")

def reply_line(reply_token, text):
    url = 'https://api.line.me/v2/bot/message/reply'
    headers = {
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    body = {
        "replyToken": reply_token,
        "messages":[{"type":"text","text": text}]
    }
    requests.post(url, headers=headers, json=body)

def push_line(user_id, text):
    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    body = {
        "to": user_id,
        "messages":[{"type":"text","text": text}]
    }
    requests.post(url, headers=headers, json=body)

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
# 📊 股票資料
# =========================
def get_price(code):
    try:
        return yf.Ticker(code).history(period="1d")["Close"].iloc[-1]
    except:
        return None

# =========================
# 🤖 指令解析（完全修正版）
# =========================
def handle_command(text, user_id):
    try:
        text = text.strip()
        parts = text.split()

        # =====================
        # 新增股票
        # =====================
        if text.startswith("新增"):
            if len(parts) != 6:
                return "❌ 用法：新增 2330 台積電 600 700 550"

            _, stock_id, name, cost, take_profit, stop_loss = parts

            code = stock_id + ".TW"

            add_stock(user_id, code, {
                "name": name,
                "cost": float(cost),
                "take_profit": float(take_profit),
                "stop_loss": float(stop_loss)
            })

            return f"✅ 已新增 {name} ({stock_id})"

        # =====================
        # 持股
        # =====================
        elif text == "持股":
            stocks = get_user_stocks(user_id)

            if not stocks:
                return "目前沒有持股"

            msg = "📊 持股列表\n\n"
            for code, data in stocks.items():
                msg += f"{data['name']} ({code})\n成本:{data['cost']}\n\n"

            return msg

        # =====================
        # 刪除
        # =====================
        elif text.startswith("刪除"):
            stock_id = parts[1] + ".TW"
            delete_stock(user_id, stock_id)
            return f"❌ 已刪除 {parts[1]}"

        # =====================
        # 分析
        # =====================
        elif text.startswith("分析"):
            if len(parts) != 2:
                return "用法：分析 2330"

            code = parts[1] + ".TW"
            price = get_price(code)

            if price is None:
                return "❌ 抓不到資料"

            return f"📊 {code}\n現價：{price:.2f}"

        return "❌ 指令錯誤"

    except Exception as e:
        print("ERROR:", e)
        return "❌ 系統錯誤"

# =========================
# 🔥 Webhook（關鍵）
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
# 🔥 Keep Alive（防睡眠）
# =========================
def keep_alive():
    while True:
        try:
            requests.get("https://你的網址.onrender.com")
            print("🔥 keep alive")
        except:
            pass
        time.sleep(300)

threading.Thread(target=keep_alive).start()

# =========================
# 🚀 啟動
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
