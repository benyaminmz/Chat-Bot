from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes, InlineQueryHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
import requests
from bs4 import BeautifulSoup
import json
import re
import html
import logging
import asyncio
import time
from fastapi import FastAPI, Request
import uvicorn
from PIL import Image
import io
import tempfile
import os
from threading import Lock

# تنظیم لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# توکن و آدرس‌ها
TOKEN = '5287864667:AAGs4CJ0DW1qhfsA447Kvyz-WJFlUbIeBh4'
IMAGE_API_URL = 'https://pollinations.ai/prompt/'
TEXT_API_URL = 'https://text.pollinations.ai/'
URL = "https://platopedia.com/items"
BASE_IMAGE_URL = "https://profile.platocdn.com/"
WEBHOOK_URL = "https://platodex.onrender.com/webhook"
EXTRACTED_ITEMS = []
AI_CHAT_USERS = set()
SEARCH_ITEM, SELECT_CATEGORY = range(2)
SELECT_SIZE, GET_PROMPT = range(2, 4)
DEFAULT_CHAT_ID = 789912945
PROCESSED_MESSAGES = set()
PROCESSING_LOCK = Lock()

SYSTEM_MESSAGE = (
    "شما دستیار هوشمند PlatoDex هستید و درمورد پلاتو به کاربران کمک میکنید و به صورت خودمونی جذاب و با ایموجی "
    "حرف میزنی به صورت نسل z و کمی با طنز حرف بزن و شوخی کنه\\. به مشخصات آیتم‌های پلاتو دسترسی داری و می‌تونی "
    "به سوالات کاربر در مورد آیتم‌ها جواب بدی و راهنمایی کنی چطور با دستور /i مشخصات کامل رو بگیرن\\. "
    "این پیام آموزشی رو توی هر پاسخ تکرار نکن، فقط توی ذهنت نگه دار و بر اساسش عمل کن\\."
)

application = None

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    global application
    update = await request.json()
    update_obj = Update.de_json(update, application.bot)
    update_id = update_obj.update_id
    logger.info(f"دریافت درخواست با update_id: {update_id}")
    with PROCESSING_LOCK:
        if update_id in PROCESSED_MESSAGES:
            logger.warning(f"درخواست تکراری با update_id: {update_id} - نادیده گرفته شد")
            return {"status": "ok"}
        PROCESSED_MESSAGES.add(update_id)
    asyncio.create_task(application.process_update(update_obj))
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "PlatoDex Bot is running!"}

def clean_text(text):
    if not text:
        return ""
    reserved_chars = r"([_*[\]()~`>#+\-=|{}.!])"
    return re.sub(reserved_chars, r"\\\1", text)

async def extract_items(context: ContextTypes.DEFAULT_TYPE = None):
    global EXTRACTED_ITEMS
    EXTRACTED_ITEMS = []
    max_retries = 3
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            response = requests.get(URL, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            script_tag = soup.find("script", string=re.compile(r"var items = {"))
            if not script_tag:
                logger.error("داده‌های آیتم‌ها پیدا نشد!")
                if context and hasattr(context.bot, 'send_message'):
                    await context.bot.send_message(chat_id=DEFAULT_CHAT_ID, text=clean_text("مشکلی تو بارگذاری آیتم‌ها پیش اومد!"))
                return
            items_data = json.loads(re.search(r"var items = ({.*?});", script_tag.string, re.DOTALL).group(1))
            table = soup.find("table", id="tool_items_table_default")
            item_details = {}
            if table:
                for row in table.find("tbody").find_all("tr"):
                    cols = row.find_all("td")
                    item_id = row["id"].replace("id-", "")
                    item_columns = {f"column_{i+1}": col.text.strip() for i, col in enumerate(cols)}
                    price_text = item_columns.get("column_4", "0")
                    price_value = int(re.search(r"\d[\d,]*", price_text).group().replace(",", "")) if re.search(r"\d[\d,]*", price_text) else 0
                    price_type = "premium" if price_value < 100 else "coins"
                    item_details[item_id] = {"columns": item_columns, "price": {"value": price_value, "type": price_type}}
            
            for item_id, item_info in items_data.items():
                med = item_info.get("med", {})
                images = [BASE_IMAGE_URL + img["uri"] for img in med.get("images", [])]
                audios = [{"uri": audio["uri"], "type": audio.get("type", "unknown")} for audio in med.get("audios", [])]
                details = item_details.get(item_id, {})
                columns = details.get("columns", {})
                if columns:
                    EXTRACTED_ITEMS.append({
                        "id": item_id,
                        "name": clean_text(columns.get("column_3", "Unknown Item")),
                        "category": clean_text(columns.get("column_2", "Unknown")),
                        "description": clean_text(columns.get("column_5", "No description available")),
                        "price": details.get("price", {"value": 0, "type": "unknown"}),
                        "images": images,
                        "audios": audios
                    })
            logger.info(f"تعداد آیتم‌ها: {len(EXTRACTED_ITEMS)}")
            if context and hasattr(context.bot, 'send_message'):
                await context.bot.send_message(chat_id=DEFAULT_CHAT_ID, text=clean_text(f"آیتم‌ها به‌روز شدند! تعداد: {len(EXTRACTED_ITEMS)}"), parse_mode="MarkdownV2")
            return
        except (requests.RequestException, requests.Timeout) as e:
            logger.error(f"خطا در تلاش {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                logger.info(f"تلاش دوباره بعد از {retry_delay} ثانیه...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("همه تلاش‌ها ناموفق بود!")
                if context and hasattr(context.bot, 'send_message'):
                    await context.bot.send_message(chat_id=DEFAULT_CHAT_ID, text=clean_text("خطا در به‌روزرسانی آیتم‌ها! بعداً امتحان کنید."), parse_mode="MarkdownV2")
                return

def schedule_scraping(app: Application):
    if app.job_queue is None:
        logger.error("JobQueue فعال نیست!")
        raise RuntimeError("JobQueue فعال نیست!")
    app.job_queue.run_repeating(extract_items, interval=12*60*60, first=0)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in AI_CHAT_USERS:
        AI_CHAT_USERS.remove(user_id)
    context.user_data.clear()
    user_name = update.message.from_user.first_name
    welcome_message = clean_text(
        f"سلام {user_name}!\nبه PlatoDex خوش اومدی - مرکز بازی‌های Plato!\n"
        "• آیتم‌ها رو ببین 🎲\n• رتبه‌بندی بازیکن‌ها رو چک کن 🏆\n• اخبار رو دنبال کن 🎯"
    )
    keyboard = [
        [InlineKeyboardButton("Run App 📱", web_app={"url": "https://platodex-tde3qe.vercel.app/"})],
        [InlineKeyboardButton("Search Items 🔍", callback_data="search_items")],
        [InlineKeyboardButton("Chat with AI 🤖", callback_data="chat_with_ai")],
        [InlineKeyboardButton("Generate Image 🖼️", callback_data="generate_image")]
    ]
    await update.message.reply_text(welcome_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")
    return ConversationHandler.END

async def start_generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("512x512", callback_data="size_512x512")],
        [InlineKeyboardButton("1024x1024", callback_data="size_1024x1024")],
        [InlineKeyboardButton("1280x720", callback_data="size_1280x720")],
        [InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        clean_text("🖼️ Generate Image Mode Activated!\n\nلطفاً سایز تصویر مورد نظر خود را انتخاب کنید:"),
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )
    return SELECT_SIZE

async def select_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    size = query.data
    if size == "size_512x512":
        context.user_data["width"] = 512
        context.user_data["height"] = 512
    elif size == "size_1024x1024":
        context.user_data["width"] = 1024
        context.user_data["height"] = 1024
    elif size == "size_1280x720":
        context.user_data["width"] = 1280
        context.user_data["height"] = 720
    keyboard = [[InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        clean_text(f"سایز تصویر انتخاب شد: {context.user_data['width']}x{context.user_data['height']}\n\nلطفاً توضیحات تصویر (پرامپت) را وارد کنید. مثلاً: 'A cat in a forest'"),
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )
    return GET_PROMPT

async def get_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text.strip()
    if not prompt:
        await update.message.reply_text(clean_text("لطفاً یک توضیح برای تصویر وارد کنید!"), parse_mode="MarkdownV2")
        return GET_PROMPT
    
    width = context.user_data["width"]
    height = context.user_data["height"]
    
    loading_message = await update.message.reply_text(clean_text("🖌️ در حال طراحی عکس... لطفاً صبر کنید."), parse_mode="MarkdownV2")
    
    api_url = f"{IMAGE_API_URL}{prompt}?width={width}&height={height}&nologo=true"
    try:
        response = requests.get(api_url, timeout=30)
        if response.status_code == 200:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_message.message_id)
            keyboard = [
                [InlineKeyboardButton("↩️ برگشت", callback_data="retry_generate_image")],
                [InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_photo(photo=response.content, reply_markup=reply_markup)
        else:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_message.message_id)
            await update.message.reply_text(clean_text("مشکلی در تولید تصویر پیش آمد. لطفاً دوباره امتحان کنید."), parse_mode="MarkdownV2")
    except Exception as e:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_message.message_id)
        await update.message.reply_text(clean_text("خطایی رخ داد. لطفاً بعداً امتحان کنید."), parse_mode="MarkdownV2")
        logger.error(f"خطا در تولید تصویر: {e}")
    
    return ConversationHandler.END

async def retry_generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("512x512", callback_data="size_512x512")],
        [InlineKeyboardButton("1024x1024", callback_data="size_1024x1024")],
        [InlineKeyboardButton("1280x720", callback_data="size_1280x720")],
        [InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        clean_text("🖼️ Generate Image Mode Activated!\n\nلطفاً سایز تصویر مورد نظر خود را انتخاب کنید:"),
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )
    return SELECT_SIZE

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query:
        await update.inline_query.answer([])
        return
    results = []
    for item in EXTRACTED_ITEMS:
        if query.lower() in item["name"].lower() or query.lower() in item["category"].lower():
            price_type = "Pips" if item["price"]["type"] == "premium" else item["price"]["type"]
            price_info = clean_text(f"{item['price']['value']} {price_type}")
            result_content = (
                f"*🔖 نام*: {item['name']}\n"
                f"\n"
                f"*🗃 دسته‌بندی*: {item['category']}\n"
                f"*📃 توضیحات*: {item['description']}\n"
                f"\n"
                f"*💸 قیمت*: {price_info}\n"
                f"*📣 @PlatoDex*"
            )
            results.append(
                InlineQueryResultArticle(
                    id=item["id"],
                    title=item["name"],
                    description=f"{item['category']} - {price_info}",
                    input_message_content=InputTextMessageContent(result_content, parse_mode="MarkdownV2"),
                    thumb_url=item["images"][0] if item["images"] else None
                )
            )
    await update.inline_query.answer(results[:50])

async def handle_inline_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    item = next((i for i in EXTRACTED_ITEMS if i["name"] in message_text), None)
    if not item:
        return
    
    thread_id = update.message.message_thread_id if hasattr(update.message, 'is_topic_message') and update.message.is_topic_message else None
    price_type = "Pips" if item["price"]["type"] == "premium" else item["price"]["type"]
    price_info = clean_text(f"{item['price']['value']} {price_type}")
    results_text = (
        f"*🔖 نام*: {item['name']}\n"
        f"\n"
        f"*🗃 دسته‌بندی*: {item['category']}\n"
        f"*📃 توضیحات*: {item['description']}\n"
        f"\n"
        f"*💸 قیمت*: {price_info}\n"
        f"*📣 @PlatoDex*"
    )
    
    if item["images"]:
        await update.message.reply_photo(
            photo=item["images"][0],
            caption=results_text,
            message_thread_id=thread_id,
            parse_mode="MarkdownV2"
        )
    else:
        await update.message.reply_text(
            results_text,
            message_thread_id=thread_id,
            parse_mode="MarkdownV2"
        )
    
    for i, audio_info in enumerate(item["audios"], 1):
        await send_audio(update, context, item, audio_info, i, None, thread_id)

async def start_item_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    categories = sorted(set(item["category"] for item in EXTRACTED_ITEMS))
    context.user_data["categories"] = categories
    context.user_data["page"] = 0
    keyboard = [
        [InlineKeyboardButton("🔍 جست‌وجو با اسم", callback_data="search_by_name")],
        [InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        clean_text("🔍 می‌خوای آیتم‌ها رو چطوری پیدا کنی؟\nیا از دسته‌بندی‌ها انتخاب کن یا اسم آیتم رو بفرست!"),
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )
    await send_paginated_categories(update, context, is_group=False)
    return SELECT_CATEGORY

async def search_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        clean_text("🔍 لطفاً اسم آیتم رو بفرست!"),
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )
    return SEARCH_ITEM

async def process_item_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_id = update.message.message_id
    with PROCESSING_LOCK:
        if message_id in PROCESSED_MESSAGES:
            logger.warning(f"پیام تکراری در چت خصوصی با message_id: {message_id} - نادیده گرفته شد")
            return SEARCH_ITEM
        PROCESSED_MESSAGES.add(message_id)
    
    user_input = update.message.text.strip().lower()
    matching_items = [item for item in EXTRACTED_ITEMS if user_input in item["name"].lower() or user_input in item["category"].lower()]
    
    if not matching_items:
        keyboard = [[InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")]]
        await update.message.reply_text(clean_text("هیچ آیتمی پیدا نشد! 😕"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")
        return SEARCH_ITEM
    
    context.user_data["matching_items"] = matching_items
    context.user_data["page"] = 0
    await send_paginated_items(update, context, is_group=False)
    return SEARCH_ITEM

async def send_paginated_items(update: Update, context: ContextTypes.DEFAULT_TYPE, is_group=False):
    matching_items = context.user_data["matching_items"]
    page = context.user_data.get("page", 0)
    items_per_page = 10
    total_pages = (len(matching_items) + items_per_page - 1) // items_per_page
    
    start_idx = page * items_per_page
    end_idx = min((page + 1) * items_per_page, len(matching_items))
    current_items = matching_items[start_idx:end_idx]
    
    if len(matching_items) == 1 and not is_group:
        item = matching_items[0]
        price_type = "Pips" if item["price"]["type"] == "premium" else item["price"]["type"]
        price_info = clean_text(f"{item['price']['value']} {price_type}")
        results_text = (
            f"*🔖 نام*: {item['name']}\n"
            f"\n"
            f"*🗃 دسته‌بندی*: {item['category']}\n"
            f"*📃 توضیحات*: {item['description']}\n"
            f"\n"
            f"*💸 قیمت*: {price_info}\n"
            f"*📣 @PlatoDex*"
        )
        keyboard = [[InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if item["images"]:
            await update.message.reply_photo(photo=item["images"][0], caption=results_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
        else:
            await update.message.reply_text(results_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
        for i, audio_info in enumerate(item["audios"], 1):
            await send_audio(update, context, item, audio_info, i, reply_markup)
        return
    
    keyboard = []
    for i, item in enumerate(current_items, start_idx + 1):
        price_type = "Pips" if item["price"]["type"] == "premium" else item["price"]["type"]
        price_info = clean_text(f"{item['price']['value']} {price_type}")
        button_text = clean_text(f"{i}. {item['name']} - {price_info}")
        callback_data = f"select{'_group' if is_group else ''}_item_{item['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"prev_page_{'group' if is_group else 'private'}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"next_page_{'group' if is_group else 'private'}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    if not is_group:
        keyboard.append([InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = clean_text(f"این آیتم‌ها رو پیدا کردم (صفحه {page + 1} از {total_pages})، کدوم رو می‌خوای؟ 👇")
    
    if is_group and update.message:
        thread_id = update.message.message_thread_id if hasattr(update.message, 'is_topic_message') and update.message.is_topic_message else None
        await update.message.reply_text(message_text, reply_markup=reply_markup, message_thread_id=thread_id, parse_mode="MarkdownV2")
    elif update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")

async def send_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, item, audio_info, index, reply_markup=None, thread_id=None):
    audio_url = audio_info["uri"]
    audio_type = audio_info.get("type", "unknown")
    base_url = "https://game-assets-prod.platocdn.com/"
    full_url = base_url + audio_url if not audio_url.startswith("http") else audio_url
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    
    if not message:
        logger.error("پیام برای ارسال وویس پیدا نشد!")
        return
    
    try:
        response = requests.get(full_url, timeout=10)
        if response.status_code == 200:
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name
            with open(temp_file_path, "rb") as voice_file:
                if thread_id:
                    await context.bot.send_voice(
                        chat_id=message.chat_id,
                        voice=voice_file,
                        caption=clean_text(audio_type),
                        message_thread_id=thread_id,
                        reply_markup=reply_markup
                    )
                else:
                    await context.bot.send_voice(
                        chat_id=message.chat_id,
                        voice=voice_file,
                        caption=clean_text(audio_type),
                        reply_markup=reply_markup
                    )
            os.remove(temp_file_path)
    except Exception as e:
        logger.error(f"خطا در دانلود یا ارسال وویس {index}: {e}")
        if thread_id:
            await message.reply_text(clean_text(f"مشکلی توی ارسال وویس {index} پیش اومد! 😅"), message_thread_id=thread_id, parse_mode="MarkdownV2")
        else:
            await message.reply_text(clean_text(f"مشکلی توی ارسال وویس {index} پیش اومد! 😅"), parse_mode="MarkdownV2")

async def select_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_id = query.data.replace("select_item_", "")
    item = next((i for i in EXTRACTED_ITEMS if i["id"] == item_id), None)
    
    if not item:
        await query.edit_message_text(clean_text("آیتم پیدا نشد! 😕"), parse_mode="MarkdownV2")
        return SEARCH_ITEM
    
    price_type = "Pips" if item["price"]["type"] == "premium" else item["price"]["type"]
    price_info = clean_text(f"{item['price']['value']} {price_type}")
    results_text = (
        f"*🔖 نام*: {item['name']}\n"
        f"\n"
        f"*🗃 دسته‌بندی*: {item['category']}\n"
        f"*📃 توضیحات*: {item['description']}\n"
        f"\n"
        f"*💸 قیمت*: {price_info}\n"
        f"*📣 @PlatoDex*"
    )
    
    keyboard = [[InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if item["images"]:
        await query.message.reply_photo(
            photo=item["images"][0],
            caption=results_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    else:
        await query.message.reply_text(
            results_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    
    for i, audio_info in enumerate(item["audios"], 1):
        await send_audio(update, context, item, audio_info, i, reply_markup)
    
    return SEARCH_ITEM

async def process_item_in_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_id = update.message.message_id
    with PROCESSING_LOCK:
        if message_id in PROCESSED_MESSAGES:
            logger.warning(f"پیام تکراری در گروه با message_id: {message_id} - نادیده گرفته شد")
            return
        PROCESSED_MESSAGES.add(message_id)
    
    chat_id = update.effective_chat.id
    try:
        await context.bot.get_chat(chat_id)
    except Exception as e:
        logger.error(f"خطا در دسترسی به چت {chat_id}: {e}")
        if "Forbidden" in str(e):
            await update.message.reply_text(clean_text("متأسفم، من از این گروه بیرون انداخته شدم! 😕 دوباره منو اد کن تا کمکت کنم."), parse_mode="MarkdownV2")
        else:
            await update.message.reply_text(clean_text("یه مشکلی پیش اومد، نمی‌تونم چت رو پیدا کنم! 😅"), parse_mode="MarkdownV2")
        return
    
    thread_id = update.message.message_thread_id if hasattr(update.message, 'is_topic_message') and update.message.is_topic_message else None
    
    if not context.args:
        categories = sorted(set(item["category"] for item in EXTRACTED_ITEMS))
        context.user_data["categories"] = categories
        context.user_data["page"] = 0
        await send_paginated_categories(update, context, is_group=True)
        return
    
    item_name = " ".join(context.args).strip().lower()
    matching_items = [item for item in EXTRACTED_ITEMS if item_name in item["name"].lower()]
    
    if not matching_items:
        await update.message.reply_text(
            clean_text(f"متأسفم، آیتمی با اسم '{item_name}' پیدا نشد! 😕"),
            message_thread_id=thread_id,
            parse_mode="MarkdownV2"
        )
        return
    
    if len(matching_items) == 1:
        item = matching_items[0]
        price_type = "Pips" if item["price"]["type"] == "premium" else item["price"]["type"]
        price_info = clean_text(f"{item['price']['value']} {price_type}")
        results_text = (
            f"*🔖 نام*: {item['name']}\n"
            f"\n"
            f"*🗃 دسته‌بندی*: {item['category']}\n"
            f"*📃 توضیحات*: {item['description']}\n"
            f"\n"
            f"*💸 قیمت*: {price_info}\n"
            f"*📣 @PlatoDex*"
        )
        if item["images"]:
            await update.message.reply_photo(
                photo=item["images"][0],
                caption=results_text,
                reply_to_message_id=update.message.message_id,
                message_thread_id=thread_id,
                parse_mode="MarkdownV2"
            )
        else:
            await update.message.reply_text(
                results_text,
                reply_to_message_id=update.message.message_id,
                message_thread_id=thread_id,
                parse_mode="MarkdownV2"
            )
        for i, audio_info in enumerate(item["audios"], 1):
            await send_audio(update, context, item, audio_info, i, None, thread_id)
    else:
        context.user_data["matching_items"] = matching_items
        context.user_data["page"] = 0
        await send_paginated_items(update, context, is_group=True)

async def send_paginated_categories(update: Update, context: ContextTypes.DEFAULT_TYPE, is_group=False):
    categories = context.user_data.get("categories", sorted(set(item["category"] for item in EXTRACTED_ITEMS)))
    page = context.user_data.get("page", 0)
    items_per_page = 10
    total_pages = (len(categories) + items_per_page - 1) // items_per_page
    
    start_idx = page * items_per_page
    end_idx = min((page + 1) * items_per_page, len(categories))
    current_categories = categories[start_idx:end_idx]
    
    keyboard = []
    for i, category in enumerate(current_categories, start_idx + 1):
        callback_data = f"select_category_{category}"
        keyboard.append([InlineKeyboardButton(clean_text(f"{i}. {category}"), callback_data=callback_data)])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"prev_page_{'group' if is_group else 'private'}_categories"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"next_page_{'group' if is_group else 'private'}_categories"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    if not is_group:
        keyboard.append([InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = clean_text(f"دسته‌بندی‌ها (صفحه {page + 1} از {total_pages})، کدوم رو می‌خوای؟ 👇")
    
    if is_group and update.message:
        thread_id = update.message.message_thread_id if hasattr(update.message, 'is_topic_message') and update.message.is_topic_message else None
        await update.message.reply_text(message_text, reply_markup=reply_markup, message_thread_id=thread_id, parse_mode="MarkdownV2")
    elif update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("select_category_", "")
    matching_items = [item for item in EXTRACTED_ITEMS if item["category"] == category]
    
    if not matching_items:
        await query.edit_message_text(clean_text(f"هیچ آیتمی تو دسته‌بندی '{category}' پیدا نشد! 😕"), parse_mode="MarkdownV2")
        return SELECT_CATEGORY
    
    context.user_data["matching_items"] = matching_items
    context.user_data["page"] = 0
    await send_paginated_items(update, context, is_group="group" in query.data)
    return SEARCH_ITEM

async def select_group_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_id = query.data.replace("select_group_item_", "")
    item = next((i for i in EXTRACTED_ITEMS if i["id"] == item_id), None)
    thread_id = query.message.message_thread_id if hasattr(query.message, 'is_topic_message') and query.message.is_topic_message else None
    
    if not item:
        await query.edit_message_text(clean_text("آیتم پیدا نشد! 😕"), parse_mode="MarkdownV2")
        return
    
    price_type = "Pips" if item["price"]["type"] == "premium" else item["price"]["type"]
    price_info = clean_text(f"{item['price']['value']} {price_type}")
    results_text = (
        f"*🔖 نام*: {item['name']}\n"
        f"\n"
        f"*🗃 دسته‌بندی*: {item['category']}\n"
        f"*📃 توضیحات*: {item['description']}\n"
        f"\n"
        f"*💸 قیمت*: {price_info}\n"
        f"*📣 @PlatoDex*"
    )
    
    if item["images"]:
        image_url = item["images"][0]
        if image_url.lower().endswith('.webp'):
            async def process_webp():
                try:
                    response = requests.get(image_url, timeout=10)
                    response.raise_for_status()
                    img = Image.open(io.BytesIO(response.content))
                    gif_buffer = io.BytesIO()
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    img.save(gif_buffer, format='GIF', save_all=True, optimize=True)
                    gif_buffer.seek(0)
                    input_file = InputFile(gif_buffer, filename="animation.gif")
                    await query.message.reply_animation(
                        animation=input_file,
                        caption=results_text,
                        message_thread_id=thread_id,
                        parse_mode="MarkdownV2"
                    )
                    for i, audio_info in enumerate(item["audios"], 1):
                        await send_audio(update, context, item, audio_info, i, None, thread_id)
                except Exception as e:
                    logger.error(f"خطا در تبدیل WebP: {e}")
                    await query.message.reply_text(clean_text("مشکلی توی ارسال عکس پیش اومد! 😅"), message_thread_id=thread_id, parse_mode="MarkdownV2")
            asyncio.create_task(process_webp())
        elif image_url.lower().endswith('.gif'):
            await query.message.reply_animation(
                animation=image_url,
                caption=results_text,
                message_thread_id=thread_id,
                parse_mode="MarkdownV2"
            )
            for i, audio_info in enumerate(item["audios"], 1):
                await send_audio(update, context, item, audio_info, i, None, thread_id)
        else:
            await query.message.reply_photo(
                photo=image_url,
                caption=results_text,
                message_thread_id=thread_id,
                parse_mode="MarkdownV2"
            )
            for i, audio_info in enumerate(item["audios"], 1):
                await send_audio(update, context, item, audio_info, i, None, thread_id)
    else:
        await query.message.reply_text(results_text, parse_mode="MarkdownV2")
        for i, audio_info in enumerate(item["audios"], 1):
            await send_audio(update, context, item, audio_info, i, None, thread_id)

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    is_group = "group" in query.data
    page = context.user_data.get("page", 0)
    
    if "categories" in query.data:
        if "next_page" in query.data:
            context.user_data["page"] = page + 1
        elif "prev_page" in query.data:
            context.user_data["page"] = max(0, page - 1)
        await send_paginated_categories(update, context, is_group=is_group)
        return SELECT_CATEGORY if not is_group else None
    else:
        if "next_page" in query.data:
            context.user_data["page"] = page + 1
        elif "prev_page" in query.data:
            context.user_data["page"] = max(0, page - 1)
        await send_paginated_items(update, context, is_group=is_group)
        return SEARCH_ITEM if not is_group else None

async def chat_with_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    AI_CHAT_USERS.add(user_id)
    context.user_data.clear()
    context.user_data["mode"] = "ai_chat"
    context.user_data["chat_history"] = []
    keyboard = [[InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        clean_text("🤖 چت با هوش مصنوعی فعال شد!\n\nهر چی می‌خوای بگو، من یادم می‌مونه چی گفتی! 😎"),
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )
    return ConversationHandler.END

async def handle_ai_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in AI_CHAT_USERS or context.user_data.get("mode") != "ai_chat":
        return ConversationHandler.END
    
    user_message = update.message.text
    chat_history = context.user_data.get("chat_history", [])
    chat_history.append({"role": "user", "content": user_message})
    context.user_data["chat_history"] = chat_history
    
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_MESSAGE}
        ] + chat_history,
        "model": "searchgpt",
        "seed": 42,
        "jsonMode": False
    }
    
    keyboard = [[InlineKeyboardButton("🏠 Back to Home", callback_data="back_to_home")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        response = requests.post(TEXT_API_URL, json=payload, timeout=10)
        if response.status_code == 200:
            ai_response = clean_text(response.text.strip())
            chat_history.append({"role": "assistant", "content": ai_response})
            context.user_data["chat_history"] = chat_history
            await update.message.reply_text(ai_response, reply_markup=reply_markup, parse_mode="MarkdownV2")
        else:
            await update.message.reply_text(
                clean_text("اوفف، یه مشکلی پیش اومد! 😅 فکر کنم API یه کم خوابش برده! بعداً امتحان کن 🚀"),
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
    except Exception as e:
        logger.error(f"خطا در اتصال به API چت: {e}")
        await update.message.reply_text(
            clean_text("اییی، یه خطا خوردم! 😭 بعداً دوباره بیا، قول می‌دم درستش کنم! 🚀"),
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    
    return ConversationHandler.END

async def handle_group_ai_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_id = update.message.message_id
    with PROCESSING_LOCK:
        if message_id in PROCESSED_MESSAGES:
            logger.warning(f"پیام تکراری در گروه با message_id: {message_id} - نادیده گرفته شد")
            return
        PROCESSED_MESSAGES.add(message_id)
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    thread_id = update.message.message_thread_id if hasattr(update.message, 'is_topic_message') and update.message.is_topic_message else None
    user_message = update.message.text.lower()
    replied_message = update.message.reply_to_message

    # ثبت تاریخچه گروه
    group_history = context.bot_data.get("group_history", {}).get(chat_id, [])
    group_history.append({"user_id": user_id, "content": user_message, "message_id": message_id})
    context.bot_data["group_history"] = {chat_id: group_history}

    # ثبت تاریخچه کاربر
    user_history = context.user_data.get("group_chat_history", [])
    
    # شرط‌های پاسخگویی
    should_reply = (
        "ربات" in user_message or "پلاتو" in user_message or
        (replied_message and replied_message.from_user.id == context.bot.id)
    )
    
    if not should_reply:
        return
    
    # اگه ریپلای به پیام رباته، متن پیام ریپلای‌شده رو هم اضافه کنیم
    if replied_message and replied_message.from_user.id == context.bot.id:
        user_history.append({"role": "assistant", "content": replied_message.text})
    
    user_history.append({"role": "user", "content": user_message})
    context.user_data["group_chat_history"] = user_history
    
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_MESSAGE}
        ] + user_history,
        "model": "searchgpt",
        "seed": 42,
        "jsonMode": False
    }
    
    try:
        response = requests.post(TEXT_API_URL, json=payload, timeout=10)
        if response.status_code == 200:
            ai_response = clean_text(response.text.strip())  # فرمت کردن پاسخ API
            user_history.append({"role": "assistant", "content": ai_response})
            context.user_data["group_chat_history"] = user_history
            
            # چک کردن سوال در مورد آیتم‌ها
            final_response = ai_response
            for item in EXTRACTED_ITEMS:
                if item["name"].lower() in user_message:
                    price_type = "Pips" if item["price"]["type"] == "premium" else item["price"]["type"]
                    price_info = clean_text(f"{item['price']['value']} {price_type}")
                    item_info = clean_text(
                        f"مشخصات آیتم پیدا شد! 🎉\n"
                        f"*🔖 نام*: {item['name']}\n"
                        f"*💸 قیمت*: {price_info}\n"
                        f"اگه می‌خوای مشخصات کامل‌تر با صدا رو ببینی، کافیه بگی: `/i {item['name']}` 😎"
                    )
                    final_response += f"\n\n{item_info}"
                    break
            
            await update.message.reply_text(
                final_response,
                reply_to_message_id=update.message.message_id,
                message_thread_id=thread_id,
                parse_mode="MarkdownV2"
            )
        else:
            error_message = clean_text("اوفف، یه مشکلی پیش اومد! 😅 بعداً امتحان کن 🚀")
            await update.message.reply_text(
                error_message,
                reply_to_message_id=update.message.message_id,
                message_thread_id=thread_id,
                parse_mode="MarkdownV2"
            )
    except Exception as e:
        logger.error(f"خطا در اتصال به API چت گروه: {e}")
        error_message = clean_text("اییی، یه خطا خوردم! 😭 بعداً دوباره بیا 🚀")
        await update.message.reply_text(
            error_message,
            reply_to_message_id=update.message.message_id,
            message_thread_id=thread_id,
            parse_mode="MarkdownV2"
        )

async def back_to_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id in AI_CHAT_USERS:
        AI_CHAT_USERS.remove(user_id)
    context.user_data.clear()
    user_name = query.from_user.first_name
    welcome_message = clean_text(
        f"سلام {user_name}!\nبه PlatoDex خوش اومدی - مرکز بازی‌های Plato!\n"
        "• آیتم‌ها رو ببین 🎲\n• رتبه‌بندی بازیکن‌ها رو چک کن 🏆\n• اخبار رو دنبال کن 🎯"
    )
    keyboard = [
        [InlineKeyboardButton("Run App 📱", web_app={"url": "https://platodex-tde3qe.vercel.app/"})],
        [InlineKeyboardButton("Search Items 🔍", callback_data="search_items")],
        [InlineKeyboardButton("Chat with AI 🤖", callback_data="chat_with_ai")],
        [InlineKeyboardButton("Generate Image 🖼️", callback_data="generate_image")]
    ]
    await query.edit_message_text(
        text=welcome_message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="MarkdownV2"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user_id = update.effective_user.id
    if user_id in AI_CHAT_USERS:
        AI_CHAT_USERS.remove(user_id)
    await update.message.reply_text(clean_text("عملیات لغو شد."), reply_markup=InlineKeyboardMarkup([]), parse_mode="MarkdownV2")
    await start(update, context)
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"خطا رخ داد: {context.error}")
    if str(context.error) == "Query is too old and response timeout expired or query id is invalid":
        if update and update.callback_query:
            await update.callback_query.message.reply_text(clean_text("اوپس، یه کم دیر شد! دوباره امتحان کن 😅"), parse_mode="MarkdownV2")

async def main():
    global application
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            application = Application.builder().token(TOKEN).read_timeout(60).write_timeout(60).connect_timeout(60).build()
            
            if application.job_queue is None:
                logger.error("JobQueue فعال نیست!")
                raise RuntimeError("JobQueue فعال نیست!")
            
            await application.bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook روی {WEBHOOK_URL} تنظیم شد.")
            
            schedule_scraping(application)
            await extract_items()
            
            search_conv_handler = ConversationHandler(
                entry_points=[CallbackQueryHandler(start_item_search, pattern="^search_items$")],
                states={
                    SELECT_CATEGORY: [
                        CallbackQueryHandler(search_by_name, pattern="^search_by_name$"),
                        CallbackQueryHandler(select_category, pattern="^select_category_"),
                        CallbackQueryHandler(handle_pagination, pattern="^(prev|next)_page_private_categories$")
                    ],
                    SEARCH_ITEM: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, process_item_search),
                        CallbackQueryHandler(select_item, pattern="^select_item_"),
                        CallbackQueryHandler(handle_pagination, pattern="^(prev|next)_page_private$")
                    ]
                },
                fallbacks=[
                    CommandHandler("cancel", cancel),
                    CommandHandler("start", start),
                    CallbackQueryHandler(back_to_home, pattern="^back_to_home$")
                ],
                name="item_search",
                persistent=False
            )
            
            image_conv_handler = ConversationHandler(
                entry_points=[
                    CallbackQueryHandler(start_generate_image, pattern="^generate_image$"),
                    CallbackQueryHandler(retry_generate_image, pattern="^retry_generate_image$")
                ],
                states={
                    SELECT_SIZE: [CallbackQueryHandler(select_size, pattern="^size_")],
                    GET_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_prompt)]
                },
                fallbacks=[
                    CommandHandler("cancel", cancel),
                    CommandHandler("start", start),
                    CallbackQueryHandler(back_to_home, pattern="^back_to_home$")
                ],
                name="image_generation",
                persistent=False
            )
            
            application.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
            application.add_handler(CommandHandler("i", process_item_in_group, filters=filters.ChatType.GROUPS))
            application.add_handler(CallbackQueryHandler(select_group_item, pattern="^select_group_item_"))
            application.add_handler(CallbackQueryHandler(select_category, pattern="^select_category_"))
            application.add_handler(CallbackQueryHandler(handle_pagination, pattern="^(prev|next)_page_group"))
            application.add_handler(CallbackQueryHandler(handle_pagination, pattern="^(prev|next)_page_group_categories"))
            application.add_handler(search_conv_handler)
            application.add_handler(image_conv_handler)
            application.add_handler(CallbackQueryHandler(chat_with_ai, pattern="^chat_with_ai$"))
            application.add_handler(CallbackQueryHandler(back_to_home, pattern="^back_to_home$"))
            application.add_handler(InlineQueryHandler(inline_query))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_ai_message))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, handle_group_ai_message))
            application.add_handler(MessageHandler(filters.Regex(r"🔖 نام"), handle_inline_selection))
            application.add_error_handler(error_handler)
            
            logger.info("در حال آماده‌سازی ربات...")
            await application.initialize()
            logger.info("در حال شروع ربات...")
            await application.start()
            
            config = uvicorn.Config(app, host="0.0.0.0", port=8000)
            server = uvicorn.Server(config)
            await server.serve()
            
        except Exception as e:
            logger.error(f"خطا در تلاش {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                logger.info(f"تلاش دوباره بعد از {retry_delay} ثانیه...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("همه تلاش‌ها برای شروع ربات ناموفق بود!")
                raise

if __name__ == "__main__":
    asyncio.run(main())
