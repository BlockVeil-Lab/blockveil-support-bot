from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters
)
import os, random, string
from io import BytesIO

TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID"))

# ================= STORAGE =================
user_active_ticket = {}
ticket_status = {}
ticket_user = {}
ticket_username = {}
ticket_messages = {}
user_tickets = {}
group_message_map = {}

# ================= HELPERS =================
def gen_ticket():
    chars = string.ascii_letters + string.digits + "*#@$&"
    return "BV-" + "".join(random.choice(chars) for _ in range(8))

def mono(tid):
    return f"`{tid}`"

def header(tid):
    return f"🎫 Ticket ID: {mono(tid)}\nStatus: {ticket_status[tid]}\n\n"

# ================= START =================
async def start(update: Update, context):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎟️ Create Ticket", callback_data="create")]])
    await update.message.reply_text(
        "Welcome to BlockVeil Support.\nClick below to create a ticket.",
        reply_markup=kb
    )

# ================= CREATE =================
async def create_ticket(update: Update, context):
    q = update.callback_query
    await q.answer()
    u = q.from_user

    if u.id in user_active_ticket:
        await q.message.reply_text(f"Active ticket:\n{mono(user_active_ticket[u.id])}", parse_mode="Markdown")
        return

    tid = gen_ticket()
    user_active_ticket[u.id] = tid
    ticket_status[tid] = "Pending"
    ticket_user[tid] = u.id
    ticket_username[tid] = u.username or ""
    ticket_messages[tid] = []
    user_tickets.setdefault(u.id, []).append(tid)

    await q.message.reply_text(
        f"🎫 Ticket Created: {mono(tid)}\nStatus: Pending\nSend your message.",
        parse_mode="Markdown"
    )

# ================= USER MESSAGE =================
async def user_msg(update: Update, context):
    u = update.message.from_user
    if u.id not in user_active_ticket:
        await update.message.reply_text(
            "❗ Please create a ticket first.\n\n"
            "Click /start to submit a new support ticket.\n"
            "Use /status BV-XXXXX to track."
        )
        return

    tid = user_active_ticket[u.id]
    if ticket_status[tid] == "Pending":
        ticket_status[tid] = "Processing"

    text = update.message.text or "[Media]"
    sent = await context.bot.send_message(
        GROUP_ID,
        header(tid) + text,
        parse_mode="Markdown"
    )
    group_message_map[sent.message_id] = tid
    ticket_messages[tid].append((u.first_name, text))

# ================= GROUP REPLY =================
async def group_reply(update: Update, context):
    if not update.message.reply_to_message:
        return
    mid = update.message.reply_to_message.message_id
    if mid not in group_message_map:
        return

    tid = group_message_map[mid]
    uid = ticket_user[tid]
    msg = update.message.text or "[Media]"

    await context.bot.send_message(
        uid,
        f"🎫 Ticket ID: {mono(tid)}\n\n{msg}",
        parse_mode="Markdown"
    )
    ticket_messages[tid].append(("BlockVeil Support", msg))

# ================= STATUS =================
async def status(update: Update, context):
    if not context.args or context.args[0] not in ticket_status:
        await update.message.reply_text("/status BV-XXXXX")
        return
    tid = context.args[0]
    await update.message.reply_text(
        f"🎫 Ticket ID: {mono(tid)}\nStatus: {ticket_status[tid]}",
        parse_mode="Markdown"
    )

# ================= SEND =================
async def send(update: Update, context):
    if update.effective_chat.id != GROUP_ID or len(context.args) < 2:
        return

    target = context.args[0]
    msg = " ".join(context.args[1:])
    targets = set()

    if target == "@all":
        targets = set(user_tickets.keys())

    elif target.startswith("BV-"):
        if target in ticket_status and ticket_status[target] != "Closed":
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
        await context.bot.send_message(uid, msg)

    await update.message.reply_text("✅ Sent")

# ================= CLOSE =================
async def close(update: Update, context):
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

    await context.bot.send_message(uid, f"🎫 Ticket {mono(tid)} Closed", parse_mode="Markdown")

# ================= OPEN =================
async def open_ticket(update: Update, context):
    tid = context.args[0]
    if tid in ticket_status and ticket_status[tid] == "Closed":
        ticket_status[tid] = "Processing"
        user_active_ticket[ticket_user[tid]] = tid
        await update.message.reply_text(f"Reopened {mono(tid)}", parse_mode="Markdown")

# ================= EXPORT =================
async def export(update: Update, context):
    tid = context.args[0]
    buf = BytesIO()
    for a,b in ticket_messages.get(tid, []):
        buf.write(f"{a}: {b}\n".encode())
    buf.seek(0)
    buf.name = f"{tid}.txt"
    await context.bot.send_document(GROUP_ID, buf)

# ================= HISTORY =================
async def history(update: Update, context):
    target = context.args[0]
    uid = int(target) if target.isdigit() else None
    if target.startswith("@"):
        for t,u in ticket_username.items():
            if u.lower()==target[1:].lower():
                uid = ticket_user[t]

    if uid not in user_tickets:
        return

    text=""
    for i,t in enumerate(user_tickets[uid],1):
        text+=f"{i}. {mono(t)}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# ================= USER LIST =================
async def users(update: Update, context):
    buf=BytesIO()
    buf.write(b"BlockVeil Support Users\n\n")
    for i,(uid) in enumerate(user_tickets.keys(),1):
        buf.write(f"{i}: {uid}\n".encode())
    buf.seek(0)
    buf.name="users.txt"
    await context.bot.send_document(GROUP_ID,buf)

# ================= LIST =================
async def list_t(update: Update, context):
    mode=context.args[0].lower()
    out=[]
    for t,s in ticket_status.items():
        if mode in ["open","opened"] and s!="Closed":
            out.append(t)
        if mode in ["close","closed"] and s=="Closed":
            out.append(t)
    await update.message.reply_text(
        "\n".join([mono(x) for x in out]),
        parse_mode="Markdown"
    )

# ================= INIT =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(create_ticket, pattern="create"))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("send", send))
app.add_handler(CommandHandler("close", close))
app.add_handler(CommandHandler("open", open_ticket))
app.add_handler(CommandHandler("export", export))
app.add_handler(CommandHandler("history", history))
app.add_handler(CommandHandler("user", users))
app.add_handler(CommandHandler("list", list_t))
app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, user_msg))
app.add_handler(MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, group_reply))

app.run_polling()
