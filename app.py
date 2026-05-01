import os
import logging
from flask import Flask, request, abort, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient, Configuration, MessagingApi,
    ReplyMessageRequest, TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent, TextMessageContent,
    FollowEvent, UnfollowEvent, PostbackEvent,
)
from google import genai
from google.genai import types as genai_types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET")
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
GEMINI_API_KEY       = os.environ.get("GEMINI_API_KEY")

if not CHANNEL_SECRET:       raise RuntimeError("LINE_CHANNEL_SECRET is not set")
if not CHANNEL_ACCESS_TOKEN: raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN is not set")
if not GEMINI_API_KEY:       raise RuntimeError("GEMINI_API_KEY is not set")

handler     = WebhookHandler(CHANNEL_SECRET)
line_config = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

GEMINI_MODEL  = "gemini-2.0-flash-lite"
SYSTEM_PROMPT = (
    "คุณเป็น AI chatbot ผู้ช่วยสำหรับร้านค้าออนไลน์ไทย "
    "ตอบภาษาไทยเป็นหลัก สุภาพ กระชับ และเป็นมิตร "
    "ถ้าถามเป็นภาษาอังกฤษให้ตอบเป็นภาษาอังกฤษ"
)

conversation_history: dict[str, list[dict]] = {}
MAX_HISTORY = 10

def get_gemini_reply(user_id: str, user_text: str) -> str:
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    conversation_history[user_id].append(
        {"role": "user", "parts": [{"text": user_text}]}
    )
    if len(conversation_history[user_id]) > MAX_HISTORY * 2:
        conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY * 2:]
    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=conversation_history[user_id],
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=1000,
            ),
        )
        reply_text = response.text or "ขออภัย ไม่สามารถตอบได้ในขณะนี้"
        conversation_history[user_id].append(
            {"role": "model", "parts": [{"text": reply_text}]}
        )
        return reply_text
    except Exception as e:
        logger.error("Gemini error: %s", e)
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

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/", methods=["GET"])
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
        reply = get_gemini_reply(user_id, text)
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
