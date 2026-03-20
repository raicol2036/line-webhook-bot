import os
import time
import threading
import requests
import yfinance as yf
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import firebase_admin
from firebase_admin import credentials, firestore

# ====== LINE ======
LINE_CHANNEL_ACCESS_TOKEN = "你的token"
LINE_CHANNEL_SECRET = "你的secret"

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ====== Firebase ======
cred = credentials.Certificate("firebase-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)

# ====== 防重複通知 ======
last_alerts = {}

# ====== 取得股價（雙API保底） ======
def get_price(stock_id):
    try:
        stock_id = stock_id.replace(".TW", "")

        # 🥇 yfinance
        try:
            ticker = yf.Ticker(f"{stock_id}.TW")
            data = ticker.history(period="1d")

            if not data.empty:
                return float(data["Close"].iloc[-1])
        except:
            pass

        # 🥈 TWSE API
        try:
            url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw&json=1&delay=0"
            headers = {"User-Agent": "Mozilla/5.0"}

            res = requests.get(url, headers=headers, timeout=5).json()

            if res.get("msgArray"):
                data = res["msgArray"][0]
                price = data.get("z")

                if price and price != "-":
                    return float(price)
        except:
            pass

        return None

    except Exception as e:
        print("price error:", e)
        return None


# ====== 分析 ======
def analyze(stock_id, cost):
    price = get_price(stock_id)

    if price is None:
        return None, "❌ 無法取得價格"

    change = (price - cost) / cost * 100

    if change <= -10:
        return price, "🚨 停損"
    elif change >= 20:
        return price, "💰 停利"
    elif change < 0:
        return price, "⚠️ 觀察"
    else:
        return price, "✅ 持有"


# ====== 自動監控 ======
def monitor():
    while True:
        try:
            users = db.collection("stocks").stream()

            for user in users:
                user_id = user.id
                stocks = user.to_dict()

                for stock_id, data in stocks.items():
                    cost = float(data["cost"])

                    price, action = analyze(stock_id, cost)

                    if price is None:
                        continue

                    change = (price - cost) / cost * 100
                    key = f"{user_id}_{stock_id}"

                    # 🔥 防重複通知
                    if action in ["🚨 停損", "💰 停利"]:
                        if last_alerts.get(key) == action:
                            continue

                        msg = f"""📊 {stock_id}
現價：{price:.2f}
成本：{cost}
報酬：{change:.1f}%
👉 {action}"""

                        line_bot_api.push_message(user_id, TextSendMessage(text=msg))
                        last_alerts[key] = action

        except Exception as e:
            print("monitor error:", e)

        time.sleep(60)


# ====== Webhook ======
@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print("webhook error:", e)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id

    # ===== 新增 =====
    if text.startswith("新增"):
        parts = text.split()

        if len(parts) < 3:
            reply = "❌ 用法：新增 2330 600"
        else:
            stock_id = parts[1].replace(".TW", "")
            cost = float(parts[2])

            db.collection("stocks").document(user_id).set({
                stock_id: {"cost": cost}
            }, merge=True)

            reply = f"✅ 已新增 {stock_id}"

    # ===== 持股 =====
    elif text == "持股":
        doc = db.collection("stocks").document(user_id).get()

        if not doc.exists:
            reply = "目前沒有持股"
        else:
            stocks = doc.to_dict()
            reply = "📊 持股\n\n"

            for stock_id, data in stocks.items():
                cost = float(data["cost"])
                price, action = analyze(stock_id, cost)

                if price is None:
                    reply += f"""📊 {stock_id}
成本：{cost}
❌ 無法取得價格

"""
                else:
                    change = (price - cost) / cost * 100

                    reply += f"""📊 {stock_id}
成本：{cost}
現價：{price:.2f}
報酬：{change:.1f}%
👉 {action}

"""

    # ===== 分析 =====
    elif text.startswith("分析"):
        parts = text.split()

        if len(parts) < 2:
            reply = "❌ 用法：分析 2330"
        else:
            stock_id = parts[1].replace(".TW", "")
            price = get_price(stock_id)

            if price is None:
                reply = f"❌ {stock_id} 抓不到資料"
            else:
                reply = f"""📊 {stock_id}
現價：{price:.2f}"""

    else:
        reply = "指令：新增 / 持股 / 分析"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


# ====== 啟動 ======
def start_monitor():
    t = threading.Thread(target=monitor)
    t.daemon = True
    t.start()


start_monitor()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
