from flask import Flask, request
import requests
import os
import threading
import time
import yfinance as yf
import pandas as pd

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_TOKEN")
USER_ID = "U4e491f83955e58fa292d0082ff332eaa"

# =========================
# 🔧 自選持股（改這裡🔥）
# =========================
WATCHLIST = {
    "2330.TW": {"name": "台積電", "cost": 3237, "stop_loss": 2900, "take_profit": 4500},
    "6770.TW": {"name": "力積電", "cost": 66.2, "stop_loss": 60, "take_profit": 80},
    "3264.TW": {"name": "欣銓", "cost": 154.65, "stop_loss": 140, "take_profit": 180},
    "3481.TW": {"name": "群創", "cost": 26.42, "stop_loss": 24, "take_profit": 35},
    "3576.TW": {"name": "聯合再生", "cost": 23.89, "stop_loss": 20, "take_profit": 30},
    "2485.TW": {"name": "兆赫", "cost": 61.2, "stop_loss": 55, "take_profit": 90},
}

# 防洗版
last_state = {}

# =========================
# 🚀 LINE推播
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
# 🚀 Webhook（互動）
# =========================
@app.route("/webhook", methods=['POST'])
def webhook():
    data = request.json

    def process():
        try:
            for event in data.get("events", []):
                if event["type"] == "message":
                    reply_token = event["replyToken"]
                    text = event["message"]["text"]

                    reply = f"📊 系統運作中\n你說：{text}"

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
        except Exception as e:
            print(e)

    threading.Thread(target=process).start()
    return "OK", 200

# =========================
# 🧠 AI分析
# =========================
def analyze(stock_code, config):
    try:
        stock = yf.Ticker(stock_code)
        df = stock.history(period="1mo")

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
        ma5 = latest['MA5']
        ma20 = latest['MA20']
        rsi = latest['RSI']

        name = config["name"]
        cost = config["cost"]

        trend = "多頭" if ma5 > ma20 else "空頭"

        if rsi > 70:
            strength = "過熱"
        elif rsi < 30:
            strength = "超跌"
        elif rsi > 50:
            strength = "偏強"
        else:
            strength = "偏弱"

        decision = "👀 觀察"

        if price < cost:
            decision = "🚨 跌破成本"
        elif ma5 > ma20 and rsi < 70:
            decision = "✅ 可續抱/加碼"
        elif ma5 < ma20:
            decision = "⚠️ 趨勢轉弱"
        elif rsi > 70:
            decision = "💰 建議停利"

        # 狀態判斷（防洗版）
        state = f"{trend}-{strength}-{decision}"

        if last_state.get(stock_code) == state:
            return

        last_state[stock_code] = state

        msg = f"""📊 {name}
現價：{price:.2f}
成本：{cost}
趨勢：{trend}
RSI：{rsi:.1f}（{strength}）
判斷：{decision}
"""

        send_line_message(msg)

        print(stock_code, msg)

    except Exception as e:
        print(e)

# =========================
# 🚀 主迴圈
# =========================
def trading_bot():
    while True:
        for stock_code, config in WATCHLIST.items():
            analyze(stock_code, config)

        time.sleep(1800)  # 30分鐘

# =========================
# 🚀 啟動
# =========================
threading.Thread(target=trading_bot).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
