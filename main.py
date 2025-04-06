async def convert_to_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    # فقط اگه پیام توی تاپیک باشه و گروه تاپیک‌ها رو ساپورت کنه، thread_id رو بفرست
    thread_id = query.message.message_thread_id if (hasattr(query.message, 'message_thread_id') and query.message.is_topic_message) else None
    message_id = query.message.message_id  # message_id پیام ربات که دکمه روش زده شده
    
    # گرفتن متن آخرین پیام ربات
    last_ai_message = context.user_data.get("last_ai_message", {})
    message_text = None
    
    if (last_ai_message.get("message_id") == message_id and 
        last_ai_message.get("chat_id") == chat_id and 
        last_ai_message.get("thread_id") == thread_id):
        message_text = last_ai_message.get("text")
    
    if not message_text:
        group_history = context.bot_data.get("group_history", {}).get(chat_id, [])
        for msg in reversed(group_history):
            if msg["message_id"] == message_id and msg["user_id"] == context.bot.id:
                message_text = msg["content"]
                break
    
    if not message_text:
        await query.edit_message_text("اوپس! <b>متن پیدا نشد!</b> 😅 <i>دوباره امتحان کن</i>", parse_mode="HTML")
        return
    
    # تنظیمات صوتی بر اساس داکیومنت Pollinations
    encoded_text = requests.utils.quote(message_text)  # URL-encode کردن متن
    voice_params = {
        "model": "openai-audio",
        "voice": "sage"  # صدای مورد نظرت
    }
    url = f"{VOICE_API_URL}{encoded_text}?{('&'.join(f'{k}={v}' for k, v in voice_params.items()))}"
    
    loading_message = await context.bot.send_message(
        chat_id=chat_id,
        text="<b>🎙️ در حال تبدیل به وویس... یه کم صبر کن!</b>",
        message_thread_id=thread_id if thread_id is not None else None,  # فقط اگه thread_id معتبر باشه
        parse_mode="HTML"
    )
    
    try:
        response = requests.get(url, timeout=15)  # درخواست GET به API
        if response.status_code == 200 and "audio" in response.headers.get("Content-Type", ""):
            voice_file = response.content  # گرفتن فایل صوتی
            await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
            await context.bot.send_voice(
                chat_id=chat_id,
                voice=voice_file,  # ارسال به صورت وویس
                caption=f"<i>وویس از متن: {clean_text(message_text[:50])}...</i>",
                reply_to_message_id=message_id,
                message_thread_id=thread_id if thread_id is not None else None,  # فقط اگه thread_id معتبر باشه
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
