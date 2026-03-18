from flask import Flask, request
import requests
import os

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_TOKEN")

@app.route("/webhook", methods=['POST'])
def webhook():
    data = request.json

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

    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
