import os
import json
import requests
from flask import Flask, request, render_template_string, redirect, session
from datetime import datetime
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

# ---------------- CONFIG ----------------
BOT_TOKEN = "8568307553:AAH7yorLpLbNAi8BoqzaGo5RRh1g-KHEi-4"
ADMIN_ID = 8158657600
ADMIN_USERNAME = "ITS_ME_UNKNOW_USER"
ADMIN_PASSWORD = "nikhil123"
OWNER_ID = 8158657600
OWNER_USERNAME = "ITS_ME_UNKNOW_USER"

API_URL = "https://numapi.anshapi.workers.dev/?num="

MONGO_URI = "PASTE_MONGO_CONNECTION_STRING"
client = MongoClient(MONGO_URI)
db = client["numberbot"]
users = db.users
lookups = db.lookups
bans = db.bans

BOT_ENABLED = True
BOT_LOCKED = False

app = Flask(__name__)
app.secret_key = "supersecretkey123"

bot = telebot.TeleBot(BOT_TOKEN)

# --------- Helpers ----------
def is_admin_user(user):
    if isinstance(user, int):
        return user == ADMIN_ID
    return user.id == ADMIN_ID or (user.username or "").lower() == ADMIN_USERNAME.lower()

def add_user(u):
    if users.find_one({"_id": u.id}) is None:
        users.insert_one({
            "_id": u.id,
            "name": u.first_name,
            "username": u.username,
            "joined": datetime.now()
        })

def is_banned(uid):
    return bans.find_one({"_id": uid}) is not None

def save_lookup(uid, number):
    lookups.insert_one({
        "user_id": uid,
        "number": number,
        "time": datetime.now()
    })

# ---------------- START ----------------
@bot.message_handler(commands=['start'])
def start_cmd(msg):
    global BOT_ENABLED, BOT_LOCKED

    if not BOT_ENABLED:
        bot.reply_to(msg, "⚠️ Bot disabled by admin.")
        return

    if BOT_LOCKED and not is_admin_user(msg.from_user):
        bot.reply_to(msg, "🔒 Bot locked by admin.")
        return

    add_user(msg.from_user)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}"))
    kb.add(InlineKeyboardButton("ℹ️ Help", callback_data="help_btn"))

    bot.send_message(
        msg.chat.id,
        "👋 *Welcome to Number Info Bot*\n"
        "🔍 Send any Indian mobile number to get info.\n"
        f"⚡ *Credit:* @{ADMIN_USERNAME}",
        parse_mode="Markdown",
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "help_btn")
def _cb_help(call):
    bot.send_message(call.message.chat.id,
                     "📘 *Help:* Just send any phone number.\nAdmin: /admin",
                     parse_mode="Markdown")

# -------------- LOOKUP ----------------
@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text.strip().replace("+", "").isdigit())
def lookup_handler(msg):
    global BOT_ENABLED, BOT_LOCKED

    if not BOT_ENABLED:
        bot.reply_to(msg, "⚠️ Bot is OFF by admin.")
        return

    if BOT_LOCKED and not is_admin_user(msg.from_user):
        bot.reply_to(msg, "🔒 Only admin can use bot.")
        return

    if is_banned(msg.from_user.id):
        bot.reply_to(msg, "🚫 You are banned.")
        return

    number = msg.text.strip().replace("+","")
    bot.send_chat_action(msg.chat.id, "typing")

    try:
        r = requests.get(f"{API_URL}{number}", timeout=10)
        res = r.json() if r.status_code == 200 else None
    except:
        res = None

    if not res:
        bot.reply_to(msg, "❌ API error or no data found.")
        return

    res["credit"] = f"@{ADMIN_USERNAME}"
    save_lookup(msg.from_user.id, number)

    json_pretty = json.dumps(res, indent=4, ensure_ascii=False)
    bot.reply_to(msg, f"📦 *JSON Result:*\n```\n{json_pretty}\n```",
                 parse_mode="Markdown")

# ---------- ADMIN PANEL --------------
@bot.message_handler(commands=['admin'])
def admin_panel(msg):
    if not is_admin_user(msg.from_user):
        bot.reply_to(msg, "❌ Admin only.")
        return

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("On/Off Bot", callback_data="toggle_bot"))
    kb.add(InlineKeyboardButton("Lock/Unlock Bot", callback_data="toggle_lock"))

    bot.send_message(msg.chat.id, "🔐 *Admin Panel*", parse_mode="Markdown", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["toggle_bot", "toggle_lock"])
def admin_buttons(call):
    global BOT_ENABLED, BOT_LOCKED

    if not is_admin_user(call.from_user):
        bot.answer_callback_query(call.id, "Admin only!", show_alert=True)
        return

    if call.data == "toggle_bot":
        BOT_ENABLED = not BOT_ENABLED
        bot.answer_callback_query(call.id, "Bot status toggled")

    if call.data == "toggle_lock":
        BOT_LOCKED = not BOT_LOCKED
        bot.answer_callback_query(call.id, "Bot lock toggled")

# ----------- WEB DASHBOARD ----------
@app.route('/login', methods=['GET','POST'])
def web_login():
    if request.method == 'POST':
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect('/')
        return "Wrong password"
    return "<form method=post><input name=password type=password /><button>Login</button></form>"

@app.route('/')
def dashboard():
    if "admin" not in session:
        return redirect('/login')
    return f"""
    <h2>NumberBot Admin</h2>
    <p>Users: {users.count_documents({})}</p>
    <p>Lookups: {lookups.count_documents({})}</p>
    <p>Status: {"🟢 ON" if BOT_ENABLED else "🔴 OFF"}</p>
    <a href='/toggle'>Toggle Bot</a><br><br>
    <a href='/logout'>Logout</a>
    """

@app.route('/toggle')
def toggle():
    global BOT_ENABLED
    if "admin" not in session:
        return redirect('/login')
    BOT_ENABLED = not BOT_ENABLED
    return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ---------- WEBHOOK ------------
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.data.decode('utf-8'))
    bot.process_new_updates([update])
    return "OK", 200

# ---- EXPORT FOR VERCEL ----
app = app