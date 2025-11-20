#!/usr/bin/env python3
# NumberBot — Final Fixed Script (v5.1)
# Features:
# - fixes sqlite "Recursive use of cursors not allowed"
# - admin panel (web) with Bot ON/OFF
# - admin telegram control panel (buttons)
# - credit field forced to @ITS_ME_UNKNOW_USER
# - owner link in start message
#
# Requirements:
# pip install pyTelegramBotAPI Flask requests

import os
import sys
import sqlite3
import json
import requests
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, session
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ------------------ CONFIG ------------------
BOT_TOKEN = "8568307553:AAH7yorLpLbNAi8BoqzaGo5RRh1g-KHEi-4"  # already provided
ADMIN_ID = 8158657600
ADMIN_USERNAME = "ITS_ME_UNKNOW_USER"   # without @
ADMIN_PASSWORD = "nikhil123"            # web dashboard password
OWNER_ID = 8158657600
OWNER_USERNAME = "ITS_ME_UNKNOW_USER"
API_URL = "https://numapi.anshapi.workers.dev/?num="

DB_FILE = "numberbot_v5_fixed.db"
# ------------------ BOT CONTROL ------------------
BOT_ENABLED = True    # If False, bot replies that it's disabled
BOT_LOCKED = False    # If True, only admin can use the bot (telegram handlers will check)

# ------------------ APP & BOT ------------------
app = Flask(__name__)
app.secret_key = "supersecretkey123"  # change for production

bot = telebot.TeleBot(BOT_TOKEN)

# ------------------ DB HELPERS (no shared cursor) ------------------
def get_conn():
    """Return a fresh sqlite3 connection. Caller must close it."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            joined TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lookups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            number TEXT,
            time TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ------------------ HELPERS ------------------
def is_admin_user(user):
    """Check admin by id or username. Accepts telebot.User or integer id."""
    if isinstance(user, int):
        return user == ADMIN_ID
    # user is object
    uname = (user.username or "").lower()
    return user.id == ADMIN_ID or uname == ADMIN_USERNAME.lower()

def add_user(user):
    """Add user to users table if not exists (safe single-connection)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE id=?", (user.id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (id, name, username, joined) VALUES (?,?,?,?)",
                    (user.id, user.first_name, user.username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    conn.close()

def is_banned(uid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM bans WHERE user_id=?", (uid,))
    res = cur.fetchone()
    conn.close()
    return res is not None

def ban_user_db(uid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO bans (user_id) VALUES(?)", (uid,))
    conn.commit()
    conn.close()

def unban_user_db(uid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM bans WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()

def save_lookup_db(uid, number):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO lookups (user_id, number, time) VALUES (?,?,?)",
                (uid, number, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# ------------------ START / HELP / OWNER ------------------
@bot.message_handler(commands=['start'])
def start_cmd(msg):
    if not BOT_ENABLED:
        bot.reply_to(msg, "⚠️ Bot is currently disabled by admin.")
        return

    if BOT_LOCKED and not is_admin_user(msg.from_user):
        bot.reply_to(msg, "🔒 Bot is locked by admin. Only admin can use it now.")
        return

    add_user(msg.from_user)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}"))
    kb.add(InlineKeyboardButton("ℹ️ Help", callback_data="help_btn"))

    bot.send_message(msg.chat.id,
                     "👋 *Welcome to Number Info Bot !!🔝*\n\n"
                     "🔍 Send any mobile number and get  info ☠️.\n\n"
                     f"⚡ *Credit: @{ADMIN_USERNAME}*",
                     parse_mode="Markdown",
                     reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "help_btn")
def _cb_help(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,
                     "📖 *Help:* Send a number like `+919876543210` or `9876543210`.\n"
                     "Admin: /admin",
                     parse_mode="Markdown")

@bot.message_handler(commands=['help'])
def help_cmd(msg):
    bot.reply_to(msg, "📖 Send a phone number to get  info. Admin: /admin", parse_mode="Markdown")

@bot.message_handler(commands=['owner'])
def owner_cmd(msg):
    bot.reply_to(msg, f"👑 Owner: [Click Here](tg://user?id={OWNER_ID})", parse_mode="Markdown")

# ------------------ LOOKUP HANDLER ------------------
@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text.strip().replace("+","").isdigit())
def lookup_handler(msg):
    global BOT_ENABLED, BOT_LOCKED

    if not BOT_ENABLED:
        bot.reply_to(msg, "⚠️ Bot is currently disabled by admin.")
        return

    if BOT_LOCKED and not is_admin_user(msg.from_user):
        bot.reply_to(msg, "🔒 Bot is locked by admin. Only admin can use it right now.")
        return

    if is_banned(msg.from_user.id):
        bot.reply_to(msg, "🚫 You are banned from using this bot.")
        return

    number = msg.text.strip().replace("+","")
    bot.send_chat_action(msg.chat.id, "typing")

    # Call API (single request, can be replaced by multi-fallback if needed)
    try:
        r = requests.get(f"{API_URL}{number}", timeout=10)
        res = r.json() if r.status_code == 200 else None
    except Exception as e:
        res = None

    if not res:
        bot.reply_to(msg, "❌ No info found or API error.")
        return

    # Force credit replacement
    if isinstance(res, dict) and "credit" in res:
        res["credit"] = f"@{ADMIN_USERNAME}"

    # Save history
    try:
        save_lookup_db(msg.from_user.id, number)
    except Exception:
        # don't fail the whole handler on DB save error
        pass

    json_pretty = json.dumps(res, indent=4, ensure_ascii=False)
    bot.reply_to(msg, f"📦 *JSON Result:*\n```\n{json_pretty}\n```", parse_mode="Markdown")

# ------------------ ADMIN TELEGRAM PANEL ------------------
@bot.message_handler(commands=['admin'])
def admin_panel_telegram(msg):
    if not is_admin_user(msg.from_user):
        bot.reply_to(msg, "❌ Admin only.")
        return

    kb = InlineKeyboardMarkup()
    # Bot ON/OFF
    if BOT_ENABLED:
        kb.add(InlineKeyboardButton("🔴 Turn Bot OFF", callback_data="bot_off"))
    else:
        kb.add(InlineKeyboardButton("🟢 Turn Bot ON", callback_data="bot_on"))
    # Lock/Unlock
    if BOT_LOCKED:
        kb.add(InlineKeyboardButton("🔓 Unlock Bot", callback_data="unlock_bot"))
    else:
        kb.add(InlineKeyboardButton("🔒 Lock Bot", callback_data="lock_bot"))
    # Restart
    kb.add(InlineKeyboardButton("♻️ Restart Bot", callback_data="restart_bot"))
    kb.add(InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}"))

    bot.send_message(msg.chat.id, "🔐 *Admin Control Panel* — use buttons below", parse_mode="Markdown", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith(("bot_on","bot_off","lock_bot","unlock_bot","restart_bot")))
def admin_button_handler(call):
    global BOT_ENABLED, BOT_LOCKED

    # ensure only admin presses
    user = call.from_user
    if not is_admin_user(user):
        bot.answer_callback_query(call.id, "❌ Admin only", show_alert=True)
        return

    if call.data == "bot_off":
        BOT_ENABLED = False
        bot.answer_callback_query(call.id, "Bot turned OFF")
        bot.edit_message_text("🔴 Bot is now OFF.", call.message.chat.id, call.message.message_id)
        return

    if call.data == "bot_on":
        BOT_ENABLED = True
        bot.answer_callback_query(call.id, "Bot turned ON")
        bot.edit_message_text("🟢 Bot is now ON.", call.message.chat.id, call.message.message_id)
        return

    if call.data == "lock_bot":
        BOT_LOCKED = True
        bot.answer_callback_query(call.id, "Bot locked (only admin can use).")
        bot.edit_message_text("🔒 Bot locked. Only admin can use.", call.message.chat.id, call.message.message_id)
        return

    if call.data == "unlock_bot":
        BOT_LOCKED = False
        bot.answer_callback_query(call.id, "Bot unlocked.")
        bot.edit_message_text("🔓 Bot unlocked. Everyone can use.", call.message.chat.id, call.message.message_id)
        return

    if call.data == "restart_bot":
        bot.answer_callback_query(call.id, "Restarting bot...")
        bot.edit_message_text("♻ Restarting bot...", call.message.chat.id, call.message.message_id)
        # graceful restart
        os.execv(sys.executable, [sys.executable] + sys.argv)

# ------------------ ADMIN WEB DASHBOARD ------------------
@app.route('/login', methods=['GET','POST'])
def web_login():
    if request.method == 'POST':
        pw = request.form.get('password','')
        if pw == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect('/')
        return "Wrong password", 401
    return """<form method=post style='margin-top:120px;text-align:center;'>
              <input name=password type=password placeholder='Admin Password' />
              <button>Login</button></form>"""

@app.route('/logout')
def web_logout():
    session.pop('logged_in', None)
    return redirect('/login')

@app.route('/toggle_bot')
def web_toggle_bot():
    global BOT_ENABLED
    if 'logged_in' not in session:
        return redirect('/login')
    BOT_ENABLED = not BOT_ENABLED
    return redirect('/')

@app.route('/')
def dashboard():
    if 'logged_in' not in session:
        return redirect('/login')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM lookups")
    lookups = cur.fetchone()[0]
    conn.close()
    return render_template_string("""
    <html><head><title>NumberBot Admin</title>
    <style>
      body{font-family:Arial;color:#fff;background:#0b0b0b;text-align:center;padding-top:40px;}
      .card{background:#111;padding:20px;border-radius:12px;width:360px;margin: auto;box-shadow:0 0 20px rgba(0,200,255,0.1);}
      a{color:#0ff;text-decoration:none;}
    </style></head>
    <body>
      <div class='card'>
        <h2>⚙ NumberBot — Admin</h2>
        <p>👥 Users: <b>{{users}}</b></p>
        <p>🔍 Lookups: <b>{{lookups}}</b></p>
        <p>🤖 Bot Status: <b>{{bot_status}}</b></p>
        <a href="/toggle_bot">🔄 Toggle Bot (ON/OFF)</a><br/><br/>
        <a href="/logout">🚪 Logout</a>
      </div>
    </body></html>
    """, users=users, lookups=lookups, bot_status=("🟢 ON" if BOT_ENABLED else "🔴 OFF"))

# ------------------ WEBHOOK (optional) ------------------
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return "OK", 200

# ------------------ RUN ------------------
if __name__ == "__main__":
    print("🚀 NumberBot v5.1 starting — Bot Enabled:", BOT_ENABLED)
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("Interrupted, exiting.")