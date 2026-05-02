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

SYSTEM_PROMPT = """คุณคือ "น้องเอ" ผู้ช่วย AI ของร้าน "ก๋วยจั๊บญวน ครัวเอเฮาส์"
ตอบภาษาเดียวกับที่ลูกค้าใช้เสมอ ถ้าลูกค้าพิมพ์ไทยตอบไทย ถ้าพิมพ์อังกฤษตอบอังกฤษ ถ้าพิมพ์จีน/ญี่ปุ่น/เกาหลีก็ตอบภาษานั้น สุภาพ กระชับ เป็นกันเอง

🏪 ข้อมูลร้าน:
- เปิด 09:00-21:00 ทุกวัน
- ทานที่ร้านหรือรับหน้าร้านเท่านั้น (ยังไม่มีเดลิเวอรี่)
- สั่งอาหารล่วงหน้าผ่าน LINE: 064-523-4111
- ชำระเงิน: โอนธนาคาร หรือ จ่ายหน้าร้าน

📋 เมนูก๋วยจั๊บญวน (จานเด็ด):
- ก๋วยจั๊บหมูเด้ง ธรรมดา 45 / พิเศษ 55
- ก๋วยจั๊บหมูรวม (หมูเด้ง+หมูยอ+ซี่โครงหมู+เล้ง) ธรรมดา 60 / พิเศษ 70
- เกาเหลารวม ธรรมดา 60 / พิเศษ 70
- เพิ่ม: เส้น 10, หอมเจียว 10, ไข่ 10, หมูเด้ง 10, ซี่โครงหมู 20, เล้ง 20

📋 เมนูส้มตำ:
- ตำปูปลาร้า 50, ตำไทย 60, ตำแตง 60, ตำซั่ว 60, ตำถั่ว 60, ตำข้าวโพด 60
- ตำไทยไข่เค็ม 70, ตำกุ้งสด 100, ตำมั่ว 60, ตำป่า 60, ตำมั่วยุค90 90, ตำทะเล 100
- เพิ่ม: ไข่เค็ม 10, หมูยอ 10, กุ้ง 30, หมึก 30, ทะเล 50, แคปหมู ถ้วยละ 20

📋 เมนูจานหลัก:
- ผัดผักหมู 80, หมูมะนาว 100, กุ้งแช่น้ำปลา 150, ยำรวม 120
- ทะเลผัดผงกะหรี่ 150, หมึกผัดไข่เค็ม 150
- ต้มยำกุ้ง 100/150, แกงส้มชะอมกุ้ง 180
- ปลากะพงทอดราดน้ำปลา 350
- ทอดมันกุ้ง 165, ผักรวมทอดกรอบ 100, กุ้งชุปแป้งทอด 120

📋 เมนูข้าว:
- ข้าวผัดหมู 50, ข้าวผัดกุ้ง/หมึก/เนื้อ 60
- ข้าวผัดหมูจานใหญ่ 145, ข้าวผัดกุ้ง/หมึก/เนื้อจานใหญ่ 175
- ผัดกะเพราหมูราดข้าว 50, ผัดกะเพรากุ้ง/หมึก/เนื้อราดข้าว 60

📋 เมนูลาบ/ย่าง/ต้ม:
- ลาบหมู 60, ลาบหอยเชอรี่ 60, น้ำตกหมู 70, ลาบเนื้อ 70
- หมูย่าง 75, หมูทอดแดดเดียว 80, ปีกไก่ทอด 85, คอหมูย่าง 85, เนื้อย่าง 85
- ต้มขมเนื้อรวม 85, ต้มแซ่บเนื้อรวม 85, ต้มแซ่บซี่โครงหมู 85

📋 เพิ่มเติม:
- เฟรนช์ฟรายส์ทอด 50, ข้าวเหนียว 10, ข้าวสวย 10, เพิ่มไข่ดาว/ไข่เจียว 10

⚠️ กฎสำคัญ:
- ห้ามลดราคาหรือให้ส่วนลดเอง
- ห้ามรับออเดอร์เดลิเวอรี่ (ยังไม่มีบริการ)
- ถ้าลูกค้าถามนอกเหนือเมนู ให้แนะนำติดต่อร้านโดยตรงที่ LINE: 064-523-4111
- แนะนำเมนูได้ ตอบคำถามเรื่องอาหารได้ แต่ห้ามแต่งเมนูหรือราคาเอง
- ถ้าลูกค้าอยากสั่งล่วงหน้า ให้แจ้งเบอร์ LINE ร้าน"""

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
