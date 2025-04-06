import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# تنظیم لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# توکن و آدرس وب‌هوک
TOKEN = '8045348833:AAEZDh60grBIHTz5mOUYEHK7ZLEV7B2npTc'
WEBHOOK_URL = "https://chat-bot-9v1s.onrender.com/webhook"

# تابع تمیز کردن متن برای MarkdownV2
def clean_text(text):
    if not text:
        return ""
    reserved_chars = r"([_*[\]()~`>#+\-=|{}.!])"
    return re.sub(reserved_chars, r"\\\1", text)

# تابع دستور /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"دریافت دستور /start از کاربر {user_id}")
    user_name = update.message.from_user.first_name
    welcome_message = clean_text(
        f"سلام {user_name}!\nبه PlatoDex خوش اومدی - مرکز بازی‌های Plato!\n"
        "• چت با هوش مصنوعی 🤖\n• تولید تصویر 🖼️"
    )
    keyboard = [
        [InlineKeyboardButton("Run App 📱", web_app={"url": "https://platodex-tde3qe.vercel.app/"})],
        [InlineKeyboardButton("Chat with AI 🤖", callback_data="chat_with_ai")],
        [InlineKeyboardButton("Generate Image 🖼️", callback_data="generate_image")]
    ]
    await update.message.reply_text(
        welcome_message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="MarkdownV2"
    )

# تابع اصلی برای اجرای ربات
def main():
    # ساخت Application
    application = Application.builder().token(TOKEN).read_timeout(60).write_timeout(60).connect_timeout(60).build()

    # اضافه کردن Handler برای دستور /start
    application.add_handler(CommandHandler("start", start))

    # اجرای ربات با وب‌هوک
    application.run_webhook(
        listen="0.0.0.0",
        port=8000,
        url_path="/webhook",
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    main()
