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

# ================= STORAGE (IN-MEMORY) =================
user_active_ticket = {}      # user_id -> active ticket_id
ticket_status = {}           # ticket_id -> status
ticket_user = {}             # ticket_id -> user_id
ticket_username = {}         # ticket_id -> username
ticket_messages = {}         # ticket_id -> list of (sender, text)
user_tickets = {}            # user_id -> [ticket_ids]
group_message_map = {}       # group_message_id -> ticket_id

# ================= HELPERS =================
def generate_ticket_id(length=8):
    chars = string.ascii_letters + string.digits + "*#@$&"
    return "BV-" + "".join(random.choice(chars) for _ in range(length))

def mono(tid):
    # inline code formatting (mono)
    return f"`{tid}`"

def ticket_header(tid, status):
    return f"🎫 Ticket ID: {mono(tid)}\nStatus: {status}\n\n"

def user_info_block(user):
    username = user.username if user.username else "N/A"
    return (
        "User Information\n"
        f"• User ID   : {user.id}\n"
        f"• Username  : @{username}\n"
        f"• Full Name : {user.first_name or ''}\n\n"
    )

# ================= /start =================
async def start(update: Update, context):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎟️ Create Ticket", callback_data="create_ticket")]])
    await update.message.reply_text(
        "Hello 👋\n\nWelcome to BlockVeil Support.\nUse the button below to create a support ticket.",
        reply_markup=kb
    )

# ================= CREATE TICKET (button) =================
async def create_ticket(update: Update, context):
    q = update.callback_query
    await q.answer()
    u = q.from_user

    if u.id in user_active_ticket:
        await q.message.reply_text(
            f"🎫 You already have an active ticket:\n{mono(user_active_ticket[u.id])}",
            parse_mode="Markdown"
        )
        return

    tid = generate_ticket_id()
    user_active_ticket[u.id] = tid
    ticket_status[tid] = "Pending"
    ticket_user[tid] = u.id
    ticket_username[tid] = u.username or ""
    ticket_messages[tid] = []
    user_tickets.setdefault(u.id, []).append(tid)

    await q.message.reply_text(
        f"🎫 Ticket Created: {mono(tid)}\nStatus: Pending\n\nPlease send your message, photo, voice, video, or file.",
        parse_mode="Markdown"
    )

# ================= USER MESSAGE (TEXT + MEDIA) =================
async def user_message(update: Update, context):
    u = update.message.from_user

    if u.id not in user_active_ticket:
        await update.message.reply_text(
            "❗ Please create a ticket first.\n\nClick /start to submit a new support ticket.\nTo track an existing ticket, use /status BV-XXXXX"
        )
        return

    tid = user_active_ticket[u.id]
    if ticket_status.get(tid) == "Pending":
        ticket_status[tid] = "Processing"

    header = ticket_header(tid, ticket_status[tid]) + user_info_block(u) + "Message:\n"
    sent = None
    log_text = ""

    # TEXT
    if update.message.text:
        log_text = update.message.text
        sent = await context.bot.send_message(
            chat_id=GROUP_ID,
            text=header + log_text,
            parse_mode="Markdown"
        )

    # PHOTO
    elif update.message.photo:
        log_text = "[Photo]"
        sent = await context.bot.send_photo(
            chat_id=GROUP_ID,
            photo=update.message.photo[-1].file_id,
            caption=header + log_text,
            parse_mode="Markdown"
        )

    # VOICE
    elif update.message.voice:
        log_text = "[Voice]"
        sent = await context.bot.send_voice(
            chat_id=GROUP_ID,
            voice=update.message.voice.file_id,
            caption=header + log_text,
            parse_mode="Markdown"
        )

    # VIDEO
    elif update.message.video:
        log_text = "[Video]"
        sent = await context.bot.send_video(
            chat_id=GROUP_ID,
            video=update.message.video.file_id,
            caption=header + log_text,
            parse_mode="Markdown"
        )

    # DOCUMENT / FILE
    elif update.message.document:
        log_text = "[Document]"
        sent = await context.bot.send_document(
            chat_id=GROUP_ID,
            document=update.message.document.file_id,
            caption=header + log_text,
            parse_mode="Markdown"
        )

    if sent:
        group_message_map[sent.message_id] = tid
        ticket_messages.setdefault(tid, []).append((u.first_name or str(u.id), log_text))

# ================= GROUP REPLY (TEXT + MEDIA) =================
async def group_reply(update: Update, context):
    if not update.message.reply_to_message:
        return

    reply_mid = update.message.reply_to_message.message_id
    if reply_mid not in group_message_map:
        return

    tid = group_message_map[reply_mid]
    uid = ticket_user.get(tid)
    if not uid:
        return

    prefix = f"🎫 Ticket ID: {mono(tid)}\n\n"

    # TEXT
    if update.message.text:
        text = update.message.text
        await context.bot.send_message(chat_id=uid, text=prefix + text, parse_mode="Markdown")
        ticket_messages.setdefault(tid, []).append(("BlockVeil Support", text))

    # PHOTO
    elif update.message.photo:
        await context.bot.send_photo(chat_id=uid, photo=update.message.photo[-1].file_id, caption=prefix, parse_mode="Markdown")
        ticket_messages.setdefault(tid, []).append(("BlockVeil Support", "[Photo]"))

    # VOICE
    elif update.message.voice:
        await context.bot.send_voice(chat_id=uid, voice=update.message.voice.file_id, caption=prefix, parse_mode="Markdown")
        ticket_messages.setdefault(tid, []).append(("BlockVeil Support", "[Voice]"))

    # VIDEO
    elif update.message.video:
        await context.bot.send_video(chat_id=uid, video=update.message.video.file_id, caption=prefix, parse_mode="Markdown")
        ticket_messages.setdefault(tid, []).append(("BlockVeil Support", "[Video]"))

    # DOCUMENT
    elif update.message.document:
        await context.bot.send_document(chat_id=uid, document=update.message.document.file_id, caption=prefix, parse_mode="Markdown")
        ticket_messages.setdefault(tid, []).append(("BlockVeil Support", "[Document]"))

# ================= /status BV-XXXXX =================
async def status_ticket(update: Update, context):
    if not context.args:
        await update.message.reply_text("/status BV-XXXXX  [ টিকেট স্টাটাস দেখা যাবে। ]")
        return

    tid = context.args[0]
    if tid not in ticket_status:
        await update.message.reply_text("❌ Ticket not found.")
        return

    text = f"🎫 Ticket ID: {mono(tid)}\nStatus: {ticket_status[tid]}"
    await update.message.reply_text(text, parse_mode="Markdown")

# ================= /send (ticket | @username | user_id | @all) =================
async def send_direct(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "/send BV-XXXXX your message\n/send @username your message\n/send user_id your message\n\n[ Ticket closed থাকলে message যাবে না এবং Username / ID valid হতে হবে ]"
        )
        return

    target = context.args[0]
    message = " ".join(context.args[1:])
    targets = set()

    # @all
    if target == "@all":
        # collect unique user ids from user_tickets (all users who ever opened tickets)
        targets = set(user_tickets.keys())

    # by ticket id
    elif target.startswith("BV-"):
        tid = target
        if tid not in ticket_status:
            await update.message.reply_text("❌ Ticket not found.")
            return
        if ticket_status.get(tid) == "Closed":
            await update.message.reply_text("⚠️ Ticket closed — message not sent.")
            return
        uid = ticket_user.get(tid)
        if uid:
            targets.add(uid)

    # by username
    elif target.startswith("@"):
        uname = target[1:]
        # find all tickets for this username and add their user ids
        for t, u_name in ticket_username.items():
            if u_name and u_name.lower() == uname.lower():
                uid = ticket_user.get(t)
                if uid:
                    targets.add(uid)

    # by numeric user id
    else:
        try:
            uid = int(target)
            targets.add(uid)
        except:
            pass

    if not targets:
        await update.message.reply_text("❌ No valid user found.")
        return

    for uid in targets:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📩 BlockVeil Support:\n\n{message}")
        except Exception:
            # ignore send failures per-user
            pass

    await update.message.reply_text("✅ Message sent.")

# ================= /close (reply or /close BV-XXXXX) =================
async def close_ticket(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return

    tid = None
    if context.args:
        tid = context.args[0]
    elif update.message.reply_to_message:
        tid = group_message_map.get(update.message.reply_to_message.message_id)

    if not tid or tid not in ticket_status:
        await update.message.reply_text("/close [ মেসেজের ticket এর reply দিয়ে দিলে ticket close হবে ]\n/close BV-XXXXX [ টিকেট close হবে ]")
        return

    ticket_status[tid] = "Closed"
    uid = ticket_user.get(tid)
    if uid:
        user_active_ticket.pop(uid, None)
        await context.bot.send_message(chat_id=uid, text=f"🎫 Ticket ID: {mono(tid)}\nStatus: Closed", parse_mode="Markdown")

    await update.message.reply_text(f"✅ Ticket {mono(tid)} closed.", parse_mode="Markdown")

# ================= /open BV-XXXXX =================
async def open_ticket(update: Update, context):
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
        await context.bot.send_message(chat_id=uid, text=f"🎫 Ticket ID: {mono(tid)}\nStatus: Reopened", parse_mode="Markdown")

    await update.message.reply_text(f"✅ Ticket {mono(tid)} reopened.", parse_mode="Markdown")

# ================= /export BV-XXXXX =================
async def export_ticket(update: Update, context):
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

# ================= /history (user id or @username) =================
async def history_user(update: Update, context):
    if update.effective_chat.id != GROUP_ID or not context.args:
        return

    target = context.args[0]
    uid = None

    # by @username
    if target.startswith("@"):
        uname = target[1:]
        # find a user id by scanning ticket_username
        for tid, uname_val in ticket_username.items():
            if uname_val and uname_val.lower() == uname.lower():
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
        text += f"{i}. {mono(t)}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# ================= /user (export user list) =================
async def user_list(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return

    seen = set()
    buf = BytesIO()
    buf.write("BlockVeil Support User list\n\n".encode())
    i = 1
    for tid, uid in ticket_user.items():
        if uid in seen:
            continue
        seen.add(uid)
        # try to get username via any ticket of this user
        uname = ticket_username.get(tid) or ""
        buf.write(f"{i} : @{uname} — {uid}\n".encode())
        i += 1

    buf.seek(0)
    buf.name = "blockveil_users.txt"
    await context.bot.send_document(chat_id=GROUP_ID, document=buf)

# ================= /list opened/closed alias wrapper =================
# (handled by list_tickets)

async def list_tickets(update: Update, context):
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

    txt = ""
    for i, tid in enumerate(out, 1):
        txt += f"{i}. {mono(tid)}\n"

    await update.message.reply_text(txt, parse_mode="Markdown")

# ================= INIT / HANDLERS =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(create_ticket, pattern="create_ticket"))

# User handlers
app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.ALL, user_message))

# Group (agent) commands & handlers
app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.ALL, group_reply))
app.add_handler(CommandHandler("status", status_ticket))
app.add_handler(CommandHandler("send", send_direct))
app.add_handler(CommandHandler("close", close_ticket))
app.add_handler(CommandHandler("open", open_ticket))
app.add_handler(CommandHandler("export", export_ticket))
app.add_handler(CommandHandler("history", history_user))
app.add_handler(CommandHandler("user", user_list))
app.add_handler(CommandHandler("list", list_tickets))

app.run_polling()
