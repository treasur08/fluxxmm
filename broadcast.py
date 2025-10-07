from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from utils import load_users
from config import ADMIN_ID
import asyncio
from telegram.error import BadRequest

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate broadcast command for admin in DM."""
    if str(update.effective_user.id) != str(ADMIN_ID):
        return
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use /broadcast in the bot's DM.")
        return

    keyboard = [
        [InlineKeyboardButton("Text Only", callback_data="broadcast_text")],
        [InlineKeyboardButton("Image + Text", callback_data="broadcast_image")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📢 <b>Choose Broadcast Type</b>\n\nSelect the type of broadcast message:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    context.user_data['broadcast_state'] = 'awaiting_type'

async def handle_broadcast_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast type selection and prompt for content."""
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_ID):
        await query.answer("Only admin can perform this action.", show_alert=True)
        return

    broadcast_type = query.data.split('_')[1]  # 'text' or 'image'
    context.user_data['broadcast_type'] = broadcast_type

    if broadcast_type == 'text':
        msg = await query.message.reply_text(
            "📝 Please reply to this message with the broadcast text.",
            parse_mode='HTML'
        )
    else:  # image
        msg = await query.message.reply_text(
            "🖼️ Please reply to this message with an image and caption.",
            parse_mode='HTML'
        )
    
    context.user_data['broadcast_prompt_id'] = msg.message_id
    context.user_data['broadcast_state'] = 'awaiting_content'
    await query.message.delete()

async def handle_broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast content reply and show confirmation."""
    if str(update.effective_user.id) != str(ADMIN_ID):
        return
    if context.user_data.get('broadcast_state') != 'awaiting_content':
        return
    if not update.message.reply_to_message or update.message.reply_to_message.message_id != context.user_data.get('broadcast_prompt_id'):
        return

    broadcast_type = context.user_data.get('broadcast_type')
    content = {}

    try:
        if broadcast_type == 'text':
            if not update.message.text:
                await update.message.reply_text("❌ Please provide text for the broadcast.")
                return
            content['text'] = update.message.text_html
            print(f"[DEBUG] Broadcast text content: {content['text']}")
        else:  # image
            if not update.message.photo or not update.message.caption:
                await update.message.reply_text("❌ Please provide an image with a caption.")
                return
            content['photo'] = update.message.photo[-1].file_id  # Highest resolution
            content['caption'] = update.message.caption_html
            print(f"[DEBUG] Broadcast photo ID: {content['photo']}, caption: {content['caption']}")
    except BadRequest as e:
        print(f"[DEBUG] HTML parsing error: {e}")
        await update.message.reply_text(
            f"❌ Invalid HTML formatting: {e}\nPlease use valid HTML tags (e.g., <b>bold</b>, <i>italic</i>)."
        )
        return

    context.user_data['broadcast_content'] = content
    keyboard = [
        [InlineKeyboardButton("✅ Yes", callback_data="broadcast_confirm"),
         InlineKeyboardButton("❌ No", callback_data="broadcast_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if broadcast_type == 'text':
            await update.message.reply_text(
                f"📢 <b>Broadcast Preview</b>\n\n{content['text']}\n\nAre you sure you want to send this to all users?",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_photo(
                photo=content['photo'],
                caption=f"📢 <b>Broadcast Preview</b>\n\n{content['caption']}\n\nAre you sure you want to send this to all users?",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    except BadRequest as e:
        print(f"[DEBUG] Preview HTML error: {e}")
        await update.message.reply_text(
            f"❌ Error in preview due to invalid HTML: {e}\nPlease check your formatting and try again."
        )
        return

    context.user_data['broadcast_state'] = 'awaiting_confirmation'
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=context.user_data['broadcast_prompt_id']
        )
    except:
        pass

async def handle_broadcast_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast confirmation and send to all users."""
    query = update.callback_query
    if str(query.from_user.id) != str(ADMIN_ID):
        await query.answer("Only admin can perform this action.", show_alert=True)
        return

    if query.data == "broadcast_cancel":
        await query.message.delete()
        await query.message.reply_text("❌ Broadcast cancelled.")
        context.user_data.clear()
        return

    if query.data != "broadcast_confirm":
        return

    users = load_users()
    user_ids = list(users.keys())
    total_users = len(user_ids)
    sent_count = 0
    failed_count = 0

    content = context.user_data.get('broadcast_content', {})
    broadcast_type = context.user_data.get('broadcast_type')

    # Send progress message
    progress_msg = await query.message.reply_text(
        f"📢 Sending broadcast to {total_users} users...\nProgress: 0/{total_users}",
        parse_mode='HTML'
    )

    for user_id in user_ids:
        try:
            if broadcast_type == 'text':
                await context.bot.send_message(
                    chat_id=user_id,
                    text=content['text'],
                    parse_mode='HTML'
                )
            else:  # image
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=content['photo'],
                    caption=content['caption'],
                    parse_mode='HTML'
                )
            sent_count += 1
            print(f"[DEBUG] Broadcast sent to user {user_id}")
            # Update progress every 10 users or at the end
            if sent_count % 10 == 0 or sent_count == total_users:
                await progress_msg.edit_text(
                    f"📢 Sending broadcast to {total_users} users...\nProgress: {sent_count}/{total_users}",
                    parse_mode='HTML'
                )
            # Avoid flooding
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[DEBUG] Failed to send broadcast to user {user_id}: {e}")
            failed_count += 1
            continue

    await query.message.delete()
    await progress_msg.edit_text(
        f"📢 Broadcast completed!\n\nSent to: {sent_count}/{total_users} users\nFailed: {failed_count}",
        parse_mode='HTML'
    )
    context.user_data.clear()
