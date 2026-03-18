from flask import Flask, request
import requests
import os
import threading

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_TOKEN")

@app.route("/webhook", methods=['POST'])
def webhook():
    data = request.json

    # ⭐ 先立即回應（最重要）
    def process():
        try:
            if 'events' in data:
                for event in data['events']:
                    if event['type'] == 'message':
                        user_id = event['source']['userId']
                        reply_token = event['replyToken']

                        print("USER_ID:", user_id)

                        url = 'https://api.line.me/v2/bot/message/reply'
                        headers = {
                            'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
                            'Content-Type': 'application/json'
                        }
                        body = {
                            'replyToken': reply_token,
                            'messages': [{
                                'type': 'text',
                                'text': f'你的USER_ID是: {user_id}'
                            }]
                        }

                        requests.post(url, headers=headers, json=body)
        except Exception as e:
            print("Error:", e)

    threading.Thread(target=process).start()

    return "OK", 200
def send_line_message(text):
    url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    body = {
        "to": "U4e491f83955e58fa292d0082ff332eaa",
        "messages":[
            {
                "type":"text",
                "text": text
            }
        ]
    }

    requests.post(url, headers=headers, json=body)
send_line_message("🚀 Trading Bot 上線成功！")
