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
BOT_TOKEN = "8176866898:AAEhQ_HV2TFyINRxfu2rGYbw3oDSkTNNUEg"
ADMIN_ID = 8158657600
ADMIN_USERNAME = "ITS_ME_UNKNOW_USER"
ADMIN_PASSWORD = "nikhil123"
OWNER_ID = 8158657600
OWNER_USERNAME = "ITS_ME_UNKNOW_USER"

API_URL = "https://numapi.anshapi.workers.dev/?num="

DB_FILE = "numberbot_v5_fixed.db"

BOT_ENABLED = True
BOT_LOCKED = False

# ------------------ APP & BOT ------------------
app = Flask(__name__)
app.secret_key = "supersecretkey123"
bot = telebot.TeleBot(BOT_TOKEN)

# ------------------ DB HELPERS ------------------
def get_conn():
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
    if isinstance(user, int):
        return user == ADMIN_ID
    uname = (user.username or "").lower()
    return user.id == ADMIN_ID or uname == ADMIN_USERNAME.lower()

def add_user(user):
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

def save_lookup_db(uid, number):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO lookups (user_id, number, time) VALUES (?,?,?)",
                (uid, number, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# ------------------ START CMD ------------------
@bot.message_handler(commands=['start'])
def start_cmd(msg):
    if not BOT_ENABLED:
        bot.reply_to(msg, "⚠️ Bot is currently disabled by admin.")
        return

    if BOT_LOCKED and not is_admin_user(msg.from_user):
        bot.reply_to(msg, "🔒 Bot is locked by admin.")
        return

    add_user(msg.from_user)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}"))
    kb.add(InlineKeyboardButton("ℹ️ Help", callback_data="help_btn"))

    bot.send_message(
        msg.chat.id,
        "👋 *Welcome to Number Info Bot !!*\n\n"
        "🔍 Send any mobile number and get info.\n\n"
        f"⚡ *Credit: @{ADMIN_USERNAME}*",
        parse_mode="Markdown",
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "help_btn")
def _cb_help(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,
                     "📖 *Help:* Send a number like `9876543210`\nAdmin: /admin",
                     parse_mode="Markdown")

# ------------------ LOOKUP HANDLER (API FULL INTEGRATED) ------------------
@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text.strip().replace("+","").isdigit())
def lookup_handler(msg):
    global BOT_ENABLED, BOT_LOCKED

    if not BOT_ENABLED:
        bot.reply_to(msg, "❌ Bot disabled.")
        return

    if BOT_LOCKED and not is_admin_user(msg.from_user):
        bot.reply_to(msg, "🔒 Bot locked.")
        return

    if is_banned(msg.from_user.id):
        bot.reply_to(msg, "🚫 You are banned.")
        return

    number = msg.text.strip().replace("+","")
    bot.send_chat_action(msg.chat.id, "typing")

    # API request
    try:
        r = requests.get(f"{API_URL}{number}", timeout=10)
        data = r.json() if r.status_code == 200 else None
    except:
        data = None

    if not data:
        bot.reply_to(msg, "❌ API error or no data.")
        return

    # Force credit replace
    if "credit" in data:
        data["credit"] = "@ITS_ME_UNKNOW_USER"

    try:
        save_lookup_db(msg.from_user.id, number)
    except:
        pass

    formatted = json.dumps(data, indent=4, ensure_ascii=False)

    bot.reply_to(msg,
                 f"📦 *JSON Result:*\n```\n{formatted}\n```",
                 parse_mode="Markdown")

# ------------------ ADMIN PANEL TG ------------------
@bot.message_handler(commands=['admin'])
def admin_panel_telegram(msg):
    if not is_admin_user(msg.from_user):
        bot.reply_to(msg, "❌ Admin only.")
        return

    kb = InlineKeyboardMarkup()

    kb.add(InlineKeyboardButton("🟢 Bot ON" if not BOT_ENABLED else "🔴 Bot OFF",
                                callback_data="toggle_bot"))
    kb.add(InlineKeyboardButton("🔒 Lock Bot" if not BOT_LOCKED else "🔓 Unlock Bot",
                                callback_data="toggle_lock"))
    kb.add(InlineKeyboardButton("♻ Restart Bot", callback_data="restart"))
    kb.add(InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}"))

    bot.send_message(msg.chat.id, "🔐 *Admin Control Panel*", parse_mode="Markdown", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data in ["toggle_bot", "toggle_lock", "restart"])
def admin_actions(call):
    global BOT_ENABLED, BOT_LOCKED

    if not is_admin_user(call.from_user):
        bot.answer_callback_query(call.id, "❌ Not allowed", show_alert=True)
        return

    if call.data == "toggle_bot":
        BOT_ENABLED = not BOT_ENABLED
        bot.edit_message_text(f"Bot Status: {'🟢 ON' if BOT_ENABLED else '🔴 OFF'}",
                              call.message.chat.id, call.message.message_id)
        return

    if call.data == "toggle_lock":
        BOT_LOCKED = not BOT_LOCKED
        bot.edit_message_text(f"Bot Lock: {'🔒 LOCKED' if BOT_LOCKED else '🔓 UNLOCKED'}",
                              call.message.chat.id, call.message.message_id)
        return

    if call.data == "restart":
        bot.edit_message_text("♻ Restarting...", call.message.chat.id, call.message.message_id)
        os.execv(sys.executable, [sys.executable] + sys.argv)

# ------------------ WEB DASHBOARD ------------------
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
    </style></head>
    <body>
      <div class='card'>
        <h2>⚙ NumberBot — Admin</h2>
        <p>👥 Users: <b>{{users}}</b></p>
        <p>🔍 Lookups: <b>{{lookups}}</b></p>
        <p>🤖 Bot Status: <b>{{status}}</b></p>
        <a href="/toggle">🔄 Toggle Bot</a><br/><br/>
        <a href="/logout">🚪 Logout</a>
      </div>
    </body></html>
    """, users=users, lookups=lookups, status="🟢 ON" if BOT_ENABLED else "🔴 OFF")

@app.route('/toggle')
def toggle_web():
    global BOT_ENABLED
    if 'logged_in' not in session:
        return redirect('/login')
    BOT_ENABLED = not BOT_ENABLED
    return redirect('/')

@app.route('/logout')
def lo():
    session.pop('logged_in', None)
    return redirect('/login')

# ------------------ WEBHOOK ------------------
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return "OK", 200

# ------------------ RUN ------------------
if __name__ == "__main__":
    print("🚀 NumberBot v5.1 starting…")
    bot.infinity_polling()