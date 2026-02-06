from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
)
import os
import random
import string
from io import BytesIO

# ================= ENV =================
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
def generate_ticket_id(length=8):
    chars = string.ascii_letters + string.digits + "*#@$&"
    return "BV-" + "".join(random.choice(chars) for _ in range(length))

def mono(tid):
    return f"`{tid}`"

def ticket_header(ticket_id, status):
    return f"🎫 Ticket ID: {mono(ticket_id)}\nStatus: {status}\n\n"

def user_info_block(user):
    return (
        "User Information\n"
        f"• User ID   : {user.id}\n"
        f"• Username  : @{user.username}\n"
        f"• Full Name : {user.first_name}\n\n"
    )

# ================= /start =================
async def start(update: Update, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟️ Create Ticket", callback_data="create_ticket")]
    ])
    await update.message.reply_text(
        "Hello Sir/Mam 👋\n\n"
        "Welcome to BlockVeil Support.\n"
        "Use the button below to create a support ticket.\n\n"
        "📧 support.blockveil@protonmail.com\n\n"
        "— BlockVeil Support Team",
        reply_markup=keyboard
    )

# ================= CREATE TICKET =================
async def create_ticket(update: Update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if user.id in user_active_ticket:
        await query.message.reply_text(
            f"🎫 You already have an active ticket:\n{mono(user_active_ticket[user.id])}"
        )
        return

    ticket_id = generate_ticket_id()
    user_active_ticket[user.id] = ticket_id
    ticket_status[ticket_id] = "Pending"
    ticket_user[ticket_id] = user.id
    ticket_username[ticket_id] = user.username
    ticket_messages[ticket_id] = []
    user_tickets.setdefault(user.id, []).append(ticket_id)

    await query.message.reply_text(
        f"🎫 Ticket Created: {mono(ticket_id)}\n"
        "Status: Pending\n\n"
        "Please send your message, photo, voice, video, or file."
    )

# ================= USER MESSAGE =================
async def user_message(update: Update, context):
    user = update.message.from_user

    if user.id not in user_active_ticket:
        await update.message.reply_text(
            "❗ Please create a ticket first.\n\n"
            "Click /start to submit a new support ticket.\n\n"
            "To track an existing ticket, please use the /status command."
        )
        return

    ticket_id = user_active_ticket[user.id]
    if ticket_status[ticket_id] == "Pending":
        ticket_status[ticket_id] = "Processing"

    header = ticket_header(ticket_id, ticket_status[ticket_id]) + user_info_block(user) + "Message:\n"

    sent = None
    log = ""

    if update.message.text:
        log = update.message.text
        sent = await context.bot.send_message(GROUP_ID, header + log)

    elif update.message.photo:
        log = "[Photo]"
        sent = await context.bot.send_photo(GROUP_ID, update.message.photo[-1].file_id, caption=header + log)

    elif update.message.voice:
        log = "[Voice]"
        sent = await context.bot.send_voice(GROUP_ID, update.message.voice.file_id, caption=header + log)

    elif update.message.video:
        log = "[Video]"
        sent = await context.bot.send_video(GROUP_ID, update.message.video.file_id, caption=header + log)

    elif update.message.document:
        log = "[Document]"
        sent = await context.bot.send_document(GROUP_ID, update.message.document.file_id, caption=header + log)

    if sent:
        group_message_map[sent.message_id] = ticket_id
        ticket_messages[ticket_id].append((user.first_name, log))

# ================= GROUP REPLY =================
async def group_reply(update: Update, context):
    if not update.message.reply_to_message:
        return
    mid = update.message.reply_to_message.message_id
    if mid not in group_message_map:
        return

    ticket_id = group_message_map[mid]
    uid = ticket_user[ticket_id]

    prefix = f"🎫 Ticket ID: {mono(ticket_id)}\n\n"

    if update.message.text:
        await context.bot.send_message(uid, prefix + update.message.text)
        ticket_messages[ticket_id].append(("BlockVeil Support", update.message.text))

# ================= /close =================
async def close_ticket(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return

    tid = context.args[0] if context.args else None
    if not tid and update.message.reply_to_message:
        tid = group_message_map.get(update.message.reply_to_message.message_id)

    if not tid or tid not in ticket_status:
        await update.message.reply_text("❌ Ticket not found.")
        return

    ticket_status[tid] = "Closed"
    user_active_ticket.pop(ticket_user[tid], None)

    await context.bot.send_message(ticket_user[tid], f"🎫 Ticket ID: {mono(tid)}\nStatus: Closed")
    await update.message.reply_text(f"✅ Ticket {mono(tid)} closed.")

# ================= /export =================
async def export_ticket(update: Update, context):
    if update.effective_chat.id != GROUP_ID or not context.args:
        return

    tid = context.args[0]
    if tid not in ticket_messages:
        await update.message.reply_text("❌ Ticket not found.")
        return

    buf = BytesIO()
    buf.write(f"Ticket ID: {tid}\nStatus: {ticket_status[tid]}\n\n".encode())

    for sender, msg in ticket_messages[tid]:
        buf.write(f"{sender}: {msg}\n\n".encode())

    buf.seek(0)
    buf.name = f"{tid}.txt"

    await context.bot.send_document(GROUP_ID, buf)

# ================= /history =================
async def history_user(update: Update, context):
    if update.effective_chat.id != GROUP_ID or not context.args:
        return

    target = context.args[0]
    uid = None

    if target.startswith("@"):
        for tid, uname in ticket_username.items():
            if uname == target[1:]:
                uid = ticket_user[tid]
                break
    else:
        uid = int(target)

    if uid not in user_tickets:
        await update.message.reply_text("No tickets found.")
        return

    text = "🎫 Ticket History\n\n"
    for i, tid in enumerate(user_tickets[uid], 1):
        text += f"{i}. {mono(tid)}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# ================= /user =================
async def user_list(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return

    buf = BytesIO()
    buf.write("BlockVeil Support User List\n\n".encode())

    seen = set()
    i = 1
    for tid, uid in ticket_user.items():
        if uid in seen:
            continue
        seen.add(uid)
        uname = ticket_username.get(tid)
        buf.write(f"{i} : @{uname} — {uid}\n".encode())
        i += 1

    buf.seek(0)
    buf.name = "blockveil_users.txt"
    await context.bot.send_document(GROUP_ID, buf)

# ================= INIT =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("close", close_ticket))
app.add_handler(CommandHandler("export", export_ticket))
app.add_handler(CommandHandler("history", history_user))
app.add_handler(CommandHandler("user", user_list))
app.add_handler(CallbackQueryHandler(create_ticket, pattern="create_ticket"))
app.add_handler(MessageHandler(filters.ChatType.PRIVATE, user_message))
app.add_handler(MessageHandler(filters.ChatType.GROUPS, group_reply))

app.run_polling()
