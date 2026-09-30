# ============================================================
# 👑 BAAP HOSTING | ROYAL TERMINAL — No-Sleep Edition
# ============================================================

import os
import sys
import json
import time
import threading
import subprocess
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import telebot
from telebot import types
import psutil

# ----------------- 🔑 CREDENTIALS -----------------
BOT_TOKEN = "8606831697:AAG4-jhExcDscpX0FO4nuaFssGcYqA4Kmig"
OWNER_ID = 8663186943

# ----------------- 🌐 RENDER URL (yahan apna URL daalo) -----------------
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
# Render automatically RENDER_EXTERNAL_URL env var deta hai.
# Agar manually set karna ho: os.environ.get("RENDER_URL", "https://your-app.onrender.com")

SELF_PING_INTERVAL = 240  # 4 minute (Render 15 min pe sulaata hai, isse pehle ping)

# ----------------- 🌐 HEALTH SERVER -----------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        if self.path == "/health":
            self.wfile.write(b"OK - BAAP HOSTING HEALTHY")
        else:
            self.wfile.write(b"BAAP HOSTING is ALIVE and KICKING!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"🌐 Health server running on port {port}")
    server.serve_forever()

# ----------------- 🔄 SELF-PING (No-Sleep Core) -----------------
def self_ping_loop():
    """
    Har 4 minute me apne aap ko ping karta hai.
    Render ka 15-min sleep timer reset ho jata hai.
    """
    time.sleep(60)  # Pehle 1 min wait taaki server ready ho
    while True:
        if not RENDER_URL:
            print("[SELF-PING] RENDER_URL not set, skipping ping.")
        else:
            try:
                req = urllib.request.Request(f"{RENDER_URL}/health", method="GET")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    print(f"[SELF-PING] ✅ {time.strftime('%H:%M:%S')} — Status: {resp.status}")
            except Exception as e:
                print(f"[SELF-PING] ❌ {time.strftime('%H:%M:%S')} — Error: {e}")
        time.sleep(SELF_PING_INTERVAL)

# ----------------- 🩺 BOT ACTIVITY WATCHER -----------------
last_activity = {"time": time.time()}

def bot_activity_watcher():
    """
    Agar bot 10 min se idle hai, force self-ping karo.
    """
    while True:
        time.sleep(600)  # 10 min
        idle = time.time() - last_activity["time"]
        if idle > 600 and RENDER_URL:
            try:
                req = urllib.request.Request(f"{RENDER_URL}/health", method="GET")
                urllib.request.urlopen(req, timeout=15)
                print(f"[WATCHER] Bot idle {int(idle)}s — forced ping sent.")
            except Exception as e:
                print(f"[WATCHER] Ping failed: {e}")

# ----------------- 🤖 BOT INIT -----------------
bot = telebot.TeleBot(BOT_TOKEN)

USERS_FILE = "allowed_users.json"
CONFIG_FILE = "bot_config.json"
MAX_CHANNELS = 10

current_dir = os.getcwd()
bg_processes = {}
waiting_for_channel_forward = set()
pending_requests = set()

START_TIME = time.time()

# ----------------- ESCAPE HELPERS -----------------
def escape_markdown(text):
    if not text:
        return ""
    for ch in ['*', '_', '`', '[']:
        text = text.replace(ch, f"\\{ch}")
    return text

# ----------------- STORAGE HELPERS -----------------
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return {OWNER_ID}
    return {OWNER_ID}

def save_users(users_set):
    with open(USERS_FILE, "w") as f:
        json.dump(list(users_set), f)

def load_config():
    default_config = {"required_channels": []}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                if "required_channel_id" in data and data["required_channel_id"]:
                    data["required_channels"] = [{
                        "id": data["required_channel_id"],
                        "title": data.get("required_channel_title") or "Required Channel",
                        "username": data.get("required_channel_username"),
                        "invite_link": data.get("required_channel_invite_link")
                    }]
                if "required_channels" not in data:
                    data["required_channels"] = []
                return data
        except Exception:
            return default_config
    return default_config

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)

allowed_users = load_users()
bot_config = load_config()

# ----------------- VERIFICATION HELPERS -----------------
def is_owner(user_id):
    return user_id == OWNER_ID

def is_allowed_user(user_id):
    return user_id in allowed_users or user_id == OWNER_ID

def check_channel_subscriptions(user_id):
    if is_owner(user_id):
        return True, []
    channels = bot_config.get("required_channels", [])
    if not channels:
        return True, []
    missing = []
    for ch in channels:
        ch_id = ch.get("id")
        try:
            member = bot.get_chat_member(ch_id, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                missing.append(ch)
        except Exception as e:
            print(f"[!] Error checking channel {ch_id}: {e}")
            missing.append(ch)
    return (len(missing) == 0), missing

def get_join_channels_keyboard(missing_channels):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for i, ch in enumerate(missing_channels, 1):
        link = ch.get("invite_link")
        title = ch.get("title", f"Channel {i}")
        if link:
            markup.add(types.InlineKeyboardButton(f"📢 Join {title}", url=link))
    markup.add(types.InlineKeyboardButton("🔄 Verify Membership", callback_data="verify_membership"))
    return markup

def get_uptime():
    uptime_seconds = int(time.time() - START_TIME)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    return f"{days}d {hours}h {minutes}m {seconds}s"

# ----------------- UI / KEYBOARDS -----------------
def get_main_menu_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_status = types.InlineKeyboardButton("⏳ Status", callback_data="btn_status")
    btn_vitals = types.InlineKeyboardButton("🧬 Vitals", callback_data="btn_sysinfo")
    btn_ram = types.InlineKeyboardButton("🧠 RAM", callback_data="btn_memory")
    btn_disk = types.InlineKeyboardButton("💽 Disk", callback_data="btn_disk")
    btn_ps = types.InlineKeyboardButton("⚙️ Engines (PS)", callback_data="btn_ps")
    btn_myid = types.InlineKeyboardButton("🪪 My ID", callback_data="btn_myid")
    btn_help = types.InlineKeyboardButton("📖 Help Guide", callback_data="btn_help")
    markup.add(btn_status, btn_vitals)
    markup.add(btn_ram, btn_disk)
    markup.add(btn_ps, btn_myid)
    if is_owner(user_id):
        btn_channel = types.InlineKeyboardButton("📢 Channel Manager", callback_data="btn_channel_info")
        btn_users = types.InlineKeyboardButton("👥 Users List", callback_data="btn_list_users")
        markup.add(btn_channel, btn_users)
    markup.add(btn_help)
    return markup

def get_back_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="btn_main_menu"))
    return markup

def get_help_text():
    channels = bot_config.get("required_channels", [])
    count = len(channels)
    return f"""👑 *BAAP HOSTING | ROYAL TERMINAL* 👑
*═════════════════════════*
Welcome to the king's system. You have full terminal access. 🚀

💻 *TERMINAL ACTIONS:*
▪️ Direct commands (`ls`, `mkdir`, `git status`)
▪️ `cd <dir>` - Switch active directory 📂
▪️ `pip install <pkg>` - Install Python package 💉
▪️ `python <script.py>` - Execute scripts 🔥

🗂 *FILE OPERATIONS:*
▪️ Send document directly to bot - Uploads to active dir 📤
▪️ `/download <filename>` - Download file from server 📥

⚙️ *BACKGROUND ENGINES:*
▪️ `/run <cmd>` - Start background engine 🟢
▪️ `/stop <pid>` - Kill running engine 🛑
▪️ `/ps` - List all active engines 📊

🖥 *SYSTEM VITALS:*
▪️ `/status` - Live uptime & overview ⏳
▪️ `/sysinfo` - CPU & RAM utilization 🧬
▪️ `/disk` - Storage details 💽
▪️ `/memory` - RAM usage breakdown 🧠

🔑 *ACCESS & CONTROL:*
▪️ `/myid` - View your Telegram User ID 🪪
▪️ `/menu` or `/start` - Interactive Dashboard 🎛
▪️ `/channel` - Add channel via forward *(Max 10)* 📢
▪️ `/channels` - View & remove channels *(Owner only)* 📋
▪️ `/channel_del <id>` - Remove specific channel ❌
▪️ `/add <id>` & `/remove <id>` - Whitelist access 👥

🔒 *Active Channels:* `{count} / {MAX_CHANNELS}`
*═════════════════════════*
*BAAP HOSTING READY >_*"""

# ----------------- OWNER CHANNEL MANAGEMENT -----------------
@bot.message_handler(commands=['channel'])
def set_channel_prompt(message):
    last_activity["time"] = time.time()
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "💀 *[ACCESS DENIED]* Owner only.", parse_mode="Markdown")
        return
    current_count = len(bot_config.get("required_channels", []))
    if current_count >= MAX_CHANNELS:
        bot.reply_to(message, f"⚠️ *[LIMIT REACHED]* Max `{MAX_CHANNELS}` channels.", parse_mode="Markdown")
        return
    waiting_for_channel_forward.add(message.from_user.id)
    text = (
        f"📢 *[CHANNEL SETUP MODE]* ({current_count}/{MAX_CHANNELS} active)\n\n"
        f"1. Add bot as **Administrator** in your channel.\n"
        f"2. **Forward any post from that channel here.**\n\n"
        f"Send `/cancel` to cancel."
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Cancel Setup", callback_data="cancel_channel_setup"))
    bot.reply_to(message, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['channels'])
def list_channels_cmd(message):
    last_activity["time"] = time.time()
    if not is_owner(message.from_user.id): return
    show_channel_manager(message.chat.id, None)

@bot.message_handler(commands=['channel_del'])
def delete_channel_by_arg(message):
    last_activity["time"] = time.time()
    if not is_owner(message.from_user.id): return
    args = message.text.split(" ")
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Use `/channel_del <channel_id>`.", parse_mode="Markdown")
        return
    try:
        del_id = int(args[1])
        channels = bot_config.get("required_channels", [])
        before = len(channels)
        bot_config["required_channels"] = [c for c in channels if c.get("id") != del_id]
        if len(bot_config["required_channels"]) < before:
            save_config(bot_config)
            bot.reply_to(message, f"✅ Removed channel `{del_id}`.", parse_mode="Markdown")
        else:
            bot.reply_to(message, f"❌ Channel `{del_id}` not found.", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "⚠️ Channel ID must be numeric.")

def show_channel_manager(chat_id, message_id=None):
    channels = bot_config.get("required_channels", [])
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not channels:
        text = "📢 *[CHANNEL MANAGER]*\n\nNo channels configured (0/10).\nSend `/channel` to add one!"
    else:
        text = f"📢 *[CHANNEL MANAGER]* ({len(channels)}/{MAX_CHANNELS} Active)\n\n"
        for i, ch in enumerate(channels, 1):
            clean_title = escape_markdown(ch.get('title', 'Channel'))
            text += f"{i}. *{clean_title}*\n   ID: `{ch.get('id')}`\n   Link: {ch.get('invite_link') or 'None'}\n\n"
            markup.add(types.InlineKeyboardButton(f"🗑 Remove: {ch.get('title', 'Channel')[:25]}", callback_data=f"del_ch_{ch.get('id')}"))
    if len(channels) < MAX_CHANNELS:
        markup.add(types.InlineKeyboardButton("➕ Add New Channel", callback_data="add_new_channel_btn"))
    markup.add(types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="btn_main_menu"))
    if message_id:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['cancel'])
def cancel_action(message):
    last_activity["time"] = time.time()
    if message.from_user.id in waiting_for_channel_forward:
        waiting_for_channel_forward.remove(message.from_user.id)
        bot.reply_to(message, "❌ Setup cancelled.")

@bot.message_handler(commands=['add'])
def add_user(message):
    last_activity["time"] = time.time()
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "💀 *[ACCESS DENIED]* Owner only.", parse_mode="Markdown")
        return
    try:
        new_id = int(message.text.split(" ")[1])
        allowed_users.add(new_id)
        save_users(allowed_users)
        bot.reply_to(message, f"⚡️ *[ACCESS GRANTED]* User `{new_id}` added! 🚀", parse_mode="Markdown")
        try:
            bot.send_message(new_id, "🎉 *[ACCESS APPROVED]* Admin ne approve kiya! /start karo.", parse_mode="Markdown")
        except Exception:
            pass
    except Exception:
        bot.reply_to(message, "⚠️ Use: `/add <userid>`", parse_mode="Markdown")

@bot.message_handler(commands=['remove'])
def remove_user(message):
    last_activity["time"] = time.time()
    if not is_owner(message.from_user.id): return
    try:
        del_id = int(message.text.split(" ")[1])
        if del_id == OWNER_ID:
            bot.reply_to(message, "👑 Cannot remove the master owner!", parse_mode="Markdown")
            return
        if del_id in allowed_users:
            allowed_users.remove(del_id)
            save_users(allowed_users)
            bot.reply_to(message, f"🗑 *[USER REMOVED]* `{del_id}` removed!", parse_mode="Markdown")
        else:
            bot.reply_to(message, "⚠️ User ID not in whitelist.")
    except Exception:
        bot.reply_to(message, "⚠️ Use: `/remove <userid>`", parse_mode="Markdown")

# ----------------- CHANNEL FORWARD CAPTURE -----------------
@bot.message_handler(func=lambda msg: msg.from_user.id in waiting_for_channel_forward and msg.forward_from_chat is not None)
def handle_channel_forward(message):
    last_activity["time"] = time.time()
    user_id = message.from_user.id
    chat = message.forward_from_chat
    waiting_for_channel_forward.discard(user_id)
    if chat.type != 'channel':
        bot.reply_to(message, "❌ Must be forwarded from a **Channel**.", parse_mode="Markdown")
        return
    channels = bot_config.get("required_channels", [])
    if len(channels) >= MAX_CHANNELS:
        bot.reply_to(message, f"⚠️ Max {MAX_CHANNELS} channels reached.", parse_mode="Markdown")
        return
    channel_id = chat.id
    channel_title = chat.title or "Required Channel"
    channel_username = chat.username
    if any(c.get("id") == channel_id for c in channels):
        bot.reply_to(message, f"⚠️ Channel *{escape_markdown(channel_title)}* already added!", parse_mode="Markdown")
        return
    invite_link = None
    try:
        chat_info = bot.get_chat(channel_id)
        if chat_info.invite_link:
            invite_link = chat_info.invite_link
        elif channel_username:
            invite_link = f"https://t.me/{channel_username}"
        else:
            link_obj = bot.create_chat_invite_link(channel_id)
            invite_link = link_obj.invite_link
    except Exception as e:
        if channel_username:
            invite_link = f"https://t.me/{channel_username}"
        print(f"[!] Invite link error: {e}")
    new_channel = {"id": channel_id, "title": channel_title, "username": channel_username, "invite_link": invite_link}
    channels.append(new_channel)
    bot_config["required_channels"] = channels
    save_config(bot_config)
    clean_title = escape_markdown(channel_title)
    bot.reply_to(
        message,
        f"✅ *[CHANNEL #{len(channels)} ADDED]*\n\n"
        f"📌 *Title:* {clean_title}\n"
        f"🆔 *ID:* `{channel_id}`\n"
        f"🔗 *Link:* {invite_link or 'No link'}\n\n"
        f"Total: `{len(channels)}/{MAX_CHANNELS}`",
        parse_mode="Markdown"
    )

# ----------------- GENERAL & DASHBOARD -----------------
@bot.message_handler(commands=['start', 'help', 'menu', 'commands'])
def send_menu(message):
    last_activity["time"] = time.time()
    user_id = message.from_user.id
    if is_owner(user_id):
        bot.reply_to(message, get_help_text(), parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
        return
    is_all_joined, missing = check_channel_subscriptions(user_id)
    if not is_all_joined:
        bot.reply_to(
            message,
            f"⚠️ *[MEMBERSHIP REQUIRED]*\nJoin all `{len(missing)}` pending channel(s).",
            parse_mode="Markdown",
            reply_markup=get_join_channels_keyboard(missing)
        )
        return
    if not is_allowed_user(user_id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📩 Request Authorization from Admin", callback_data="send_auth_request"))
        bot.reply_to(
            message,
            "✅ *[CHANNELS VERIFIED]*\n\n🔒 *[AUTHORIZATION REQUIRED]*\nClick below to request access.",
            parse_mode="Markdown",
            reply_markup=markup
        )
        return
    bot.reply_to(message, get_help_text(), parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))

@bot.message_handler(commands=['myid'])
def my_id(message):
    last_activity["time"] = time.time()
    bot.reply_to(message, f"🪪 *YOUR ID:* `{message.from_user.id}` ⚡️", parse_mode="Markdown")

# ----------------- SYSTEM INFO -----------------
@bot.message_handler(commands=['status'])
def server_status(message):
    last_activity["time"] = time.time()
    user_id = message.from_user.id
    if not is_allowed_user(user_id):
        bot.reply_to(message, "⛔️ *[UNAUTHORIZED]*", parse_mode="Markdown"); return
    is_all_joined, missing = check_channel_subscriptions(user_id)
    if not is_all_joined:
        bot.reply_to(message, "⚠️ Join all channels.", reply_markup=get_join_channels_keyboard(missing), parse_mode="Markdown"); return
    bot.reply_to(
        message,
        f"🟢 *SERVER STATUS:* `ONLINE`\n⏳ *RUNTIME:* `{get_uptime()}`\n⚙️ *ACTIVE ENGINES:* `{len(bg_processes)}`\n⚡️ *CONNECTION:* `SECURE`",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(user_id)
    )

@bot.message_handler(commands=['sysinfo', 'disk', 'memory'])
def sys_info(message):
    last_activity["time"] = time.time()
    user_id = message.from_user.id
    if not is_allowed_user(user_id):
        bot.reply_to(message, "⛔️ *[UNAUTHORIZED]*", parse_mode="Markdown"); return
    is_all_joined, missing = check_channel_subscriptions(user_id)
    if not is_all_joined:
        bot.reply_to(message, "⚠️ Join all channels.", reply_markup=get_join_channels_keyboard(missing), parse_mode="Markdown"); return
    if message.text == '/memory':
        mem = psutil.virtual_memory()
        bot.reply_to(message, f"🧠 *MEMORY:*\n*Total:* `{mem.total / (1024**3):.2f} GB`\n*Used:* `{mem.used / (1024**3):.2f} GB` ({mem.percent}%) ⚡️", parse_mode="Markdown")
    elif message.text == '/disk':
        disk = psutil.disk_usage('/')
        bot.reply_to(message, f"💽 *DISK:*\n*Total:* `{disk.total / (1024**3):.2f} GB`\n*Used:* `{disk.used / (1024**3):.2f} GB` ({disk.percent}%) 📂", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"🧬 *VITALS:*\n*CPU:* `{psutil.cpu_percent()}%` 🔥\n*RAM:* `{psutil.virtual_memory().percent}%` 🧠", parse_mode="Markdown")

# ----------------- BACKGROUND ENGINES -----------------
@bot.message_handler(commands=['run'])
def run_bg(message):
    last_activity["time"] = time.time()
    user_id = message.from_user.id
    if not is_allowed_user(user_id):
        bot.reply_to(message, "⛔️ *[UNAUTHORIZED]*", parse_mode="Markdown"); return
    is_all_joined, missing = check_channel_subscriptions(user_id)
    if not is_all_joined:
        bot.reply_to(message, "⚠️ Join all channels.", reply_markup=get_join_channels_keyboard(missing), parse_mode="Markdown"); return
    global current_dir
    cmd = message.text.replace('/run', '', 1).strip()
    if not cmd:
        bot.reply_to(message, "⚠️ Use `/run <command>`.", parse_mode="Markdown"); return
    try:
        proc = subprocess.Popen(cmd, shell=True, cwd=current_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        bg_processes[proc.pid] = {'process': proc, 'cmd': cmd}
        bot.reply_to(message, f"🟢 *[ENGINE STARTED]*\n*PID:* `{proc.pid}`\n*CMD:* `{cmd}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ *[CRASH]* {e}")

@bot.message_handler(commands=['ps'])
def list_ps(message):
    last_activity["time"] = time.time()
    user_id = message.from_user.id
    if not is_allowed_user(user_id):
        bot.reply_to(message, "⛔️ *[UNAUTHORIZED]*", parse_mode="Markdown"); return
    is_all_joined, missing = check_channel_subscriptions(user_id)
    if not is_all_joined:
        bot.reply_to(message, "⚠️ Join all channels.", reply_markup=get_join_channels_keyboard(missing), parse_mode="Markdown"); return
    if not bg_processes:
        bot.reply_to(message, "💤 *[SYSTEM IDLE]*"); return
    res = "📊 *[ACTIVE ENGINES]*\n*════════════════*\n"
    active_count = 0
    markup = types.InlineKeyboardMarkup()
    for pid, pinfo in list(bg_processes.items()):
        if pinfo['process'].poll() is None:
            active_count += 1
            res += f"⚙️ *PID:* `{pid}` | *CMD:* `{pinfo['cmd']}`\n"
            markup.add(types.InlineKeyboardButton(f"🛑 Kill PID {pid}", callback_data=f"kill_{pid}"))
        else:
            del bg_processes[pid]
    if active_count == 0:
        bot.reply_to(message, "💤 *[SYSTEM IDLE]*")
    else:
        bot.reply_to(message, res, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['stop'])
def stop_ps(message):
    last_activity["time"] = time.time()
    user_id = message.from_user.id
    if not is_allowed_user(user_id):
        bot.reply_to(message, "⛔️ *[UNAUTHORIZED]*", parse_mode="Markdown"); return
    is_all_joined, missing = check_channel_subscriptions(user_id)
    if not is_all_joined:
        bot.reply_to(message, "⚠️ Join all channels.", reply_markup=get_join_channels_keyboard(missing), parse_mode="Markdown"); return
    try:
        pid = int(message.text.split(" ")[1])
        if pid in bg_processes:
            bg_processes[pid]['process'].terminate()
            del bg_processes[pid]
            bot.reply_to(message, f"🛑 *[KILLED]* PID `{pid}` terminated!", parse_mode="Markdown")
        else:
            bot.reply_to(message, "⚠️ PID not found.")
    except Exception:
        bot.reply_to(message, "⚠️ Use: `/stop <pid>`.", parse_mode="Markdown")

# ----------------- FILE OPERATIONS -----------------
@bot.message_handler(commands=['download'])
def download_file(message):
    last_activity["time"] = time.time()
    user_id = message.from_user.id
    if not is_allowed_user(user_id):
        bot.reply_to(message, "⛔️ *[UNAUTHORIZED]*", parse_mode="Markdown"); return
    is_all_joined, missing = check_channel_subscriptions(user_id)
    if not is_all_joined:
        bot.reply_to(message, "⚠️ Join all channels.", reply_markup=get_join_channels_keyboard(missing), parse_mode="Markdown"); return
    global current_dir
    filename = message.text.replace('/download', '', 1).strip()
    if not filename:
        bot.reply_to(message, "⚠️ Use `/download <filename>`.", parse_mode="Markdown"); return
    filepath = os.path.join(current_dir, filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        bot.reply_to(message, "📥 *[EXTRACTING]* Transmitting... ⏳", parse_mode="Markdown")
        try:
            with open(filepath, 'rb') as f:
                bot.send_document(message.chat.id, f)
        except Exception as e:
            bot.reply_to(message, f"❌ Failed: {e}")
    else:
        bot.reply_to(message, "❌ *[404]* File not found!")

@bot.message_handler(content_types=['document'])
def handle_upload(message):
    last_activity["time"] = time.time()
    user_id = message.from_user.id
    if not is_allowed_user(user_id):
        bot.reply_to(message, "⛔️ *[UNAUTHORIZED]*", parse_mode="Markdown"); return
    is_all_joined, missing = check_channel_subscriptions(user_id)
    if not is_all_joined:
        bot.reply_to(message, "⚠️ Join all channels.", reply_markup=get_join_channels_keyboard(missing), parse_mode="Markdown"); return
    global current_dir
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        filepath = os.path.join(current_dir, message.document.file_name)
        with open(filepath, 'wb') as nf:
            nf.write(downloaded)
        bot.reply_to(message, f"📤 *[UPLOAD COMPLETE]*\n`{filepath}` 🔒", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ *[UPLOAD FAILED]* {e}")

# ----------------- DIRECT TERMINAL -----------------
@bot.message_handler(func=lambda message: not message.text.startswith('/'))
def direct_terminal(message):
    last_activity["time"] = time.time()
    user_id = message.from_user.id
    if not is_allowed_user(user_id):
        bot.reply_to(message, "⛔️ *[UNAUTHORIZED]*", parse_mode="Markdown"); return
    is_all_joined, missing = check_channel_subscriptions(user_id)
    if not is_all_joined:
        bot.reply_to(message, "⚠️ Join all channels.", reply_markup=get_join_channels_keyboard(missing), parse_mode="Markdown"); return
    global current_dir
    cmd = message.text.strip()
    if cmd.startswith("cd "):
        new_dir = cmd[3:].strip()
        target_path = os.path.abspath(os.path.join(current_dir, new_dir))
        if os.path.exists(target_path) and os.path.isdir(target_path):
            current_dir = target_path
            bot.reply_to(message, f"📂 *[DIR CHANGED]*\n`{current_dir}` ⚡️", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ *[404]* Directory does not exist!")
        return
    try:
        bot.send_chat_action(message.chat.id, 'typing')
        result = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT, cwd=current_dir)
        if not result.strip():
            bot.reply_to(message, "✅ *[EXECUTED]* Command succeeded with empty output. 🥷", parse_mode="Markdown")
        else:
            if len(result) > 4000:
                out_path = "output.txt"
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(result)
                with open(out_path, "rb") as f:
                    bot.send_document(message.chat.id, f, caption="⚠️ *[OUTPUT TRUNCATED]*", parse_mode="Markdown")
            else:
                bot.reply_to(message, f"```\n{result}\n```", parse_mode="Markdown")
    except subprocess.CalledProcessError as e:
        bot.reply_to(message, f"🛑 *[COMMAND ERROR]*:\n```\n{e.output}\n```", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ *[SYSTEM ERROR]*: {e}")

# ----------------- CALLBACK HANDLERS -----------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    last_activity["time"] = time.time()
    user_id = call.from_user.id

    if call.data == "verify_membership":
        is_all_joined, missing = check_channel_subscriptions(user_id)
        if is_all_joined:
            if is_allowed_user(user_id):
                bot.answer_callback_query(call.id, "✅ Verified!")
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=get_help_text(), parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
            else:
                bot.answer_callback_query(call.id, "✅ Verified!")
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("📩 Request Authorization", callback_data="send_auth_request"))
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🎉 *[VERIFIED]*\n\n⚠️ Admin approval required.", parse_mode="Markdown", reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, f"❌ Still {len(missing)} left!", show_alert=True)
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_join_channels_keyboard(missing))
        return

    if call.data == "send_auth_request":
        is_all_joined, missing = check_channel_subscriptions(user_id)
        if not is_all_joined:
            bot.answer_callback_query(call.id, "❌ Join all channels first!", show_alert=True); return
        if is_allowed_user(user_id):
            bot.answer_callback_query(call.id, "✅ Already authorized!")
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=get_help_text(), parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
            return
        raw_full_name = f"{call.from_user.first_name} {call.from_user.last_name or ''}".strip()
        safe_full_name = escape_markdown(raw_full_name)
        safe_username = "@" + escape_markdown(call.from_user.username) if call.from_user.username else "None"
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton("✅ Allow", callback_data=f"auth_allow_{user_id}"),
            types.InlineKeyboardButton("❌ Deny", callback_data=f"auth_deny_{user_id}")
        )
        channels_count = len(bot_config.get("required_channels", []))
        admin_text = (
            f"👑 *BAAP HOSTING | NEW ACCESS REQUEST* 👑\n\n"
            f"👤 *Name:* {safe_full_name}\n"
            f"🔗 *Username:* {safe_username}\n"
            f"🆔 *User ID:* `{user_id}`\n"
            f"📢 *Channels:* Verified `{channels_count}` ✅\n\n"
            f"Grant terminal access?"
        )
        try:
            bot.send_message(OWNER_ID, admin_text, parse_mode="Markdown", reply_markup=admin_markup)
            pending_requests.add(user_id)
            bot.answer_callback_query(call.id, "📨 Sent to Admin!")
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="⏳ *[REQUEST SENT]*\n\nAdmin approval ka wait karo! 🚀", parse_mode="Markdown")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Error: {e}", show_alert=True)
        return

    if call.data.startswith("auth_allow_"):
        if not is_owner(user_id):
            bot.answer_callback_query(call.id, "⛔ Owner only.", show_alert=True); return
        target_uid = int(call.data.replace("auth_allow_", ""))
        allowed_users.add(target_uid)
        save_users(allowed_users)
        pending_requests.discard(target_uid)
        bot.answer_callback_query(call.id, f"User {target_uid} approved!")
        try:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=call.message.text + f"\n\n🟢 APPROVED on {time.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            pass
        try:
            user_markup = types.InlineKeyboardMarkup()
            user_markup.add(types.InlineKeyboardButton("🚀 Launch Dashboard", callback_data="btn_main_menu"))
            bot.send_message(target_uid, "🎉 *[ACCESS APPROVED]*\n\nAdmin ne approve kiya! *BAAP HOSTING* pe swagat hai.", parse_mode="Markdown", reply_markup=user_markup)
        except Exception as e:
            print(f"[!] Notify failed: {e}")
        return

    if call.data.startswith("auth_deny_"):
        if not is_owner(user_id):
            bot.answer_callback_query(call.id, "⛔ Owner only.", show_alert=True); return
        target_uid = int(call.data.replace("auth_deny_", ""))
        pending_requests.discard(target_uid)
        bot.answer_callback_query(call.id, f"User {target_uid} denied.")
        try:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=call.message.text + f"\n\n🔴 DENIED on {time.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            pass
        try:
            bot.send_message(target_uid, "🚫 *[ACCESS DENIED]*", parse_mode="Markdown")
        except Exception:
            pass
        return

    if call.data == "btn_channel_info":
        if not is_owner(user_id): return
        show_channel_manager(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if call.data == "add_new_channel_btn":
        if not is_owner(user_id): return
        current_count = len(bot_config.get("required_channels", []))
        if current_count >= MAX_CHANNELS:
            bot.answer_callback_query(call.id, f"Limit reached ({MAX_CHANNELS}).", show_alert=True); return
        waiting_for_channel_forward.add(user_id)
        text = f"📢 *[ADD CHANNEL]* ({current_count}/{MAX_CHANNELS})\n\nForward any message from that channel."
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_channel_setup"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, parse_mode="Markdown", reply_markup=markup)
        bot.answer_callback_query(call.id)
        return

    if call.data.startswith("del_ch_"):
        if not is_owner(user_id): return
        target_ch_id = int(call.data.replace("del_ch_", ""))
        channels = bot_config.get("required_channels", [])
        bot_config["required_channels"] = [c for c in channels if c.get("id") != target_ch_id]
        save_config(bot_config)
        bot.answer_callback_query(call.id, "Channel removed!")
        show_channel_manager(call.message.chat.id, call.message.message_id)
        return

    if not is_allowed_user(user_id):
        bot.answer_callback_query(call.id, "⛔ Unauthorized.", show_alert=True); return

    is_all_joined, missing = check_channel_subscriptions(user_id)
    if not is_all_joined:
        bot.answer_callback_query(call.id, "⚠️ Channel membership required!", show_alert=True); return

    if call.data.startswith("kill_"):
        pid = int(call.data.replace("kill_", ""))
        if pid in bg_processes:
            try:
                bg_processes[pid]['process'].terminate()
                del bg_processes[pid]
                bot.answer_callback_query(call.id, f"Engine {pid} killed!")
                bot.send_message(call.message.chat.id, f"🛑 *[KILLED]* PID `{pid}` terminated.", parse_mode="Markdown")
            except Exception as e:
                bot.answer_callback_query(call.id, f"Error: {e}", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "PID not found.")
        return

    if call.data == "btn_main_menu":
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=get_help_text(), parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
        bot.answer_callback_query(call.id)

    elif call.data == "btn_status":
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"🟢 *SERVER STATUS:* `ONLINE`\n⏳ *RUNTIME:* `{get_uptime()}`\n⚙️ *ACTIVE ENGINES:* `{len(bg_processes)}`\n⚡️ *CONNECTION:* `SECURE`",
            parse_mode="Markdown", reply_markup=get_back_keyboard()
        )
        bot.answer_callback_query(call.id)

    elif call.data == "btn_sysinfo":
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"🧬 *VITALS:*\n*CPU:* `{psutil.cpu_percent()}%` 🔥\n*RAM:* `{psutil.virtual_memory().percent}%` 🧠",
            parse_mode="Markdown", reply_markup=get_back_keyboard()
        )
        bot.answer_callback_query(call.id)

    elif call.data == "btn_memory":
        mem = psutil.virtual_memory()
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"🧠 *MEMORY:*\n*Total:* `{mem.total / (1024**3):.2f} GB`\n*Used:* `{mem.used / (1024**3):.2f} GB` ({mem.percent}%) ⚡️\n*Available:* `{mem.available / (1024**3):.2f} GB`",
            parse_mode="Markdown", reply_markup=get_back_keyboard()
        )
        bot.answer_callback_query(call.id)

    elif call.data == "btn_disk":
        disk = psutil.disk_usage('/')
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"💽 *DISK:*\n*Total:* `{disk.total / (1024**3):.2f} GB`\n*Used:* `{disk.used / (1024**3):.2f} GB` ({disk.percent}%) 📂\n*Free:* `{disk.free / (1024**3):.2f} GB`",
            parse_mode="Markdown", reply_markup=get_back_keyboard()
        )
        bot.answer_callback_query(call.id)

    elif call.data == "btn_ps":
        if not bg_processes:
            text = "💤 *[SYSTEM IDLE]*"
            markup = get_back_keyboard()
        else:
            text = "📊 *[ACTIVE ENGINES]*\n*════════════════*\n"
            markup = types.InlineKeyboardMarkup()
            for pid, pinfo in list(bg_processes.items()):
                if pinfo['process'].poll() is None:
                    text += f"⚙️ *PID:* `{pid}` | *CMD:* `{pinfo['cmd']}`\n"
                    markup.add(types.InlineKeyboardButton(f"🛑 Kill PID {pid}", callback_data=f"kill_{pid}"))
                else:
                    del bg_processes[pid]
            markup.add(types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="btn_main_menu"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, parse_mode="Markdown", reply_markup=markup)
        bot.answer_callback_query(call.id)

    elif call.data == "btn_myid":
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"🪪 *YOUR ID:* `{call.from_user.id}` ⚡️",
            parse_mode="Markdown", reply_markup=get_back_keyboard()
        )
        bot.answer_callback_query(call.id)

    elif call.data == "btn_help":
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=get_help_text(), parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
        bot.answer_callback_query(call.id)

    elif call.data == "btn_list_users":
        if not is_owner(user_id): return
        users_list_str = "\n".join([f"▪️ `{uid}`" for uid in allowed_users])
        bot.edit_message_text(
            chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"👥 *[WHITELISTED USERS]*\n\n{users_list_str}\n\n• Use `/add <id>` or `/remove <id>`.",
            parse_mode="Markdown", reply_markup=get_back_keyboard()
        )
        bot.answer_callback_query(call.id)

    elif call.data == "cancel_channel_setup":
        waiting_for_channel_forward.discard(user_id)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="❌ Channel setup cancelled.")
        bot.answer_callback_query(call.id)

# ============================================================
# 🚀 MAIN — Sab Kuch Start Karo
# ============================================================

def run_bot_polling():
    """Polling ko crash-proof banaya — agar crash ho, 5 sec me restart."""
    while True:
        try:
            print("👑 BAAP HOSTING bot polling started...")
            bot.infinity_polling(timeout=30, long_polling_timeout=20)
        except Exception as e:
            print(f"[!] Polling crashed: {e}")
            print("[!] Restarting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    # 1. Health server background me
    threading.Thread(target=run_health_server, daemon=True).start()

    # 2. Self-ping thread (No-Sleep ka core)
    threading.Thread(target=self_ping_loop, daemon=True).start()

    # 3. Bot activity watcher
    threading.Thread(target=bot_activity_watcher, daemon=True).start()

    # 4. 3 second wait taaki sab ready ho
    time.sleep(3)

    print("=" * 50)
    print("👑 BAAP HOSTING — No-Sleep Edition")
    print(f"🌐 Render URL: {RENDER_URL or 'NOT SET'}")
    print(f"🔄 Self-ping every {SELF_PING_INTERVAL}s")
    print("=" * 50)

    # 5. Bot chalao (main thread)
    run_bot_polling()