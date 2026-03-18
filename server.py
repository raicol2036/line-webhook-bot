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
# 🔧 自選股票 + 風控設定
# =========================
WATCHLIST = {
    "3264.TW": {"buy": 150, "stop_loss": 154, "take_profit": 165},
    "7769.TW": {"buy": 4100, "stop_loss": 4300, "take_profit": 4450},
    "6770.TW": {"buy": 60, "stop_loss": 65, "take_profit": 80},
}

# 防重複
last_signal = {}

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
        "messages":[
            {
                "type":"text",
                "text": text
            }
        ]
    }
    requests.post(url, headers=headers, json=body)

# =========================
# 🚀 Webhook（保留）
# =========================
@app.route("/webhook", methods=['POST'])
def webhook():
    return "OK", 200

# =========================
# 🚀 策略核心
# =========================
def check_stock(stock_code, config):
    try:
        stock = yf.Ticker(stock_code)
        df = stock.history(period="1mo")

        if len(df) < 20:
            return

        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        price = latest['Close']
        ma5 = latest['MA5']
        ma20 = latest['MA20']

        prev_ma5 = prev['MA5']
        prev_ma20 = prev['MA20']

        stop = config["stop_loss"]
        take = config["take_profit"]

        signal = None

        # 📈 黃金交叉（買點）
        if prev_ma5 < prev_ma20 and ma5 > ma20:
            signal = "GOLDEN"

        # 📉 死亡交叉（賣點）
        elif prev_ma5 > prev_ma20 and ma5 < ma20:
            signal = "DEATH"

        # 🚨 停損
        elif price < stop:
            signal = "STOP"

        # 💰 停利
        elif price > take:
            signal = "TAKE"

        # 防重複
        if last_signal.get(stock_code) == signal:
            return

        # =====================
        # 🚀 發送通知
        # =====================
        if signal == "GOLDEN":
            send_line_message(f"📈 {stock_code} 黃金交叉\n現價:{price:.2f}")
        elif signal == "DEATH":
            send_line_message(f"📉 {stock_code} 死亡交叉\n現價:{price:.2f}")
        elif signal == "STOP":
            send_line_message(f"🚨 {stock_code} 停損觸發\n現價:{price:.2f}")
        elif signal == "TAKE":
            send_line_message(f"💰 {stock_code} 停利達成\n現價:{price:.2f}")

        if signal:
            last_signal[stock_code] = signal

        print(stock_code, price, signal)

    except Exception as e:
        print(e)

# =========================
# 🚀 主迴圈
# =========================
def trading_bot():
    while True:
        for stock_code, config in WATCHLIST.items():
            check_stock(stock_code, config)

        time.sleep(300)  # 每5分鐘

# =========================
# 🚀 啟動
# =========================
threading.Thread(target=trading_bot).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
