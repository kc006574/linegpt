import os
import sqlite3
import datetime
from flask import Flask, request, abort, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import openai

app = Flask(__name__)

# 從環境變數讀取金鑰
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET or not OPENAI_API_KEY:
    raise Exception("請先設定環境變數：LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, OPENAI_API_KEY")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

# 初始化 SQLite 資料庫（若不存在則建立）
def init_db():
    conn = sqlite3.connect("reminders.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            time TEXT,
            message TEXT,
            periodic INTEGER DEFAULT 0,
            recurrence TEXT DEFAULT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# LINE Webhook 入口
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# 處理 LINE 傳入的訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    user_id = event.source.user_id

    if text.startswith("!提醒"):
        response = handle_reminder_command(user_id, text)
    else:
        response = chatgpt_reply(text)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=response)
    )

# 處理提醒指令
def handle_reminder_command(user_id, text):
    # 指令範例：
    # 新增一次提醒： !提醒 add 08:00 吃早餐
    # 新增週期提醒： !提醒 add-periodic daily 08:00 吃早餐
    #                或 !提醒 add-periodic weekly 08:00 吃早餐
    # 刪除提醒：       !提醒 delete 1
    # 查詢提醒：       !提醒 list
    parts = text.split()
    if len(parts) < 2:
        return "指令格式錯誤。請使用：!提醒 add|add-periodic|delete|list"
    command = parts[1].lower()
    if command == "add" and len(parts) >= 4:
        time_str = parts[2]
        msg = " ".join(parts[3:])
        conn = sqlite3.connect("reminders.db")
        c = conn.cursor()
        c.execute("INSERT INTO reminders (user_id, time, message, periodic) VALUES (?, ?, ?, ?)",
                  (user_id, time_str, msg, 0))
        conn.commit()
        conn.close()
        return f"已新增提醒: {time_str} {msg}"
    elif command == "add-periodic" and len(parts) >= 5:
        recurrence = parts[2].lower()  # daily 或 weekly
        if recurrence not in ["daily", "weekly"]:
            return "週期性提醒請輸入 daily 或 weekly"
        time_str = parts[3]
        msg = " ".join(parts[4:])
        conn = sqlite3.connect("reminders.db")
        c = conn.cursor()
        c.execute("INSERT INTO reminders (user_id, time, message, periodic, recurrence) VALUES (?, ?, ?, ?, ?)",
                  (user_id, time_str, msg, 1, recurrence))
        conn.commit()
        conn.close()
        return f"已新增 {recurrence} 提醒: {time_str} {msg}"
    elif command == "delete" and len(parts) == 3:
        reminder_id = parts[2]
        conn = sqlite3.connect("reminders.db")
        c = conn.cursor()
        c.execute("DELETE FROM reminders WHERE id=? AND user_id=?", (reminder_id, user_id))
        conn.commit()
        affected = c.rowcount
        conn.close()
        if affected:
            return f"已刪除提醒 ID: {reminder_id}"
        else:
            return f"找不到提醒 ID: {reminder_id}"
    elif command == "list":
        conn = sqlite3.connect("reminders.db")
        c = conn.cursor()
        c.execute("SELECT id, time, message, periodic, recurrence FROM reminders WHERE user_id=?", (user_id,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            retu
