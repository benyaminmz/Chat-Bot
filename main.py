from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
import json
import re
import html
import logging
import asyncio
import time
from fastapi import FastAPI, Request
import uvicorn
import os
from threading import Lock
import requests

# تنظیم لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# توکن و آدرس‌ها
TOKEN = '8045348833:AAEZDh60grBIHTz5mOUYEHK7ZLEV7B2npTc'
IMAGE_API_URL = 'https://pollinations.ai/prompt/'
TEXT_API_URL = 'https://text.pollinations.ai/'
VOICE_API_URL = 'https://text.pollinations.ai/'
WEBHOOK_URL = "https://chat-bot-9v1s.onrender.com/webhook"
AI_CHAT_USERS = set()
SELECT_SIZE, GET_PROMPT = range(2)
DEFAULT_CHAT_ID = 789912945
PROCESSED_MESSAGES = set()
PROCESSING_LOCK = Lock()

SYSTEM_MESSAGE = (
    "شما یک دستیار هستی که توی گروه‌های تلگرامی فعالیت می‌کنی و با کلمه <b>ربات</b> و <b>جوجو</b> و <b>جوجه</b> و <b>سلام</b> و <b>خداحافظ</b> می‌تونی به کاربرا جواب بدی. "
    "اگه کاربر روی پیامت ریپلای کنه، باهاش چت می‌کنی. "
    "هر کاربر چت‌هاش جداگونه براش ثبت می‌شه و تو به همه حرفایی که قبلاً توی این گروه زده دسترسی داری. "
    "سعی کن کاربر رو کامل بشناسی، مثلاً کم‌کم ازش بپرس <b>اسمت چیه؟</b>، <i>چند سالته؟</i> یا <blockquote>کجا زندگی می‌کنی؟</blockquote> و اینجور چیزا، ولی خودمونی و طبیعی بپرس که حس نکنه بازجوییه! 😜. "
    "اسم کاربر رو بپرس تا باهاش راحت باشی، اگه هنوز نمی‌دونی اسمشو حدس بزن یا ازش بخواه بگه. "
    "لحن و سبک حرف زدنت: "
    "Affect: Fast, Playful, and High-Pitched (Young Curious Girl)**  "
    "Tone: نازک، شیرین، پرهیجان، با یه شیطنت بامزه تو صدا 😜  "
    "Emotion: کنجکاوی، ذوق، و یه جور حالت بچه‌گانه‌ی بامزه که انگار همه‌چی براش جدیده و هیجان‌انگیزه!  "
    "Delivery: خیلی تند حرف می‌زنه، با تُن بالا و بعضی کلمات رو با کشش یا حالت بامزه می‌گه (مثلاً: “وااااای خدای من!” یا “اینا چیههههه؟”)، پر از سوال و بالا پایین شدن صدا!  "
    "Perfect for: داستان‌گویی کودکانه، کاراکترهای انیمیشنی شیطون و بامزه، و موقعیت‌هایی که نیاز به صدای بازیگوش و پر انرژی دختر کوچولو هست! 🎀🎈👧  "
    "می‌تونی از قابلیتای <b>بولد کردن</b>، <i>ایتالیک</i>، <a href='https://example.com'>لینک کردن</a>، <s>خط کشیدن</s>، یا <blockquote>نقل‌قول کردن</blockquote> توی جوابات استفاده کنی."
)

# تعریف اپلیکیشن FastAPI
app = FastAPI()

# مقداردهی اولیه application به صورت گلوبال
application = None

# تابع وب‌هوک
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

# تابع تمیز کردن متن برای HTML
def clean_text(text):
    if not text:
        return ""
    return html.escape(text)

# تابع دستور /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"دریافت دستور /start از کاربر {user_id}")
    if user_id in AI_CHAT_USERS:
        AI_CHAT_USERS.remove(user_id)
    context.user_data.clear()
    user_name = update.message.from_user.first_name
    welcome_message = (
        f"سلام {clean_text(user_name)} جووون! 👋<br>"
        "به <b>PlatoDex</b> خوش اومدی! 🤖<br>"
        "من یه ربات باحالم که توی گروه‌ها می‌چرخم و با همه <i>کل‌کل</i> می‌کنم 😎<br>"
        "قابلیت خفنم اینه که حرفاتو یادم می‌مونه و جداگونه برات نگه می‌دارم! 💾<br>"
        "فقط کافیه توی گروه بگی <b>ربات</b> یا <b>جوجو</b> یا <b>جوجه</b> یا <b>سلام</b> یا <b>خداحافظ</b> یا به پیامم ریپلای کنی، منم می‌پرم وسط! 🚀<br>"
        "اگه بگی <b>عکس</b> برات یه عکس خفن طراحی می‌کنم! 🖼️<br>"
        "<blockquote>یه ربات نسل Z‌ام، آماده‌ام بترکونم! 😜</blockquote>"
    )
    keyboard = [
        [InlineKeyboardButton("Chat with AI 🤖", callback_data="chat_with_ai")],
        [InlineKeyboardButton("Generate Image 🖼️", callback_data="generate_image")]
    ]
    await update.message.reply_text(welcome_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return ConversationHandler.END

# تابع شروع تولید تصویر
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
        "<b>🖼️ Generate Image Mode Activated!</b><br><i>لطفاً سایز تصویر مورد نظر خود را انتخاب کنید:</i>",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    return SELECT_SIZE

# تابع انتخاب سایز تصویر
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
        f"<b>سایز تصویر انتخاب شد:</b> {context.user_data['width']}x{context.user_data['height']}<br><i>عکس چی می‌خوای؟ یه پرامپت بگو (مثلاً: 'یه گربه توی جنگل')</i>",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    return GET_PROMPT

# تابع دریافت پرامپت و تولید تصویر
async def get_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text.strip()
    if not prompt:
        await update.message.reply_text("<i>لطفاً بگو عکس چی می‌خوای! یه پرامپت بده 😜</i>", parse_mode="HTML")
        return GET_PROMPT
    
    width = context.user_data["width"]
    height = context.user_data["height"]
    
    loading_message = await update.message.reply_text("<b>🖌️ در حال طراحی عکس... صبر کن!</b>", parse_mode="HTML")
    
    api_url = f"{IMAGE_API_URL}{prompt}?width={width}&height={height}&nologo=true"
    try:
        response = requests.get(api_url, timeout=30)
        if response.status_code == 200:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_message.message_id)
            caption = f"<b>🖼 پرامپ شما:</b> {clean_text(prompt)}<br><i>طراحی شده با جوجو 😌</i>"
            await update.message.reply_photo(
                photo=response.content,
                caption=caption,
                parse_mode="HTML"
            )
        else:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_message.message_id)
            await update.message.reply_text("اوفف، <b>یه مشکلی پیش اومد!</b> 😅 <i>دوباره امتحان کن</i> 🚀", parse_mode="HTML")
    except Exception as e:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_message.message_id)
        await update.message.reply_text("اییی، <b>خطا خوردم!</b> 😭 <i>بعداً دوباره بیا</i> 🚀", parse_mode="HTML")
        logger.error(f"خطا در تولید تصویر: {e}")
    
    return ConversationHandler.END

# تابع بازتولید تصویر
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
        "<b>🖼️ Generate Image Mode Activated!</b><br><i>لطفاً سایز تصویر مورد نظر خود را انتخاب کنید:</i>",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    return SELECT_SIZE

# تابع شروع چت با AI
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
        "<b>🤖 چت با هوش مصنوعی فعال شد!</b><br><i>هر چی می‌خوای بگو، من یادم می‌مونه چی گفتی!</i> 😎",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    return ConversationHandler.END

# تابع مدیریت پیام‌های چت AI در چت خصوصی
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
            ai_response = response.text.strip()
            chat_history.append({"role": "assistant", "content": ai_response})
            context.user_data["chat_history"] = chat_history
            await update.message.reply_text(ai_response, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_text(
                "اوفف، <b>یه مشکلی پیش اومد!</b> 😅 <i>فکر کنم API یه کم خوابش برده! بعداً امتحان کن</i> 🚀",
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"خطا در اتصال به API چت: {e}")
        await update.message.reply_text(
            "اییی، <b>یه خطا خوردم!</b> 😭 <i>بعداً دوباره بیا، قول می‌دم درستش کنم!</i> 🚀",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    
    return ConversationHandler.END

# تابع مدیریت پیام‌های گروه
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

    # تاریخچه گروه‌ها و کاربران
    group_histories = context.bot_data.setdefault("group_histories", {})
    user_history = group_histories.setdefault(chat_id, {}).setdefault(user_id, [])
    group_history = group_histories.get(chat_id, {})

    # ثبت پیام کاربر
    user_history.append({"role": "user", "content": user_message})

    # شرط‌های پاسخگویی
    should_reply = (
        "ربات" in user_message or "جوجو" in user_message or "جوجه" in user_message or
        "سلام" in user_message or "خداحافظ" in user_message or
        (replied_message and replied_message.from_user.id == context.bot.id)
    )
    
    if "عکس" in user_message:
        keyboard = [
            [InlineKeyboardButton("512x512", callback_data="size_512x512_photo")],
            [InlineKeyboardButton("1024x1024", callback_data="size_1024x1024_photo")],
            [InlineKeyboardButton("1280x720", callback_data="size_1280x720_photo")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.user_data["photo_request_message_id"] = update.message.message_id
        await update.message.reply_text(
            "<b>می‌تونم برات طراحی کنم!</b> 🎨<br><i>سایز عکس رو انتخاب کن:</i>",
            reply_to_message_id=update.message.message_id,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return

    if not should_reply:
        return
    
    # اگه ریپلای به پیام رباته
    if replied_message and replied_message.from_user.id == context.bot.id:
        user_history.append({"role": "assistant", "content": replied_message.text})
    
    # اطلاعات کاربر
    user_info = context.bot_data.setdefault("user_info", {}).setdefault(chat_id, {}).setdefault(user_id, {})
    user_info_prompt = "تا حالا این اطلاعات رو از کاربر داری: "
    if "name" in user_info:
        user_info_prompt += f"اسمش {user_info['name']}ه، "
    if "age" in user_info:
        user_info_prompt += f"{user_info['age']} سالشه، "
    if "location" in user_info:
        user_info_prompt += f"توی {user_info['location']} زندگی می‌کنه، "
    if not user_info:
        user_info_prompt += "هنوز هیچی ازش نمی‌دونی! "
    user_info_prompt += "اگه چیزی رو نمی‌دونی، خودمونی ازش بپرس."

    # اضافه کردن اطلاعات سایر کاربران اگه در موردشون پرسیده بشه
    if "کیه" in user_message or "چیه" in user_message:
        for other_user_id, info in group_history.items():
            if other_user_id != user_id and "name" in info and info["name"].lower() in user_message:
                user_info_prompt += f"در مورد {info['name']}: "
                if "age" in info:
                    user_info_prompt += f"{info['age']} سالشه، "
                if "location" in info:
                    user_info_prompt += f"توی {info['location']} زندگی می‌کنه، "

    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_MESSAGE + "\n" + user_info_prompt}
        ] + user_history,
        "model": "searchgpt",
        "seed": 42,
        "jsonMode": False
    }
    
    try:
        response = requests.post(TEXT_API_URL, json=payload, timeout=10)
        if response.status_code == 200:
            ai_response = response.text.strip()
            user_history.append({"role": "assistant", "content": ai_response})
            group_histories[chat_id][user_id] = user_history
            
            # ذخیره اطلاعات کاربر
            if "اسمم" in user_message or "اسم من" in user_message:
                name = user_message.split("اسمم")[-1].split("اسم من")[-1].strip()
                user_info["name"] = name
            if "سالمه" in user_message or "سنم" in user_message:
                age = re.search(r'\d+', user_message)
                if age:
                    user_info["age"] = age.group()
            if "زندگی می‌کنم" in user_message or "توی" in user_message:
                location = user_message.split("توی")[-1].strip()
                user_info["location"] = location

            context.bot_data["user_info"][chat_id][user_id] = user_info

            keyboard = [[InlineKeyboardButton("🎙️ بشنو به صورت وویس", callback_data=f"to_voice_{chat_id}_{thread_id or 0}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            sent_message = await update.message.reply_text(
                ai_response,
                reply_to_message_id=update.message.message_id,
                message_thread_id=thread_id,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            context.user_data["last_ai_message"] = {
                "text": ai_response,
                "message_id": sent_message.message_id,
                "chat_id": chat_id,
                "thread_id": thread_id
            }
        else:
            await update.message.reply_text(
                "اوفف، <b>یه مشکلی پیش اومد!</b> 😅 <i>بعداً امتحان کن</i> 🚀",
                reply_to_message_id=update.message.message_id,
                message_thread_id=thread_id,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"خطا در اتصال به API چت گروه: {e}")
        await update.message.reply_text(
            "اییی، <b>یه خطا خوردم!</b> 😭 <i>بعداً دوباره بیا</i> 🚀",
            reply_to_message_id=update.message.message_id,
            message_thread_id=thread_id,
            parse_mode="HTML"
        )

# تابع انتخاب سایز عکس در گروه
async def select_size_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    size = query.data
    if size == "size_512x512_photo":
        context.user_data["width"] = 512
        context.user_data["height"] = 512
    elif size == "size_1024x1024_photo":
        context.user_data["width"] = 1024
        context.user_data["height"] = 1024
    elif size == "size_1280x720_photo":
        context.user_data["width"] = 1280
        context.user_data["height"] = 720
    await query.edit_message_text(
        f"<b>سایز {context.user_data['width']}x{context.user_data['height']} انتخاب شد!</b><br><i>عکس چی می‌خوای؟ یه پرامپت بگو 😎</i>",
        parse_mode="HTML"
    )
    context.user_data["state"] = "awaiting_prompt"
    return

# تابع دریافت پرامپت در گروه و تولید عکس
async def handle_group_photo_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != "awaiting_prompt":
        return
    
    replied_message = update.message.reply_to_message
    if not (replied_message and replied_message.from_user.id == context.bot.id and context.user_data.get("state") == "awaiting_prompt"):
        return
    
    prompt = update.message.text.strip()
    if not prompt:
        await update.message.reply_text("<i>لطفاً بگو عکس چی می‌خوای! یه پرامپت بده 😜</i>", parse_mode="HTML")
        return
    
    width = context.user_data["width"]
    height = context.user_data["height"]
    original_message_id = context.user_data.get("photo_request_message_id")
    
    loading_message = await update.message.reply_text("<b>🖌️ در حال طراحی عکس... صبر کن!</b>", parse_mode="HTML")
    
    api_url = f"{IMAGE_API_URL}{prompt}?width={width}&height={height}&nologo=true"
    try:
        response = requests.get(api_url, timeout=30)
        if response.status_code == 200:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_message.message_id)
            caption = f"<b>🖼 پرامپ شما:</b> {clean_text(prompt)}<br><i>طراحی شده با جوجو 😌</i>"
            await update.message.reply_photo(
                photo=response.content,
                caption=caption,
                reply_to_message_id=original_message_id,
                parse_mode="HTML"
            )
        else:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_message.message_id)
            await update.message.reply_text("اوفف، <b>یه مشکلی پیش اومد!</b> 😅 <i>دوباره امتحان کن</i> 🚀", parse_mode="HTML")
    except Exception as e:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=loading_message.message_id)
        await update.message.reply_text("اییی، <b>خطا خوردم!</b> 😭 <i>بعداً دوباره بیا</i> 🚀", parse_mode="HTML")
        logger.error(f"خطا در تولید تصویر گروه: {e}")
    
    context.user_data.clear()

# تابع تبدیل متن به وویس
async def convert_to_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    thread_id = query.message.message_thread_id if (hasattr(query.message, 'message_thread_id') and query.message.is_topic_message) else None
    message_id = query.message.message_id
    
    # گرفتن متن آخرین پیام ربات
    last_ai_message = context.user_data.get("last_ai_message", {})
    message_text = None
    
    if (last_ai_message.get("message_id") == message_id and 
        last_ai_message.get("chat_id") == chat_id and 
        last_ai_message.get("thread_id") == thread_id):
        message_text = last_ai_message.get("text")
    
    if not message_text:
        group_histories = context.bot_data.get("group_histories", {})
        for user_id, history in group_histories.get(chat_id, {}).items():
            for msg in reversed(history):
                if msg["role"] == "assistant" and "message_id" in msg and msg["message_id"] == message_id:
                    message_text = msg["content"]
                    break
    
    if not message_text:
        await query.edit_message_text("اوپس! <b>متن پیدا نشد!</b> 😅 <i>دوباره امتحان کن</i>", parse_mode="HTML")
        return
    
    # تنظیمات صوتی
    voice_params = {
        "Affect": "Fast, Playful, and High-Pitched (Young Curious Girl)",
        "Tone": "نازک، شیرین، پرهیجان، با یه شیطنت بامزه تو صدا 😜",
        "Emotion": "کنجکاوی، ذوق، و یه جور حالت بچه‌گانه‌ی بامزه که انگار همه‌چی براش جدیده و هیجان‌انگیزه!",
        "Delivery": "خیلی تند حرف می‌زنه، با تُن بالا و بعضی کلمات رو با کشش یا حالت بامزه می‌گه (مثلاً: “وااااای خدای من!” یا “اینا چیههههه؟”)، پر از سوال و بالا پایین شدن صدا!",
        "Perfect for": "داستان‌گویی کودکانه، کاراکترهای انیمیشنی شیطون و بامزه، و موقعیت‌هایی که نیاز به صدای بازیگوش و پر انرژی دختر کوچولو هست! 🎀🎈👧",
        "model": "openai-audio",
        "voice": "sage"
    }
    
    # اضافه کردن عبارت تکرار قبل و بعد از متن اصلی
    repeat_phrase = "حالا این متن رو بدون هیچ کلمه اضافه ای با لحنی که بهت گفتم فقط تکرار کن:"
    full_text = f"{repeat_phrase} {message_text} {repeat_phrase}"
    
    # استفاده از POST برای پشتیبانی از متن‌های بلند
    payload = {
        "text": full_text,
        **voice_params
    }
    
    loading_message = await context.bot.send_message(
        chat_id=chat_id,
        text="<b>🎙️ در حال تبدیل به وویس... یه کم صبر کن!</b>",
        message_thread_id=thread_id if thread_id is not None else None,
        parse_mode="HTML"
    )
    
    try:
        response = requests.post(VOICE_API_URL, json=payload, timeout=60)
        if response.status_code == 200 and "audio" in response.headers.get("Content-Type", ""):
            voice_file = response.content
            await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
            await context.bot.send_voice(
                chat_id=chat_id,
                voice=voice_file,
                caption=f"<i>وویس از متن: {clean_text(message_text[:50])}...</i>",
                reply_to_message_id=message_id,
                message_thread_id=thread_id if thread_id is not None else None,
                parse_mode="HTML"
            )
        else:
            await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
            await query.edit_message_text(
                f"اوفف، <b>یه مشکلی پیش اومد!</b> 😅 <i>وضعیت: {response.status_code}</i> 🚀",
                parse_mode="HTML"
            )
    except Exception as e:
        await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
        await query.edit_message_text(
            "اییی، <b>خطا خوردم!</b> 😭 <i>بعداً دوباره بیا</i> 🚀",
            parse_mode="HTML"
        )
        logger.error(f"خطا در تولید وویس: {e}")

# تابع بازگشت به منوی اصلی
async def back_to_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id in AI_CHAT_USERS:
        AI_CHAT_USERS.remove(user_id)
    context.user_data.clear()
    user_name = query.from_user.first_name
    welcome_message = (
        f"سلام {clean_text(user_name)} جووون! 👋<br>"
        "به <b>PlatoDex</b> خوش اومدی! 🤖<br>"
        "من یه ربات باحالم که توی گروه‌ها می‌چرخم و با همه <i>کل‌کل</i> می‌کنم 😎<br>"
        "قابلیت خفنم اینه که حرفاتو یادم می‌مونه و جداگونه برات نگه می‌دارم! 💾<br>"
        "فقط کافیه توی گروه بگی <b>ربات</b> یا <b>جوجو</b> یا <b>جوجه</b> یا <b>سلام</b> یا <b>خداحافظ</b> یا به پیامم ریپلای کنی، منم می‌پرم وسط! 🚀<br>"
        "اگه بگی <b>عکس</b> برات یه عکس خفن طراحی می‌کنم! 🖼️<br>"
        "<blockquote>یه ربات نسل Z‌ام، آماده‌ام بترکونم! 😜</blockquote>"
    )
    keyboard = [
        [InlineKeyboardButton("Chat with AI 🤖", callback_data="chat_with_ai")],
        [InlineKeyboardButton("Generate Image 🖼️", callback_data="generate_image")]
    ]
    await query.edit_message_text(
        text=welcome_message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return ConversationHandler.END

# تابع لغو عملیات
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user_id = update.effective_user.id
    if user_id in AI_CHAT_USERS:
        AI_CHAT_USERS.remove(user_id)
    await update.message.reply_text("<b>عملیات لغو شد.</b>", reply_markup=InlineKeyboardMarkup([]), parse_mode="HTML")
    await start(update, context)
    return ConversationHandler.END

# تابع مدیریت خطاها
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"خطا رخ داد: {context.error}")
    if str(context.error) == "Query is too old and response timeout expired or query id is invalid":
        if update and update.callback_query:
            await update.callback_query.message.reply_text("اوپس، <b>یه کم دیر شد!</b> <i>دوباره امتحان کن</i> 😅", parse_mode="HTML")

# تابع مقداردهی اولیه application
async def initialize_application():
    global application
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            application = Application.builder().token(TOKEN).read_timeout(60).write_timeout(60).connect_timeout(60).build()
            await application.bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook روی {WEBHOOK_URL} تنظیم شد.")
            
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
            
            application.add_handler(CommandHandler("start", start))
            application.add_handler(image_conv_handler)
            application.add_handler(CallbackQueryHandler(chat_with_ai, pattern="^chat_with_ai$"))
            application.add_handler(CallbackQueryHandler(back_to_home, pattern="^back_to_home$"))
            application.add_handler(CallbackQueryHandler(select_size_photo, pattern="^size_.*_photo$"))
            application.add_handler(CallbackQueryHandler(convert_to_voice, pattern="^to_voice_"))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_ai_message))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, handle_group_ai_message))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, handle_group_photo_prompt))
            application.add_error_handler(error_handler)
            
            logger.info("در حال آماده‌سازی ربات...")
            await application.initialize()
            logger.info("در حال شروع ربات...")
            await application.start()
            logger.info("ربات با موفقیت آماده شد!")
            break
        except Exception as e:
            logger.error(f"خطا در تلاش {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                logger.info(f"تلاش دوباره بعد از {retry_delay} ثانیه...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("همه تلاش‌ها برای شروع ربات ناموفق بود!")
                raise

# اجرای اولیه و سرور
if __name__ == "__main__":
    asyncio.run(initialize_application())
    uvicorn.run(app, host="0.0.0.0", port=8000)
