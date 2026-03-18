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

# 🚀 LINE推播
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

# 🚀 Webhook
@app.route("/webhook", methods=['POST'])
def webhook():
    return "OK", 200


# 🚀 台股策略（均線）
def check_stock(stock_code):
    try:
        stock = yf.Ticker(stock_code)
        df = stock.history(period="1mo")

        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()

        latest = df.iloc[-1]

        price = latest['Close']
        ma5 = latest['MA5']
        ma20 = latest['MA20']

        print(stock_code, price, ma5, ma20)

        # 策略
        if ma5 > ma20:
            send_line_message(f"📈 {stock_code} 黃金交叉\n現價:{price:.2f}")
        elif ma5 < ma20:
            send_line_message(f"📉 {stock_code} 死亡交叉\n現價:{price:.2f}")

    except Exception as e:
        print(e)


# 🚀 主迴圈
def trading_bot():
    stocks = ["2330.TW", "2317.TW"]  # 台積電 / 鴻海

    while True:
        for s in stocks:
            check_stock(s)

        time.sleep(300)  # 每5分鐘

# 🚀 背景執行
threading.Thread(target=trading_bot).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
