# BlockVeil Support Bot — Final stable release
# Requirements: python-telegram-bot v20+, set BOT_TOKEN and GROUP_ID env vars.

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters
)
import os, random, string, html
from io import BytesIO

TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID"))

# ----------------- In-memory storage -----------------
user_active_ticket = {}      # user_id -> active ticket_id
ticket_status = {}           # ticket_id -> status (Pending/Processing/Closed)
ticket_user = {}             # ticket_id -> user_id
ticket_username = {}         # ticket_id -> username (may be "")
ticket_messages = {}         # ticket_id -> list of (sender, text)
user_tickets = {}            # user_id -> [ticket_ids]
group_message_map = {}       # group_message_id -> ticket_id

# ----------------- Helpers -----------------
def generate_ticket_id(length=8):
    chars = string.ascii_letters + string.digits + "*#@$&"
    return "BV-" + "".join(random.choice(chars) for _ in range(length))

def code(tid):
    # return HTML-coded mono style
    return f"<code>{html.escape(tid)}</code>"

def user_info_block_html(user):
    uname = user.username or ""
    fname = user.first_name or ""
    return (
        "User Information\n"
        f"• User ID   : {html.escape(str(user.id))}\n"
        f"• Username  : @{html.escape(uname)}\n"
        f"• Full Name : {html.escape(fname)}\n\n"
    )

def safe_text(s):
    # escape for HTML output to avoid breaking formatting
    return html.escape(s or "")

def make_header_html(tid, status, user):
    return f"🎫 Ticket ID: {code(tid)}\nStatus: {html.escape(status)}\n\n" + user_info_block_html(user) + "Message:\n"

# ----------------- /start -----------------
async def start_handler(update: Update, context):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎟️ Create Ticket", callback_data="create_ticket")]])
    await update.message.reply_text("Welcome to BlockVeil Support.\nClick below to create a ticket.", reply_markup=kb)

# ----------------- Create ticket (callback) -----------------
async def create_ticket_handler(update: Update, context):
    q = update.callback_query
    await q.answer()
    u = q.from_user

    if u.id in user_active_ticket:
        await q.message.reply_text(f"🎫 You already have an active ticket:\n{code(user_active_ticket[u.id])}", parse_mode="HTML")
        return

    tid = generate_ticket_id()
    user_active_ticket[u.id] = tid
    ticket_status[tid] = "Pending"
    ticket_user[tid] = u.id
    ticket_username[tid] = u.username or ""
    ticket_messages[tid] = []
    user_tickets.setdefault(u.id, []).append(tid)

    await q.message.reply_text(
        f"🎫 Ticket Created: {code(tid)}\nStatus: Pending\n\nPlease send your message, photo, voice, video, or file.",
        parse_mode="HTML"
    )

# ----------------- User -> Group messages (text + media) -----------------
async def user_message_handler(update: Update, context):
    msg = update.message
    u = msg.from_user

    if u.id not in user_active_ticket:
        await msg.reply_text(
            "❗ Please create a ticket first.\n\nClick /start to submit a new support ticket.\nTo track an existing ticket, use /status BV-XXXXX"
        )
        return

    tid = user_active_ticket[u.id]
    if ticket_status.get(tid) == "Pending":
        ticket_status[tid] = "Processing"

    header_html = make_header_html(tid, ticket_status[tid], u)
    sent = None
    log_text = ""

    # Text
    if msg.text:
        log_text = safe_text(msg.text)
        sent = await context.bot.send_message(chat_id=GROUP_ID, text=header_html + log_text, parse_mode="HTML")

    # Photo
    elif msg.photo:
        log_text = "[Photo]"
        # use largest photo
        file_id = msg.photo[-1].file_id
        sent = await context.bot.send_photo(chat_id=GROUP_ID, photo=file_id, caption=header_html + log_text, parse_mode="HTML")

    # Voice
    elif msg.voice:
        log_text = "[Voice]"
        sent = await context.bot.send_voice(chat_id=GROUP_ID, voice=msg.voice.file_id, caption=header_html + log_text, parse_mode="HTML")

    # Video
    elif msg.video:
        log_text = "[Video]"
        sent = await context.bot.send_video(chat_id=GROUP_ID, video=msg.video.file_id, caption=header_html + log_text, parse_mode="HTML")

    # Document
    elif msg.document:
        log_text = "[Document]"
        sent = await context.bot.send_document(chat_id=GROUP_ID, document=msg.document.file_id, caption=header_html + log_text, parse_mode="HTML")

    # Fallback (sticker, etc.)
    else:
        log_text = "[Unsupported media/type]"
        sent = await context.bot.send_message(chat_id=GROUP_ID, text=header_html + log_text, parse_mode="HTML")

    # record mapping & history
    if sent:
        group_message_map[sent.message_id] = tid
        ticket_messages.setdefault(tid, []).append((u.first_name or str(u.id), log_text))

# ----------------- Group reply -> User (supports reply media/text) -----------------
async def group_reply_handler(update: Update, context):
    msg = update.message
    if not msg.reply_to_message:
        return
    reply_mid = msg.reply_to_message.message_id
    if reply_mid not in group_message_map:
        return

    tid = group_message_map[reply_mid]
    uid = ticket_user.get(tid)
    if not uid:
        return

    prefix = f"🎫 Ticket ID: {code(tid)}\n\n"

    # Text
    if msg.text:
        text = safe_text(msg.text)
        await context.bot.send_message(chat_id=uid, text=prefix + text, parse_mode="HTML")
        ticket_messages.setdefault(tid, []).append(("BlockVeil Support", text))

    # Photo
    elif msg.photo:
        await context.bot.send_photo(chat_id=uid, photo=msg.photo[-1].file_id, caption=prefix, parse_mode="HTML")
        ticket_messages.setdefault(tid, []).append(("BlockVeil Support", "[Photo]"))

    # Voice
    elif msg.voice:
        await context.bot.send_voice(chat_id=uid, voice=msg.voice.file_id, caption=prefix, parse_mode="HTML")
        ticket_messages.setdefault(tid, []).append(("BlockVeil Support", "[Voice]"))

    # Video
    elif msg.video:
        await context.bot.send_video(chat_id=uid, video=msg.video.file_id, caption=prefix, parse_mode="HTML")
        ticket_messages.setdefault(tid, []).append(("BlockVeil Support", "[Video]"))

    # Document
    elif msg.document:
        await context.bot.send_document(chat_id=uid, document=msg.document.file_id, caption=prefix, parse_mode="HTML")
        ticket_messages.setdefault(tid, []).append(("BlockVeil Support", "[Document]"))

# ----------------- /status BV-XXXXX -----------------
async def status_handler(update: Update, context):
    if not context.args:
        await update.message.reply_text("/status BV-XXXXX  [ টিকেট স্টাটাস দেখা যাবে। ]")
        return
    tid = context.args[0]
    if tid not in ticket_status:
        await update.message.reply_text("❌ Ticket not found.")
        return
    await update.message.reply_text(f"🎫 Ticket ID: {code(tid)}\nStatus: {html.escape(ticket_status[tid])}", parse_mode="HTML")

# ----------------- /send (BV-/@username/user_id/@all) -----------------
async def send_handler(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "/send BV-XXXXX your message\n/send @username your message\n/send user_id your message\n/send @all your message\n\n[ Ticket closed থাকলে message যাবে না এবং Username / ID valid হতে হবে ]"
        )
        return

    target = context.args[0]
    message = " ".join(context.args[1:])
    safe_message = safe_text(message)
    targets = set()

    if target == "@all":
        # all users who ever had tickets
        targets = set(user_tickets.keys())

    elif target.startswith("BV-"):
        if target not in ticket_status:
            await update.message.reply_text("❌ Ticket not found.")
            return
        if ticket_status.get(target) == "Closed":
            await update.message.reply_text("⚠️ Ticket is closed — message not sent.")
            return
        uid = ticket_user.get(target)
        if uid:
            targets.add(uid)

    elif target.startswith("@"):
        uname = target[1:].lower()
        for tid, uname_val in ticket_username.items():
            if uname_val and uname_val.lower() == uname:
                uid = ticket_user.get(tid)
                if uid:
                    targets.add(uid)

    else:
        try:
            uid = int(target)
            targets.add(uid)
        except:
            pass

    if not targets:
        await update.message.reply_text("❌ No valid user found.")
        return

    sent_count = 0
    for uid in targets:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📩 BlockVeil Support:\n\n{safe_message}")
            sent_count += 1
        except Exception:
            # ignore failure for single user
            pass

    await update.message.reply_text(f"✅ Message sent to {sent_count} user(s).")

# ----------------- /close (reply or /close BV-XXXXX) -----------------
async def close_handler(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return
    tid = None
    if context.args:
        tid = context.args[0]
    elif update.message.reply_to_message:
        tid = group_message_map.get(update.message.reply_to_message.message_id)

    if not tid or tid not in ticket_status:
        await update.message.reply_text("/close [reply to a ticket message to close] or /close BV-XXXXX")
        return

    ticket_status[tid] = "Closed"
    uid = ticket_user.get(tid)
    if uid:
        user_active_ticket.pop(uid, None)
        await context.bot.send_message(chat_id=uid, text=f"🎫 Ticket ID: {code(tid)}\nStatus: Closed", parse_mode="HTML")

    await update.message.reply_text(f"✅ Ticket {code(tid)} closed.", parse_mode="HTML")

# ----------------- /open BV-XXXXX -----------------
async def open_handler(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return
    if not context.args:
        return
    tid = context.args[0]
    if tid not in ticket_status:
        await update.message.reply_text("❌ Ticket not found.")
        return
    if ticket_status.get(tid) != "Closed":
        await update.message.reply_text("⚠️ Ticket already open.")
        return
    ticket_status[tid] = "Processing"
    uid = ticket_user.get(tid)
    if uid:
        user_active_ticket[uid] = tid
        await context.bot.send_message(chat_id=uid, text=f"🎫 Ticket ID: {code(tid)}\nStatus: Reopened", parse_mode="HTML")
    await update.message.reply_text(f"✅ Ticket {code(tid)} reopened.", parse_mode="HTML")

# ----------------- /export BV-XXXXX (txt) -----------------
async def export_handler(update: Update, context):
    if update.effective_chat.id != GROUP_ID or not context.args:
        return
    tid = context.args[0]
    if tid not in ticket_messages:
        await update.message.reply_text("❌ Ticket not found.")
        return

    buf = BytesIO()
    header = f"Ticket ID: {tid}\nStatus: {ticket_status.get(tid,'N/A')}\n\nConversation Log\n\n"
    buf.write(header.encode())
    for sender, msg in ticket_messages.get(tid, []):
        buf.write(f"{sender}: {msg}\n\n".encode())
    buf.seek(0)
    buf.name = f"{tid}.txt"
    await context.bot.send_document(chat_id=GROUP_ID, document=buf)

# ----------------- /history <user_id|@username> -----------------
async def history_handler(update: Update, context):
    if update.effective_chat.id != GROUP_ID or not context.args:
        return
    target = context.args[0]
    uid = None

    if target.startswith("@"):
        uname = target[1:].lower()
        # find first ticket with that username
        for tid, uname_val in ticket_username.items():
            if uname_val and uname_val.lower() == uname:
                uid = ticket_user.get(tid)
                break
    else:
        try:
            uid = int(target)
        except:
            pass

    if not uid or uid not in user_tickets:
        await update.message.reply_text("No tickets found for this user.")
        return

    text = "🎫 Ticket History\n\n"
    for i, t in enumerate(user_tickets.get(uid, []), 1):
        text += f"{i}. {code(t)}\n"

    await update.message.reply_text(text, parse_mode="HTML")

# ----------------- /user -> export user list txt -----------------
async def user_handler(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return
    seen = set()
    buf = BytesIO()
    buf.write("BlockVeil Support User list\n\n".encode())
    i = 1
    # iterate through tickets to collect unique users and a username
    for tid, uid in ticket_user.items():
        if uid in seen:
            continue
        seen.add(uid)
        uname = ticket_username.get(tid, "")
        buf.write(f"{i} : @{uname} — {uid}\n".encode())
        i += 1
    buf.seek(0)
    buf.name = "blockveil_users.txt"
    await context.bot.send_document(chat_id=GROUP_ID, document=buf)

# ----------------- /list opened / closed (aliases) -----------------
async def list_handler(update: Update, context):
    if update.effective_chat.id != GROUP_ID or not context.args:
        return
    mode = context.args[0].lower()
    open_alias = {"open", "opened"}
    close_alias = {"close", "closed"}
    out = []
    for tid, st in ticket_status.items():
        if mode in open_alias and st != "Closed":
            out.append(tid)
        elif mode in close_alias and st == "Closed":
            out.append(tid)
    if not out:
        await update.message.reply_text("No tickets found.")
        return
    text = ""
    for i, t in enumerate(out, 1):
        text += f"{i}. {code(t)}\n"
    await update.message.reply_text(text, parse_mode="HTML")

# ----------------- App init & handlers (order matters) -----------------
app = ApplicationBuilder().token(TOKEN).build()

# Command handlers first (group commands)
app.add_handler(CommandHandler("status", status_handler))
app.add_handler(CommandHandler("send", send_handler))
app.add_handler(CommandHandler("close", close_handler))
app.add_handler(CommandHandler("open", open_handler))
app.add_handler(CommandHandler("export", export_handler))
app.add_handler(CommandHandler("history", history_handler))
app.add_handler(CommandHandler("user", user_handler))
app.add_handler(CommandHandler("list", list_handler))

# Callback for create button
app.add_handler(CallbackQueryHandler(create_ticket_handler, pattern="create_ticket|create"))

# Message handlers last, strict filters to avoid collisions
app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.VOICE | filters.VIDEO | filters.Document), user_message_handler))
app.add_handler(MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, group_reply_handler))

# Start polling
app.run_polling()
