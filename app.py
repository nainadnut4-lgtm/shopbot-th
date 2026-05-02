import os
import logging
import requests
from flask import Flask, request, abort, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient, Configuration, MessagingApi,
    ReplyMessageRequest, TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent, TextMessageContent,
    FollowEvent, UnfollowEvent,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
GROQ_API_KEY         = os.environ.get("GROQ_API_KEY")

if not CHANNEL_SECRET:       raise RuntimeError("LINE_CHANNEL_SECRET is not set")
if not CHANNEL_ACCESS_TOKEN: raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN is not set")
if not GROQ_API_KEY:         raise RuntimeError("GROQ_API_KEY is not set")

handler     = WebhookHandler(CHANNEL_SECRET)
line_config = Configuration(access_token=CHANNEL_ACCESS_TOKEN)

SYSTEM_PROMPT = (
    "คุณเป็น AI chatbot ผู้ช่วยสำหรับร้านค้าออนไลน์ไทย "
    "ตอบภาษาไทยเป็นหลัก สุภาพ กระชับ และเป็นมิตร "
    "ถ้าถามเป็นภาษาอังกฤษให้ตอบเป็นภาษาอังกฤษ"
)

conversation_history: dict[str, list[dict]] = {}
MAX_HISTORY = 10

def get_ai_reply(user_id: str, user_text: str) -> str:
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    conversation_history[user_id].append({"role": "user", "content": user_text})
    if len(conversation_history[user_id]) > MAX_HISTORY * 2:
        conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY * 2:]
    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history[user_id]
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.1-8b-instant", "messages": messages, "max_tokens": 1000},
            timeout=30,
        )
        data = resp.json()
        reply_text = data["choices"][0]["message"]["content"]
        conversation_history[user_id].append({"role": "assistant", "content": reply_text})
        return reply_text
    except Exception as e:
        logger.error("AI error: %s", e)
        conversation_history[user_id].pop()
        return "ขออภัย เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้งครับ"

def get_messaging_api():
    return MessagingApi(ApiClient(line_config))

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK", 200

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/")
def index():
    return jsonify({"service": "ShopBotTH", "status": "running"}), 200

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    user_id = event.source.user_id
    text    = event.message.text
    if text.strip().lower() in ("reset", "/reset", "รีเซ็ต"):
        conversation_history.pop(user_id, None)
        reply = "รีเซ็ตแล้วครับ เริ่มใหม่ได้เลย! 🔄"
    else:
        reply = get_ai_reply(user_id, text)
    get_messaging_api().reply_message(
        ReplyMessageRequest(reply_token=event.reply_token,
                            messages=[TextMessage(text=reply)])
    )

@handler.add(FollowEvent)
def handle_follow(event):
    conversation_history.pop(event.source.user_id, None)
    get_messaging_api().reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=(
                "สวัสดีครับ! ยินดีต้อนรับ 🎉\n"
                "ฉันคือ AI ผู้ช่วยของร้านนี้\n"
                "มีอะไรให้ช่วยบอกได้เลยครับ!\n\n"
                "พิมพ์ reset เพื่อเริ่มการสนทนาใหม่"
            ))]
        )
    )

@handler.add(UnfollowEvent)
def handle_unfollow(event):
    conversation_history.pop(event.source.user_id, None)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
