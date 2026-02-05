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
import itertools
from io import BytesIO

# ================= ENV =================
TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID"))

# ================= STORAGE (IN-MEMORY) =================
ticket_counter = itertools.count(10000)

user_active_ticket = {}          # user_id -> ticket_id
ticket_status = {}               # ticket_id -> status
ticket_user = {}                 # ticket_id -> user_id
ticket_username = {}             # ticket_id -> username
ticket_messages = {}             # ticket_id -> [(sender, text)]
user_tickets = {}                # user_id -> [ticket_ids]
group_message_map = {}           # group_msg_id -> ticket_id


# ================= HELPERS =================
def generate_ticket_id():
    return f"BV-{next(ticket_counter)}"

def ticket_header(ticket_id, status):
    return f"🎫 Ticket ID: {ticket_id}\nStatus: {status}\n\n"

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
        "You can contact the BlockVeil team using this bot.\n\n"
        "🔐 Privacy Notice\n"
        "Your information is kept strictly confidential.\n\n"
        "📧 support.blockveil@protonmail.com\n\n"
        "—\nBlockVeil Support Team",
        reply_markup=keyboard
    )


# ================= CREATE TICKET =================
async def create_ticket(update: Update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if user.id in user_active_ticket:
        await query.message.reply_text(
            f"🎫 You already have an active ticket:\n{user_active_ticket[user.id]}"
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
        f"🎫 Ticket Created: {ticket_id}\n"
        "Status: Pending\n\n"
        "Please send your message."
    )


# ================= USER MESSAGE =================
async def user_message(update: Update, context):
    user = update.message.from_user

    if user.id not in user_active_ticket:
        await update.message.reply_text("❗ Please create a ticket first.")
        return

    ticket_id = user_active_ticket[user.id]

    if ticket_status[ticket_id] == "Pending":
        ticket_status[ticket_id] = "Processing"

    header = (
        ticket_header(ticket_id, ticket_status[ticket_id]) +
        user_info_block(user) +
        "Message:\n"
    )

    sent = None
    text_content = None

    if update.message.text:
        text_content = update.message.text
        sent = await context.bot.send_message(
            chat_id=GROUP_ID,
            text=header + text_content
        )

    elif update.message.photo:
        text_content = "[Photo]"
        sent = await context.bot.send_photo(
            chat_id=GROUP_ID,
            photo=update.message.photo[-1].file_id,
            caption=header + text_content
        )

    elif update.message.voice:
        text_content = "[Voice Message]"
        sent = await context.bot.send_voice(
            chat_id=GROUP_ID,
            voice=update.message.voice.file_id,
            caption=header + text_content
        )

    elif update.message.document:
        text_content = "[File]"
        sent = await context.bot.send_document(
            chat_id=GROUP_ID,
            document=update.message.document.file_id,
            caption=header + text_content
        )

    if sent:
        group_message_map[sent.message_id] = ticket_id
        ticket_messages[ticket_id].append(
            (user.first_name, text_content)
        )


# ================= GROUP REPLY =================
async def group_reply(update: Update, context):
    if not update.message.reply_to_message:
        return

    reply_id = update.message.reply_to_message.message_id
    if reply_id not in group_message_map:
        return

    ticket_id = group_message_map[reply_id]
    user_id = ticket_user[ticket_id]

    # CLOSE TICKET
    if update.message.text and update.message.text.strip() == "/close":
        ticket_status[ticket_id] = "Closed"
        user_active_ticket.pop(user_id, None)

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"🎫 Ticket ID: {ticket_id}\n"
                "Status: Closed\n\n"
                "Thank you for contacting BlockVeil Support."
            )
        )
        return

    prefix = f"🎫 Ticket ID: {ticket_id}\n\n"
    agent_name = "BlockVeil Support"

    if update.message.text:
        await context.bot.send_message(
            chat_id=user_id,
            text=prefix + update.message.text
        )
        ticket_messages[ticket_id].append(
            (agent_name, update.message.text)
        )


# ================= /history BV-XXXXX =================
async def history(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return

    if not context.args:
        return

    ticket_id = context.args[0]
    if ticket_id not in ticket_messages:
        await update.message.reply_text("❌ Ticket not found.")
        return

    buffer = BytesIO()
    buffer.write(
        f"Ticket ID: {ticket_id}\n"
        f"Status: {ticket_status[ticket_id]}\n\nConversation Log\n\n".encode()
    )

    for sender, msg in ticket_messages[ticket_id]:
        buffer.write(f"{sender} : {msg}\n\n".encode())

    buffer.seek(0)
    buffer.name = f"{ticket_id}.txt"

    await context.bot.send_document(
        chat_id=GROUP_ID,
        document=buffer
    )


# ================= /historyticket =================
async def historyticket(update: Update, context):
    if update.effective_chat.id != GROUP_ID:
        return

    if not context.args:
        return

    target = context.args[0]
    user_id = None

    if target.startswith("@"):
        username = target[1:]
        for tid, uname in ticket_username.items():
            if uname == username:
                user_id = ticket_user[tid]
                break
    else:
        user_id = int(target)

    if user_id not in user_tickets:
        await update.message.reply_text("No tickets found.")
        return

    text = "🎫 Ticket History\n\n"
    for i, tid in enumerate(user_tickets[user_id], 1):
        text += f"{i}. {tid}\n"

    await update.message.reply_text(text)


# ================= INIT =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("history", history))
app.add_handler(CommandHandler("historyticket", historyticket))
app.add_handler(CallbackQueryHandler(create_ticket, pattern="create_ticket"))
app.add_handler(MessageHandler(filters.ChatType.PRIVATE, user_message))
app.add_handler(MessageHandler(filters.ChatType.GROUPS, group_reply))

app.run_polling()
