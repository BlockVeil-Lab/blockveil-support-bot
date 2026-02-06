from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters
)
import os, random, string, html
from io import BytesIO

TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID"))

user_active_ticket = {}
ticket_status = {}
ticket_user = {}
ticket_username = {}
ticket_messages = {}
user_tickets = {}
group_message_map = {}

def generate_ticket_id(length=8):
    chars = string.ascii_letters + string.digits + "*#@$&"
    return "BV-" + "".join(random.choice(chars) for _ in range(length))

def code(tid):
    return f"<code>{html.escape(tid)}</code>"

def user_info(user):
    return (
        "User Information\n"
        f"• User ID   : {user.id}\n"
        f"• Username  : @{user.username or ''}\n"
        f"• Full Name : {user.first_name or ''}\n\n"
    )

def header(tid, user):
    return (
        f"🎫 Ticket ID: {code(tid)}\n"
        f"Status: {ticket_status[tid]}\n\n"
        + user_info(user)
        + "Message:\n"
    )

async def start(update: Update, context):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎟️ Create Ticket", callback_data="create")]])
    await update.message.reply_text("Welcome to BlockVeil Support.", reply_markup=kb)

async def create_ticket(update: Update, context):
    q = update.callback_query
    await q.answer()
    u = q.from_user
    if u.id in user_active_ticket:
        await q.message.reply_text(f"{code(user_active_ticket[u.id])}", parse_mode="HTML")
        return
    tid = generate_ticket_id()
    user_active_ticket[u.id] = tid
    ticket_status[tid] = "Pending"
    ticket_user[tid] = u.id
    ticket_username[tid] = u.username or ""
    ticket_messages[tid] = []
    user_tickets.setdefault(u.id, []).append(tid)
    await q.message.reply_text(f"{code(tid)}", parse_mode="HTML")

async def user_message(update: Update, context):
    u = update.message.from_user
    if u.id not in user_active_ticket:
        await update.message.reply_text("❗ Please create a ticket first.")
        return
    tid = user_active_ticket[u.id]
    if ticket_status[tid] == "Pending":
        ticket_status[tid] = "Processing"
    m = update.message
    sent = None
    if m.text:
        sent = await context.bot.send_message(
            GROUP_ID, header(tid, u) + html.escape(m.text), parse_mode="HTML"
        )
        ticket_messages[tid].append((u.first_name, m.text))
    elif m.photo:
        sent = await context.bot.send_photo(
            GROUP_ID, m.photo[-1].file_id,
            caption=header(tid, u) + "[Photo]", parse_mode="HTML"
        )
        ticket_messages[tid].append((u.first_name, "[Photo]"))
    elif m.voice:
        sent = await context.bot.send_voice(
            GROUP_ID, m.voice.file_id,
            caption=header(tid, u) + "[Voice]", parse_mode="HTML"
        )
        ticket_messages[tid].append((u.first_name, "[Voice]"))
    elif m.video:
        sent = await context.bot.send_video(
            GROUP_ID, m.video.file_id,
            caption=header(tid, u) + "[Video]", parse_mode="HTML"
        )
        ticket_messages[tid].append((u.first_name, "[Video]"))
    elif m.document:
        sent = await context.bot.send_document(
            GROUP_ID, m.document.file_id,
            caption=header(tid, u) + "[Document]", parse_mode="HTML"
        )
        ticket_messages[tid].append((u.first_name, "[Document]"))
    if sent:
        group_message_map[sent.message_id] = tid

async def group_reply(update: Update, context):
    if not update.message.reply_to_message:
        return
    mid = update.message.reply_to_message.message_id
    if mid not in group_message_map:
        return
    tid = group_message_map[mid]
    uid = ticket_user[tid]
    m = update.message
    prefix = f"🎫 Ticket ID: {code(tid)}\n\n"
    if m.text:
        await context.bot.send_message(uid, prefix + html.escape(m.text), parse_mode="HTML")
        ticket_messages[tid].append(("BlockVeil Support", m.text))
    elif m.photo:
        await context.bot.send_photo(uid, m.photo[-1].file_id, caption=prefix, parse_mode="HTML")
        ticket_messages[tid].append(("BlockVeil Support", "[Photo]"))
    elif m.voice:
        await context.bot.send_voice(uid, m.voice.file_id, caption=prefix, parse_mode="HTML")
        ticket_messages[tid].append(("BlockVeil Support", "[Voice]"))
    elif m.video:
        await context.bot.send_video(uid, m.video.file_id, caption=prefix, parse_mode="HTML")
        ticket_messages[tid].append(("BlockVeil Support", "[Video]"))
    elif m.document:
        await context.bot.send_document(uid, m.document.file_id, caption=prefix, parse_mode="HTML")
        ticket_messages[tid].append(("BlockVeil Support", "[Document]"))

async def status_cmd(update: Update, context):
    if not context.args or context.args[0] not in ticket_status:
        return
    tid = context.args[0]
    await update.message.reply_text(
        f"🎫 Ticket ID: {code(tid)}\nStatus: {ticket_status[tid]}",
        parse_mode="HTML"
    )

async def send_cmd(update: Update, context):
    if update.effective_chat.id != GROUP_ID or len(context.args) < 2:
        return
    target = context.args[0]
    text = html.escape(" ".join(context.args[1:]))
    targets = set()
    if target == "@all":
        targets = set(user_tickets.keys())
    elif target.startswith("BV-") and target in ticket_status and ticket_status[target] != "Closed":
        targets.add(ticket_user[target])
    elif target.startswith("@"):
        for t, u in ticket_username.items():
            if u.lower() == target[1:].lower():
                targets.add(ticket_user[t])
    else:
        try:
            targets.add(int(target))
        except:
            pass
    for uid in targets:
        await context.bot.send_message(uid, text)

async def close_cmd(update: Update, context):
    tid = None
    if context.args:
        tid = context.args[0]
    elif update.message.reply_to_message:
        tid = group_message_map.get(update.message.reply_to_message.message_id)
    if not tid or tid not in ticket_status:
        return
    ticket_status[tid] = "Closed"
    uid = ticket_user[tid]
    user_active_ticket.pop(uid, None)
    await context.bot.send_message(uid, f"{code(tid)}", parse_mode="HTML")

async def open_cmd(update: Update, context):
    if not context.args:
        return
    tid = context.args[0]
    if tid in ticket_status and ticket_status[tid] == "Closed":
        ticket_status[tid] = "Processing"
        user_active_ticket[ticket_user[tid]] = tid

async def export_cmd(update: Update, context):
    if not context.args:
        return
    tid = context.args[0]
    buf = BytesIO()
    for a, b in ticket_messages.get(tid, []):
        buf.write(f"{a}: {b}\n".encode())
    buf.seek(0)
    buf.name = f"{tid}.txt"
    await context.bot.send_document(GROUP_ID, buf)

async def history_cmd(update: Update, context):
    if not context.args:
        return
    target = context.args[0]
    uid = int(target) if target.isdigit() else None
    if target.startswith("@"):
        for t, u in ticket_username.items():
            if u.lower() == target[1:].lower():
                uid = ticket_user[t]
    if uid not in user_tickets:
        return
    text = ""
    for i, t in enumerate(user_tickets[uid], 1):
        text += f"{i}. {code(t)}\n"
    await update.message.reply_text(text, parse_mode="HTML")

async def user_cmd(update: Update, context):
    buf = BytesIO()
    seen = set()
    i = 1
    for tid, uid in ticket_user.items():
        if uid in seen:
            continue
        seen.add(uid)
        buf.write(f"{i} : @{ticket_username[tid]} — {uid}\n".encode())
        i += 1
    buf.seek(0)
    buf.name = "users.txt"
    await context.bot.send_document(GROUP_ID, buf)

async def list_cmd(update: Update, context):
    if not context.args:
        return
    mode = context.args[0].lower()
    out = []
    for t, s in ticket_status.items():
        if mode in ["open", "opened"] and s != "Closed":
            out.append(t)
        if mode in ["close", "closed"] and s == "Closed":
            out.append(t)
    await update.message.reply_text("\n".join(code(x) for x in out), parse_mode="HTML")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(create_ticket, pattern="create"))
app.add_handler(CommandHandler("status", status_cmd))
app.add_handler(CommandHandler("send", send_cmd))
app.add_handler(CommandHandler("close", close_cmd))
app.add_handler(CommandHandler("open", open_cmd))
app.add_handler(CommandHandler("export", export_cmd))
app.add_handler(CommandHandler("history", history_cmd))
app.add_handler(CommandHandler("user", user_cmd))
app.add_handler(CommandHandler("list", list_cmd))
app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, user_message))
app.add_handler(MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, group_reply))

app.run_polling()
