import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

def init_db():
    conn = sqlite3.connect('sbpay.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, joined_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS activity
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT, created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    return sqlite3.connect('sbpay.db')

SERVICES = [
    "Design & Creative",
    "Writing & Translation",
    "Tech Support",
    "Marketing & Social",
    "Tutoring & Education",
]

async def ensure_user(user_id, username):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, joined_at) VALUES (?,?,?)",
              (user_id, username or "", datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

def add_points(user_id, n, action):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET points = points + ? WHERE user_id=?", (n, user_id))
    c.execute("INSERT INTO activity (user_id, action, created_at) VALUES (?,?,?)",
              (user_id, action, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await ensure_user(u.id, u.username)
    keyboard = [
        [InlineKeyboardButton("🗂 Browse Services", callback_data='services')],
        [InlineKeyboardButton("🤝 Connect with People", callback_data='connect')],
        [InlineKeyboardButton("⭐ My Activity Points", callback_data='points')],
        [InlineKeyboardButton("❓ Help", callback_data='help')],
    ]
    await update.message.reply_text(
        "Welcome to Sb Pay.\n\n"
        "Discover services, connect with people, explore opportunities, "
        "and track your activity points — all in one place.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Sb Pay Help:\n"
        "/start - Main menu\n"
        "/services - Browse available services\n"
        "/connect - Connect with people\n"
        "/points - View your activity points\n"
        "/help - Show this help\n\n"
        "Sb Pay is a discovery and connection assistant. "
        "Activity points reflect in-app engagement only and are not cash."
    )

async def services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Available service categories:\n\n" + "\n".join(f"• {s}" for s in SERVICES)
    text += "\n\nSelect a category from the menu to explore."
    keyboard = [[InlineKeyboardButton(s, callback_data=f"svc_{i}")] for i, s in enumerate(SERVICES)]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def connect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Connect with people:\n\n"
        "Share your interests and what you are looking for in this format:\n"
        "Interest | What you offer\n"
        "Example: Design | Logo and branding help"
    )
    context.user_data['awaiting_connect'] = True

async def points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    c.execute("SELECT action, created_at FROM activity WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,))
    recent = c.fetchall()
    conn.close()
    pts = row[0] if row else 0
    lines = "\n".join(f"• {a} ({t})" for a, t in recent) if recent else "No activity yet."
    await update.message.reply_text(
        f"⭐ Your activity points: {pts}\n\nRecent activity:\n{lines}\n\n"
        "Points reflect in-app engagement only and are not cash or withdrawable."
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    if q.data == 'services':
        text = "Available service categories:\n\n" + "\n".join(f"• {s}" for s in SERVICES)
        keyboard = [[InlineKeyboardButton(s, callback_data=f"svc_{i}")] for i, s in enumerate(SERVICES)]
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif q.data == 'connect':
        await q.edit_message_text(
            "Share your interests in this format:\nInterest | What you offer\n"
            "Example: Design | Logo and branding help"
        )
        context.user_data['awaiting_connect'] = True
    elif q.data == 'points':
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        pts = row[0] if row else 0
        await q.edit_message_text(
            f"⭐ Your activity points: {pts}\n\n"
            "Points reflect in-app engagement only and are not cash or withdrawable."
        )
    elif q.data == 'help':
        await q.edit_message_text(
            "Sb Pay is a free assistant to discover services and connect with people.\n"
            "Use /start to return to the menu."
        )
    elif q.data.startswith('svc_'):
        idx = int(q.data.split('_')[1])
        cat = SERVICES[idx]
        add_points(user_id, 1, f"Viewed {cat}")
        await q.edit_message_text(
            f"🗂 {cat}\n\n"
            "This category is available for discovery. "
            "You earned 1 activity point for exploring.\n\n"
            "Use /connect to share what you offer, or /start to go back."
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_connect'):
        context.user_data['awaiting_connect'] = False
        parts = update.message.text.split('|')
        if len(parts) != 2:
            await update.message.reply_text("Invalid format. Use: Interest | What you offer")
            return
        interest = parts[0].strip()
        offer = parts[1].strip()
        add_points(update.effective_user.id, 2, f"Connected: {interest}")
        await update.message.reply_text(
            f"✅ Saved your profile note.\nInterest: {interest}\nOffer: {offer}\n\n"
            "You earned 2 activity points for connecting."
        )
        return
    await update.message.reply_text("Use /start to see the menu, or /help for instructions.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("services", services_command))
    app.add_handler(CommandHandler("connect", connect_command))
    app.add_handler(CommandHandler("points", points_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Sb Pay bot starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
