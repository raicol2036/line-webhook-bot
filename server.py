from flask import Flask, request
import requests
import os
import threading
import time
import yfinance as yf
import pandas as pd
import json
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

# =========================
# 🔥 Firebase 初始化
# =========================
cred_json = json.loads(os.environ.get("FIREBASE_CREDENTIALS"))
cred = credentials.Certificate(cred_json)
firebase_admin.initialize_app(cred)
db = firestore.client()

# =========================
# LINE
# =========================
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_TOKEN")
USER_ID = "U4e491f83955e58fa292d0082ff332eaa"

last_state = {}

# =========================
# 🔥 Firebase CRUD
# =========================
def get_watchlist():
    docs = db.collection("stocks").stream()
    result = {}
    for doc in docs:
        result[doc.id] = doc.to_dict()
    return result

def add_stock(code, data):
    db.collection("stocks").document(code).set(data)

def delete_stock(code):
    db.collection("stocks").document(code).delete()

# =========================
# LINE 推播
# =========================
def send_line_message(text):
    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    body = {
        "to": USER_ID,
        "messages":[{"type":"text","text": text}]
    }
    requests.post(url, headers=headers, json=body)

# =========================
# 指令
# =========================
def handle_command(text):
    try:
        text = text.strip()
        parts = text.split()

        # 👉 新增
        if text.startswith("新增"):
            if len(parts) < 6:
                return "格式錯誤\n範例：新增 2330 台積電 600 550 700"

            code = parts[1] + ".TW"
            name = parts[2]

            try:
                cost = float(parts[3])
                stop_loss = float(parts[4])
                take_profit = float(parts[5])
            except:
                return "數值錯誤（成本/停損/停利要是數字）"

            add_stock(code, {
                "name": name,
                "cost": cost,
                "stop_loss": stop_loss,
                "take_profit": take_profit
            })

            return f"✅ 已新增 {name}"

        # 👉 刪除
        elif text.startswith("刪除"):
            if len(parts) < 2:
                return "格式錯誤：刪除 2330"

            code = parts[1] + ".TW"
            delete_stock(code)
            return f"❌ 已刪除 {code}"

        # 👉 持股
        elif text.startswith("持股"):
            watchlist = get_watchlist()

            if not watchlist:
                return "目前沒有持股"

            msg = ""
            for k, v in watchlist.items():
                msg += f"{v['name']} ({k})\n成本:{v['cost']}\n\n"

            return msg

        else:
            return "指令錯誤\n\n用法：新增 2330 台積電 600 550 700"

    except Exception as e:
        print("❌ ERROR:", e)
        return "系統錯誤"

# =========================
# Webhook
# =========================
@app.route("/webhook", methods=['POST'])
def webhook():
    data = request.json

    for event in data.get("events", []):
        if event["type"] == "message":
            reply_token = event["replyToken"]
            text = event["message"]["text"]

            reply = handle_command(text)

            url = 'https://api.line.me/v2/bot/message/reply'
            headers = {
                'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
                'Content-Type': 'application/json'
            }
            body = {
                'replyToken': reply_token,
                'messages': [{"type":"text","text": reply}]
            }
            requests.post(url, headers=headers, json=body)

    return "OK"

# =========================
# AI分析
# =========================
def analyze(code, config):
    try:
        df = yf.Ticker(code).history(period="1mo")
        if len(df) < 20:
            return

        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        latest = df.iloc[-1]

        price = latest['Close']
        rsi = latest['RSI']

        cost = config["cost"]
        name = config["name"]

        profit = (price - cost) / cost * 100

        decision = "觀察"
        if price < config["stop_loss"]:
            decision = "🚨 停損"
        elif price > config["take_profit"]:
            decision = "💰 停利"

        state = f"{decision}-{round(profit,1)}"

        if last_state.get(code) == state:
            return

        last_state[code] = state

        msg = f"""📊 {name}
現價：{price:.2f}
報酬：{profit:.2f}%
RSI：{rsi:.1f}
判斷：{decision}
"""

        send_line_message(msg)

    except Exception as e:
        print(e)

# =========================
# 主迴圈
# =========================
def bot_loop():
    while True:
        watchlist = get_watchlist()
        for code, config in watchlist.items():
            analyze(code, config)

        time.sleep(600)

threading.Thread(target=bot_loop).start()

# =========================
# 啟動
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
