from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import json
import os
import asyncio
from telethon import TelegramClient
from telethon import functions, types
from telethon.tl.functions.messages import CreateChatRequest, ExportChatInviteRequest,  AddChatUserRequest, EditChatPhotoRequest
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import ChatAdminRights, ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.errors import UserNotParticipantError, ChatAdminRequiredError, ChannelPrivateError
from telethon.errors import FloodWaitError, UserNotMutualContactError
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, InputChatUploadedPhoto
from config import *
from utils import *
from withdrawal import *
import re  
from deposit import *
from datetime import datetime,  timedelta
from refund import *
from telegram.error import BadRequest
from login import *
from config import DEAL_TYPE_DISPLAY

telethon_client = None
client_listening = False

async def start_telethon_client():
    global telethon_client
    if telethon_client is None:
        telethon_client = TelegramClient("admin_session", API_ID, API_HASH)
        await telethon_client.connect()
        print("Admin Telethon client connected")      
    if not await telethon_client.is_user_authorized():
        return False
    return True



def load_fees():
    with open('config.json', 'r') as f:
        config = json.load(f)
    return config['p2p_fee'], config['bs_fee'], config['allfee']

def calculate_fee(amount, deal_type):
    p2p_fee, bs_fee, allfee = load_fees()
    if deal_type == "p2p":
        fee_percentage = p2p_fee
    elif deal_type == "b_and_s":
        fee_percentage = bs_fee
    else:
        fee_percentage = allfee
    return amount * (fee_percentage / 100)

async def is_bot_admin(context, chat_id):
    """Robust admin check using status and permissions."""
    bot_user = await context.bot.get_me()
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        is_admin = False
        for admin in admins:
            # Print debug info for diagnosis
            print(f"[is_bot_admin] user.id={admin.user.id} status={getattr(admin, 'status', None)} can_manage_chat={getattr(admin, 'can_manage_chat', None)}")
            if admin.user.id == bot_user.id:
                # Check admin via status/capabilities, not only list presence
                status = getattr(admin, 'status', None)
                if status in ('administrator', 'creator') or getattr(admin, 'can_manage_chat', False):
                    is_admin = True
                break
        return is_admin
    except Exception as e:
        print(f"[is_bot_admin] Error checking admin status: {e}")
        return False


async def handle_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != str(ADMIN_ID):
        await update.message.reply_text("You are not authorized to use this command.")
        return
    group_id = None
    # Support /leave or /leave {group_id}
    if context.args and len(context.args) > 0:
        try:
            group_id = int(context.args[0])
        except Exception:
            await update.message.reply_text("Invalid group_id for /leave. Usage: /leave {group_id}")
            return
    else:
        group_id = update.effective_chat.id
    try:
        await update.message.reply_text(f"Leaving group {group_id} now...")
        await context.bot.leave_chat(group_id)
    except Exception as e:
        await update.message.reply_text(f"Error trying to leave: {e}")
# Register the /leave command handler (add to your bot setup)


async def check_bot_admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE, for_callback=False):
  
    if update.effective_chat.type not in ['group', 'supergroup']:
        error_msg = "This command can only be used in a group."
        if for_callback:
            await update.callback_query.answer(error_msg, show_alert=True)
        else:
            await update.message.reply_text(error_msg)
        return False
    
    try:
        bot_id = (await context.bot.get_me()).id
        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        is_admin = any(admin.user.id == bot_id for admin in admins)
        
        if not is_admin:
            error_msg = "Bot must be an admin to use this feature in this group."
            if for_callback:
                await update.callback_query.answer(error_msg, show_alert=True)
            else:
                await update.message.reply_text(error_msg)
            return False
        
        return True
    except Exception as e:
        print(f"Error checking bot admin status: {e}")
        error_msg = "Unable to verify bot admin status. Please ensure bot has proper permissions."
        if for_callback:
            await update.callback_query.answer(error_msg, show_alert=True)
        else:
            await update.message.reply_text(error_msg)
        return False

# def ensure_bot_admin():
#     """
#     Decorator for handler functions: ensures bot is admin, otherwise responds and stops.
#     Handles both message and callback_query contexts, with detailed logging.
#     """
#     def decorator(handler):
#         @functools.wraps(handler)
#         async def wrapper(update, context, *args, **kwargs):
#             chat_id = None
#             is_query = hasattr(update, "callback_query") and update.callback_query is not None
#             query = update.callback_query if is_query else None

#             print(f"[ensure_bot_admin] Called for handler: {handler.__name__}")
#             print(f"[ensure_bot_admin] Update: {update}")
#             print(f"[ensure_bot_admin] Is callback query: {is_query}")

#             if is_query:
#                 if hasattr(query, "message") and hasattr(query.message, "chat_id"):
#                     chat_id = query.message.chat_id
#                     print(f"[ensure_bot_admin] (query) chat_id: {chat_id}")
#                 else:
#                     print("[ensure_bot_admin] (query) No valid chat_id found in callback query.")
#             elif hasattr(update, "effective_message") and update.effective_message:
#                 chat_id = update.effective_message.chat_id
#                 print(f"[ensure_bot_admin] (message) chat_id: {chat_id}")
#             else:
#                 print("[ensure_bot_admin] No chat_id found, skipping admin check.")
            
#             if chat_id is None:
#                 print("[ensure_bot_admin] chat_id is None, calling handler anyway.")
#                 return await handler(update, context, *args, **kwargs)

#             is_admin = await is_bot_admin(context, chat_id)
#             print(f"[ensure_bot_admin] is_bot_admin result: {is_admin}")

#             if not is_admin:
#                 print("[ensure_bot_admin] Bot is NOT an admin. Sending error message.")
#                 if is_query:
#                     await query.answer(
#                         "❌ Bot must be an admin in this group to perform this action.",
#                         show_alert=True
#                     )
#                 else:
#                     await update.effective_message.reply_text(
#                         "❌ Bot must be an admin in this group to perform this action."
#                     )
#                 return  # Do NOT call the handler

#             print("[ensure_bot_admin] Bot IS an admin. Calling original handler.")
#             return await handler(update, context, *args, **kwargs)
#         return wrapper
#     return decorator

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Help ⚠️", callback_data="help"),
         InlineKeyboardButton("Reviews 🌟", callback_data="reviews")],
        [InlineKeyboardButton("Contact Mod 📞", url=f"https://t.me/{ADMIN_USERNAME}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Load custom messages from custom.json
    with open('custom.json', 'r', encoding='utf-8') as f:
        custom_texts = json.load(f)
    
    welcome_text = (
        f"𝗪𝗲𝗹𝗰𝗼𝗺𝗲 𝘁𝗼 𝘁𝗵𝗲 {custom_texts['escrow_bot_name']}! 🤝\n"
        f"{custom_texts['start_message']}"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

async def handle_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("This command can only be used in a group.")
        return
    # created = await start_telethon_client()
    # if not created:
    #     await update.message.reply_text("*Admin needs to login first ⚠*", parse_mode='Markdown')
    #     return
    
    is_admin = await ensure_bot_admin_telethon(update.effective_chat.id)
    if not is_admin:
        await update.message.reply_text("❌ Bot must be an admin in this group to perform this action.")
        return
    # Don't allow multiple awaiting forms in the same group
    if context.chat_data.get('awaiting_form_id'):
        await update.message.reply_text("A form is already being filled out in this group. Complete or cancel it before starting a new one.")
        return
   
    group_id = update.effective_chat.id
    active_deals = get_all_active_deals()
    deal_id = None
    cur_deal = None
    for d_id, deal in active_deals.items():
        if deal.get('group_id') == group_id and deal.get('status') != 'completed':
            deal_id = d_id
            cur_deal = deal
            break
    if cur_deal:
        kb = []
        if update.effective_user.id == cur_deal.get('starter') or str(update.effective_user.id) == str(ADMIN_ID):
            kb = [[InlineKeyboardButton("End Deal", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(kb) if kb else None
        msg = "*There is already an active deal in this group ❌\n\n You must end the current deal before starting a new one*"
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
        return
    
    notified_flag = f"admin_notified_{update.effective_chat.id}"
    groups_file = "groups.json"
    group_entry = {
        "group_id": update.effective_chat.id,
        "title": update.effective_chat.title,
    }
    if not context.bot_data.get(notified_flag):
        try:
            try:
                invite_link = await context.bot.export_chat_invite_link(update.effective_chat.id)
            except Exception:
                invite_link = "❌ Could not generate invite link"
            group_entry["invite_link"] = invite_link
            try:
                if os.path.exists(groups_file):
                    with open(groups_file, "r") as f:
                        all_groups = json.load(f)
                else:
                    all_groups = []
                if not any(x.get("group_id") == update.effective_chat.id for x in all_groups):
                    group_entry["logged_at"] = datetime.now().isoformat()
                    all_groups.append(group_entry)
                    with open(groups_file, "w") as f:
                        json.dump(all_groups, f, indent=2)
            except Exception as e:
                print(f"Failed to log group in groups.json: {e}")
            # Send ADMIN message only once for this group
            await context.bot.send_message(
                ADMIN_ID,
                f"📢 Bot is admin in group:\n\n <b>{update.effective_chat.title}</b>\n (ID: <code>{update.effective_chat.id}</code>)\n\n"
                f"Invite link:\n <code>{invite_link}</code>",
                parse_mode='HTML'
            )
            context.bot_data[notified_flag] = True
        except Exception as e:
            print(f"Failed to notify admin/log group: {e}")
    # Mark group as having an awaiting form
    context.user_data['awaiting_form'] = True
    # Save the message id, so form replies must reply to this message
    keyboard = [[InlineKeyboardButton("❌", callback_data="cancel_form")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Load custom messages from custom.json
    with open('custom.json', 'r', encoding='utf-8') as f:
        custom_texts = json.load(f)
    
    msg = await update.message.reply_text(
        custom_texts['form_message'],
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    context.chat_data['awaiting_form_id'] = msg.message_id
    context.user_data['form_prompt_msg_id'] = msg.message_id

def parse_time_duration(time_text):
    """Parse time duration from text and return hours as integer"""
    time_text = time_text.lower().strip()
    
    # Remove common words
    time_text = time_text.replace('time:', '').strip()
    
    # Parse different formats
    import re
    
    # Match patterns like "2 hours", "1 hr", "3 h", "30 minutes", "1.5 hours"
    hour_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b',
        r'(\d+(?:\.\d+)?)\s*(?:hour|hr)\b'
    ]
    
    minute_patterns = [
        r'(\d+)\s*(?:minutes?|mins?|m)\b'
    ]
    
    # Try hour patterns first
    for pattern in hour_patterns:
        match = re.search(pattern, time_text)
        if match:
            hours = float(match.group(1))
            if 1 <= hours <= 24:
                return int(hours) if hours == int(hours) else hours
    
    # Try minute patterns
    for pattern in minute_patterns:
        match = re.search(pattern, time_text)
        if match:
            minutes = int(match.group(1))
            hours = minutes / 60
            if 1 <= hours <= 24:
                return max(1, int(hours))  
    
    return None


async def ensure_bot_admin_telethon(chat_id, bot_username=None, context=None):
    """
    Check if bot is admin in a group/channel using Telethon.
    Works with private groups and channels.
    
    Args:
        chat_id: The chat ID to check
        bot_username: Bot username (optional, will read from config if not provided)
        context: Bot context (optional, for getting bot info)
    
    Returns:
        bool: True if bot is admin, False otherwise
    """
    # TELETHON CHECK 
    global telethon_client
    started = await start_telethon_client()
    if not started:
        print(f"[ensure_bot_admin_telethon] Telethon client did NOT start. Returning False.")
        return False
    
    client = telethon_client
    
    # Get bot username from various sources
    if not bot_username:
        try:
            # Try to get from context first
            if context:
                bot_me = await context.bot.get_me()
                bot_username = bot_me.username
            else:
                # Fallback to config file
                with open('config.json', 'r') as f:
                    config = json.load(f)
                bot_username = config.get('bot_username') or config.get('username')
        except Exception as e:
            print(f"[ensure_bot_admin_telethon] Failed to get bot_username: {e}")
            bot_username = None
    
    if not bot_username:
        return False
    
    # Ensure username has @ prefix
    if not bot_username.startswith('@'):
        bot_username = '@' + bot_username
    
    
    try:
        # Get the chat entity
        try:
            chat_entity = await client.get_entity(chat_id)
        except Exception as e:
            print(f"[ensure_bot_admin_telethon] Failed to get chat entity for {chat_id}: {e}")
            return False
        
        # Get the bot entity
        try:
            bot_entity = await client.get_entity(bot_username)
            bot_id = bot_entity.id
        except Exception as e:
            print(f"[ensure_bot_admin_telethon] Failed to get bot entity for {bot_username}: {e}")
            return False
        
        # Check if it's a channel/supergroup or regular group
        if hasattr(chat_entity, 'megagroup') or hasattr(chat_entity, 'broadcast'):
            # This is a channel or supergroup
            try:
                participant = await client(GetParticipantRequest(
                    channel=chat_entity,
                    participant=bot_entity
                ))
                
                # Check if bot is admin or creator
                if isinstance(participant.participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                    
                    # Additional check for admin rights if it's an admin
                    if isinstance(participant.participant, ChannelParticipantAdmin):
                        admin_rights = participant.participant.admin_rights
                        if admin_rights:
                           
                            return True
                        else:
                            print(f"[ensure_bot_admin_telethon] Bot is admin but has no admin rights")
                            return False
                    else:
                        # Bot is creator
                        return True
                else:
                    print(f"[ensure_bot_admin_telethon] Bot is not admin in channel/supergroup")
                    return False
                    
            except UserNotParticipantError:
                print(f"[ensure_bot_admin_telethon] Bot is not a participant in the channel/supergroup")
                return False
            except ChatAdminRequiredError:
                print(f"[ensure_bot_admin_telethon] Admin required to check participants")
                return False
            except ChannelPrivateError:
                print(f"[ensure_bot_admin_telethon] Channel is private and we don't have access")
                return False
            except Exception as e:
                print(f"[ensure_bot_admin_telethon] Error checking channel participant: {e}")
                return False
        
        else:
            # This is a regular group
            try:
                full_chat = await client(GetFullChatRequest(chat_id=chat_entity.id))
                chat_full = full_chat.full_chat
                
                # Check if bot is in admins list
                for participant in full_chat.users:
                    if participant.id == bot_id:
                        # Found the bot, now check if it's admin
                        for chat_participant in chat_full.participants.participants:
                            if hasattr(chat_participant, 'user_id') and chat_participant.user_id == bot_id:
                                participant_type = type(chat_participant).__name__
                                
                                if 'Admin' in participant_type or 'Creator' in participant_type:
                                    print(f"[ensure_bot_admin_telethon] Bot is admin/creator in regular group")
                                    return True
                                else:
                                    print(f"[ensure_bot_admin_telethon] Bot is not admin in regular group")
                                    return False
                        break
                
                print(f"[ensure_bot_admin_telethon] Bot not found in group participants")
                return False
                
            except Exception as e:
                print(f"[ensure_bot_admin_telethon] Error checking regular group: {e}")
                return False
    
    except Exception as e:
        print(f"[ensure_bot_admin_telethon] Unexpected error: {e}")
        return False


async def process_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only check admin if we're actually about to process form input (not for TOS etc)
    if context.user_data.get('awaiting_form'):
        is_admin = await ensure_bot_admin_telethon(update.effective_chat.id)
        if not is_admin:
            await update.message.reply_text("❌ Bot must be an admin in this group to perform this action.")
            return
    # If this is the TERMS step, save terms, store, and proceed
    if context.user_data.get('awaiting_terms'):
        # Only accept reply to the TOS prompt
        tos_prompt_id = context.user_data.get('tos_prompt_msg_id')
        if not update.message.reply_to_message or update.message.reply_to_message.message_id != tos_prompt_id:
            await update.message.reply_text("Please reply directly to the Terms prompt message to enter your terms.")
            return
        deal_id = context.user_data.get('terms_deal_id')
        if not deal_id:
            await update.message.reply_text("Unexpected error storing terms. Please start form again.")
            context.user_data.pop('awaiting_terms', None)
            context.user_data.pop('tos_prompt_msg_id', None)
            return
        terms = update.message.text.strip()
        deal_data = get_active_deal(deal_id)
        if not deal_data:
            await update.message.reply_text("Deal not found while saving terms. Please start form again.")
            context.user_data.pop('awaiting_terms', None)
            context.user_data.pop('tos_prompt_msg_id', None)
            return
        deal_data['terms_and_conditions'] = terms
        update_active_deal(deal_id, {"terms_and_conditions": terms})
        context.user_data.pop('awaiting_terms', None)
        context.user_data.pop('state', None)
        context.user_data.pop('terms_deal_id', None)
        context.user_data.pop('tos_prompt_msg_id', None)

        buyer_name = deal_data.get('buyer_name', '')
        seller_name = deal_data.get('seller_name', '')
        timer_hours = deal_data.get('timer_hours', 1)
        keyboard = [
            [InlineKeyboardButton("Click Confirm ✅", callback_data=f"confirm_form_{deal_id}")],
            [InlineKeyboardButton("End Deal ❌", callback_data=f"back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        timer_display = f"{timer_hours} Hour{'s' if timer_hours != 1 else ''}"
        # Better format TOS for professional look
        formatted_terms = '\n'.join(f"<b>•</b> {line.strip()}" if line.strip() else '' for line in terms.splitlines())
        tos_msg_body = (
            f"<b>TERMS & CONDITIONS OF DEAL</b>\n\n"
            f"{formatted_terms}" if formatted_terms.strip() else "<i>No terms provided.</i>"
        )
        await update.message.reply_text(
            f"<b>𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b>\n\n"
            f"👤 Buyer: <a href='tg://user?id={deal_data['buyer']}'>{buyer_name}</a>\n"
            f"👥 Seller: <a href='tg://user?id={deal_data['seller']}'>{seller_name}</a>\n"
            f"🔵 Deal: {deal_data['deal_type']}\n"
            f"💰 Amount: ${deal_data['amount']:.2f}\n\n"
            f"⏰ Timer: {timer_display}\n\n"
            f"{tos_msg_body}\n\n"
            f"<i>Both buyer and seller must confirm to proceed</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        context.user_data['awaiting_form'] = False
        print(">>> Terms collected and confirmation message sent")
        return

    if not context.user_data.get('awaiting_form'):
        print(">>> Not awaiting form, returning early")
        return
    # Clear group awaiting marker after form completion or cancel
    context.chat_data.pop('awaiting_form_id', None)
    context.user_data.pop('form_prompt_msg_id', None)
    text = update.message.text
    lines = text.split('\n')
    form_data = {}
    entities = update.message.entities
    
    print(f">>> Starting form processing with {len(lines)} lines")
    print(f">>> Raw text: {text}")
    print(f">>> Entities found: {entities}")
    
    try:
        global telethon_client
        # Progress tracking setup
        form_progress_msg = await update.message.reply_text("<b>PROCESSING FORM: 0%</b>", parse_mode='HTML')
        progress = 0
        progress_steps = ["buyer", "seller", "deal", "price", "time"]
        curr_step = 0
        # ---
        for line in lines:
            line = line.replace('  ', ' ') 
            print(f">>> Processing line: {line}")
            
            if line.lower().startswith('buyer:'):
                print(">>> Processing buyer...")
                curr_step = 1
                progress = 20
                try:
                    await update.message.get_bot().edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=form_progress_msg.message_id,
                        text=f"<b>PROCESSING FORM: {progress}%</b>",
                        parse_mode='HTML')
                except Exception: pass
                await start_telethon_client()
                buyer_found = False
                
                for entity in entities:
                    if entity.type in ['text_mention', 'mention']:
                        entity_text = text[entity.offset:entity.offset + entity.length]
                        print(f">>> Found buyer entity: {entity_text}")
                        print(f">>> Entity offset: {entity.offset}, length: {entity.length}")
                        print(f">>> Checking if {entity_text} is in {line}")
                        
                        if entity_text in line:
                            try:
                                print(f">>> Attempting to get entity for {entity_text}")
                                user = await telethon_client.get_entity(entity_text)
                                
                                # NEW: Better error handling for entity types
                                if hasattr(user, 'first_name'):
                                    form_data['buyer_id'] = user.id
                                    form_data['buyer_name'] = user.first_name
                                    print(f">>> Successfully resolved buyer: {form_data['buyer_name']} (ID: {form_data['buyer_id']})")
                                    buyer_found = True
                                else:
                                    keyboard = [[InlineKeyboardButton("❌ Cancel Form", callback_data="cancel_form")]]
                                    reply_markup = InlineKeyboardMarkup(keyboard)
                                    msg = await update.message.reply_text(
                                        f"❌ The username {entity_text} is not a valid user account (it might be a channel, bot, or invalid username).\n\n"
                                        "Please reply to this message with a corrected form using valid user accounts, or click Cancel to end the form.",
                                        reply_markup=reply_markup
                                    )
                                    context.user_data['form_prompt_msg_id'] = msg.message_id
                                    context.chat_data['awaiting_form_id'] = msg.message_id
                                    return
                                    
                            except Exception as e:
                                print(f">>> Error resolving buyer entity: {e}")
                               
                                keyboard = [[InlineKeyboardButton("❌ Cancel Form", callback_data="cancel_form")]]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                msg = await update.message.reply_text(
                                    f"❌ Error resolving username {entity_text}: {str(e)}\n\n"
                                    "Please reply to this message with a corrected form using valid usernames, or click Cancel to end the form.",
                                    reply_markup=reply_markup
                                )
                                context.user_data['form_prompt_msg_id'] = msg.message_id
                                context.chat_data['awaiting_form_id'] = msg.message_id
                                return
                
                if not buyer_found:
                    print(">>> No buyer entity was matched in the line")
                    msg = await update.message.reply_text(
                                    "💡 Form Guide:\n\n"
                                    "1. Make sure usernames are correct\n"
                                    "2. Both users must be in the group\n"
                                    "3. Try copying the format below:\n\n"
                                    "<code>Buyer: @username\n"
                                    "Seller: @username\n"
                                    "Deal: item description\n"
                                    "Price: $amount</code>",
                                    parse_mode='HTML'
                                )
                    context.user_data['form_prompt_msg_id'] = msg.message_id
                    context.chat_data['awaiting_form_id'] = msg.message_id

            elif line.lower().startswith('seller:'):
                print(">>> Processing seller...")
                curr_step = 2
                progress = 40
                try:
                    await update.message.get_bot().edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=form_progress_msg.message_id,
                        text=f"<b>PROCESSING FORM: {progress}%</b>",
                        parse_mode='HTML')
                except Exception: pass
                
                
                await start_telethon_client()

               
                seller_found = False
                
                for entity in entities:
                    if entity.type in ['text_mention', 'mention']:
                        entity_text = text[entity.offset:entity.offset + entity.length]
                        print(f">>> Found seller entity: {entity_text}")
                        print(f">>> Entity offset: {entity.offset}, length: {entity.length}")
                        print(f">>> Checking if {entity_text} is in {line}")
                        
                        if entity_text in line:
                            try:
                                print(f">>> Attempting to get entity for {entity_text}")
                                user = await telethon_client.get_entity(entity_text)
                                
                                # NEW: Better error handling for entity types
                                if hasattr(user, 'first_name'):
                                    form_data['seller_id'] = user.id
                                    form_data['seller_name'] = user.first_name
                                    print(f">>> Successfully resolved seller: {form_data['seller_name']} (ID: {form_data['seller_id']})")
                                    seller_found = True
                                else:
                                    # Handle channels, bots, or other entity types
                                    
                                    keyboard = [[InlineKeyboardButton("❌ Cancel Form", callback_data="cancel_form")]]
                                    reply_markup = InlineKeyboardMarkup(keyboard)
                                    msg = await update.message.reply_text(
                                        f"❌ The username {entity_text} is not a valid user account (it might be a channel, bot, or invalid username).\n\n"
                                        "Please reply to this message with a corrected form using valid user accounts, or click Cancel to end the form.",
                                        reply_markup=reply_markup
                                    )
                                    context.user_data['form_prompt_msg_id'] = msg.message_id
                                    context.chat_data['awaiting_form_id'] = msg.message_id
                                    return
                                    
                            except Exception as e:
                                print(f">>> Error resolving seller entity: {e}")
                                
                                keyboard = [[InlineKeyboardButton("❌ Cancel Form", callback_data="cancel_form")]]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                msg = await update.message.reply_text(
                                    f"❌ Error resolving username {entity_text}: {str(e)}\n\n"
                                    "Please reply to this message with a corrected form using valid usernames, or click Cancel to end the form.",
                                    reply_markup=reply_markup
                                )
                                context.user_data['form_prompt_msg_id'] = msg.message_id
                                context.chat_data['awaiting_form_id'] = msg.message_id
                                return
                
                if not seller_found:
                    print(">>> No seller entity was matched in the line")
                
            elif line.lower().startswith('deal:'):
                deal_type = line.split('Deal:')[1].strip()
                form_data['deal_type'] = deal_type
                print(f">>> Added deal_type: {deal_type}")
                curr_step = 3
                progress = 60
                try:
                    await update.message.get_bot().edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=form_progress_msg.message_id,
                        text=f"<b>PROCESSING FORM: {progress}%</b>",
                        parse_mode='HTML')
                except Exception: pass
                
            elif line.lower().startswith('price:'):
                try:
                    # Handle different price formats
                    price_text = line.split(':', 1)[1].strip()
                    price_text = price_text.replace('$', '').strip()
                    price_text = price_text.replace('usd', '').strip()
                    amount = float(price_text)
                    form_data['amount'] = amount
                    if amount < 1:
                        await update.message.reply_text("❌ Amount must be at least $1. Please enter a valid amount.")
                        return
                except ValueError:      
                    curr_step = 4
                    progress = 80
                    try:
                        await update.message.get_bot().edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=form_progress_msg.message_id,
                            text=f"<b>PROCESSING FORM: {progress}%</b>",
                            parse_mode='HTML')
                    except Exception: pass
                except:
                    await update.message.reply_text(
                        "💡 Price should be a number like:\n"
                        "Price: $100\n"
                        "Price: 100\n"
                        "Price: 100.50"
                    )
                    return
            elif line.lower().startswith('time:'):
                time_text = line.split(':', 1)[1].strip()
                parsed_time = parse_time_duration(time_text)
                if parsed_time:
                    form_data['timer_hours'] = parsed_time
                    print(f">>> Added timer_hours: {parsed_time}")
                    curr_step = 5
                    progress = 95
                    try:
                        await update.message.get_bot().edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=form_progress_msg.message_id,
                            text=f"<b>PROCESSING FORM: {progress}%</b>",
                            parse_mode='HTML')
                    except Exception: pass
                else:
                    msg = await update.message.reply_text(
                        "💡 Invalid time format. Use:\n"
                        "Time: 2 hours\n"
                        "Time: 1 hr\n"
                        "Time: 3 h\n"
                        "Time: 30 minutes\n\n"
                        "Valid range: 1 - 24 hours"
                    )
                    context.user_data['form_prompt_msg_id'] = msg.message_id
                    context.chat_data['awaiting_form_id'] = msg.message_id
                    return
        
        print(f">>> Form data collected: {form_data}")
        required_fields = ['buyer_id', 'buyer_name', 'seller_id', 'seller_name', 'deal_type', 'amount']
        missing_fields = [field for field in required_fields if field not in form_data]
        
        progress = 100
        try:
            await update.message.get_bot().edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=form_progress_msg.message_id,
                text=f"<b>PROCESSING FORM: {progress}%</b>",
                parse_mode='HTML')
        except Exception: pass
        
        print(f">>> Required fields: {required_fields}")
        print(f">>> Missing fields: {missing_fields}")
        
        if not all(k in form_data for k in ['buyer_id', 'buyer_name', 'seller_id', 'seller_name', 'deal_type', 'amount']):
            keyboard = [[InlineKeyboardButton("❌ Cancel Form", callback_data="cancel_form")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            msg = await update.message.reply_text(
                "Form not arranged correctly ❌\n\n"
                "💡 Copy and fill this format:\n"
                "<code>Buyer: @username\n"
                "Seller: @username\n"
                "Deal: what you're trading\n"
                "Price: $amount\n"
                "Time: duration (optional)</code>",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            context.user_data['form_prompt_msg_id'] = msg.message_id
            context.chat_data['awaiting_form_id'] = msg.message_id
            return

        # Check if buyer and seller are the same person
        if form_data['buyer_id'] == form_data['seller_id']:
            await update.message.reply_text("Buyer and seller cannot be the same person. Please enter different users for each role.")
            context.user_data['awaiting_form'] = False
            context.chat_data.pop('awaiting_form_id', None)
            context.user_data.pop('form_prompt_msg_id', None)
            return
            
        deal_id = generate_deal_id(form_data['buyer_id'], None, update.effective_chat.id)
        print(f">>> Generated deal_id: {deal_id}")

        timer_hours = form_data.get('timer_hours', 1)
        
        deal_data = {
            "status": "initiated",
            "starter": update.effective_user.id,
            "group_id": update.effective_chat.id,
            "buyer": form_data['buyer_id'],
            "seller": form_data['seller_id'],
            "buyer_name": form_data['buyer_name'],
            "seller_name": form_data['seller_name'],
            "amount": form_data['amount'],
            "deal_type": form_data['deal_type'],
            "timer_hours": timer_hours,
            "timestamp": datetime.now().isoformat()
        }
        
        print(f">>> Deal data prepared: {deal_data}")
        save_active_deal(deal_id, deal_data)

        # Send deal details to involved parties
        try:
            invite_link = await context.bot.export_chat_invite_link(update.effective_chat.id)
        except Exception:
            invite_link = "❌ Could not generate invite link"

        deal_details = (
            f"<b>🔔 New Deal Initiated!</b>\n\n"
            f"<b>Group:</b> {update.effective_chat.title} (ID: <code>{update.effective_chat.id}</code>)\n"
            f"<b>Group Link:</b> {invite_link}\n"
            f"<b>Buyer:</b> <a href='tg://user?id={form_data['buyer_id']}'>{form_data['buyer_name']}</a>\n"
            f"<b>Seller:</b> <a href='tg://user?id={form_data['seller_id']}'>{form_data['seller_name']}</a>\n"
            f"<b>Deal:</b> {form_data['deal_type']}\n"
            f"<b>Amount:</b> ${form_data['amount']:.2f}\n"
            f"<b>Timer:</b> {form_data.get('timer_hours', 1)} hours\n\n"
            f"Timestamp: <i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
        )

        # Send to admin, buyer, and seller
        try:
            await context.bot.send_message(ADMIN_ID, deal_details, parse_mode='HTML', disable_web_page_preview=True)
        except Exception as e:
            print(f"Failed to send deal details to admin: {e}")

        try:
            await context.bot.send_message(form_data['buyer_id'], deal_details, parse_mode='HTML', disable_web_page_preview=True)
        except Exception as e:
            print(f"Failed to send deal details to buyer: {e}")

        try:
            await context.bot.send_message(form_data['seller_id'], deal_details, parse_mode='HTML', disable_web_page_preview=True)
        except Exception as e:
            print(f"Failed to send deal details to seller: {e}")
        try:
            form_prompt_id = context.user_data.get('form_prompt_msg_id') or context.chat_data.get('awaiting_form_id')
            if form_prompt_id:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=form_prompt_id
                )
                context.user_data.pop('form_prompt_msg_id', None)
                context.chat_data.pop('awaiting_form_id', None)
        except Exception as e:
            print(f"Failed to delete form prompt message: {e}")

        # Prompt for terms and conditions NEXT
        context.user_data['awaiting_terms'] = True
        context.user_data['state'] = 'AWAITING_TOS'
        context.user_data['terms_deal_id'] = deal_id
        keyboard = [[InlineKeyboardButton("❌", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        with open("custom.json", "r", encoding="utf-8") as f:
            custom = json.load(f)

        tos_prompt = custom.get("tos_prompt_message", (
            "<b>TERMS AND CONDITIONS OF DEAL</b>\n\n"
            "<i>Please reply to this message and clearly state all rules, obligations, and important points governing the deal.\n"
            "• Use clear paragraphs or lists.\n"
            "• Example: <b>All payments must be made before delivery. No refunds unless mutually agreed. Both parties must follow the group rules...</b></i>"
        ))
        tos_msg = await update.message.reply_text(
            tos_prompt,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        context.user_data['tos_prompt_msg_id'] = tos_msg.message_id
        return
    except Exception as e:
        print(f">>> CRITICAL ERROR processing form: {str(e)}")
        print(f">>> Exception type: {type(e)}")
        import traceback
        print(f">>> Traceback: {traceback.format_exc()}")
        await update.message.reply_text("Invalid form format or user not found. Please try again.")
        context.user_data['awaiting_form'] = False



async def handle_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    formatted_reviews = review_system.get_formatted_reviews()
    
    if not formatted_reviews:
        keyboard = [[InlineKeyboardButton("Back 🔙", callback_data="mainmenu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "No reviews available yet. Be the first to complete a deal! 🌟",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return
        
    review_text = (
        "<b>🌟 SELLER REVIEWS</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )
    
    for seller_id, data in formatted_reviews.items():
        review_text += (
            f"<b>👤 <a href='tg://user?id={seller_id}'>{data['name']}</a></b>\n"
            f"P2P Trade 🤝: {data['p2p_trades']}\n"
            f"Buy & Sell 💎: {data['bs_trades']}\n"
            f"<b>Total Rating:</b> <b>👍 {data['positive_trades']} | 👎 {data['negative_trades']}</b>\n\n"
            f"<i>Buyers that Rated:</i>\n"
        )
        
        for reviewer_id, reviewer_data in data['reviewers'].items():
            review_text += (
                f"• <a href='tg://user?id={reviewer_id}'>{reviewer_data['name']}</a>"
                f" (👍{reviewer_data['positive']} | 👎{reviewer_data['negative']})\n"
            )
        
        review_text += "\n━━━━━━━━━━━━━━━━━━\n"
    
    keyboard = [[InlineKeyboardButton("Back 🔙", callback_data="mainmenu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        review_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    await query.edit_message_text(
        review_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def handle_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    groups_text = "<b>🔍 Bot's Group List:</b>\n\n"
    
    try:
        # Get bot's updates to find groups
        updates = await context.bot.get_updates()
        seen_groups = set()
        
        for update in updates:
            if update.message and update.message.chat:
                chat = update.message.chat
                if chat.type in ['group', 'supergroup'] and chat.id not in seen_groups:
                    try:
                        invite_link = await context.bot.export_chat_invite_link(chat.id)
                        groups_text += f"📌 <b>{chat.title}</b>\n"
                        groups_text += f"🔗 Link: {invite_link}\n\n"
                        seen_groups.add(chat.id)
                    except Exception:
                        groups_text += f"📌 <b>{chat.title}</b>\n"
                        groups_text += "❌ Could not generate invite link\n\n"
                        seen_groups.add(chat.id)

        await update.message.reply_text(groups_text, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error fetching groups: {str(e)}")

async def handle_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global telethon_client
    
    if update.effective_user.is_bot:
        await update.message.reply_text("This command can only be used by real users.")
        return

    created = await start_telethon_client()
    if not created:
        await update.message.reply_text("*Admin needs to login first ⚠*", parse_mode='Markdown')
        return
    client = telethon_client
        
    try:
        with open('custom.json', 'r', encoding='utf-8') as f:
            custom = json.load(f)

        brand_name = custom.get("brand_name", "FLUXX")
        unique_id = f"{random.randint(0, 999):03d}"
        group_title = f"{brand_name} 𝙴S𝙲𝚁𝙾𝚆 𝙶𝚁𝙾𝚄𝙿 {unique_id}"
        group_description = f"Welcome to the {brand_name} ESCROW GROUP. This is a secure environment for conducting transactions with the assistance of our escrow bot."
        
        bot_username = (await context.bot.get_me()).username
        user = await client.get_input_entity(update.effective_user.username)
        bot = await client.get_input_entity(bot_username)
        
        # Create the group
        await client(CreateChatRequest(users=[user], title=group_title))

        # 🔹 Fetch the newly created chat from your recent dialogs
        dialogs = await telethon_client(GetDialogsRequest(
            offset_date=None,
            offset_id=0,
            offset_peer=InputPeerEmpty(),
            limit=10,  # Get last 10 chats
            hash=0
        ))

        chat_id = None
        for dialog in dialogs.chats:
            if dialog.title == group_title:  # Match by title
                chat_id = dialog.id
                break

        if chat_id is None:
            await update.message.reply_text("⚠️ Group creation failed: Could not retrieve chat ID.")
            return
        
        print(f">>> Successfully retrieved chat_id: {chat_id}")
        
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            
            profile_url = config.get('profileurl', '')
            
            if profile_url and profile_url.strip():
                
                import requests
                from io import BytesIO
                
                response = requests.get(profile_url)
                if response.status_code == 200 and response.headers.get("Content-Type","").startswith("image"):
                    try:
                        from PIL import Image
                        img = Image.open(BytesIO(response.content)).convert("RGB")
                        temp_buf = BytesIO()
                        img.save(temp_buf, format="JPEG")
                        temp_buf.seek(0)
                        temp_buf.name = "photo.jpg"  # Critical for telethon upload_file -> InputChatUploadedPhoto
                        
                        # Upload and set as profile picture
                        await telethon_client(EditChatPhotoRequest(
                            chat_id=chat_id,
                            photo=InputChatUploadedPhoto(
                                file=await telethon_client.upload_file(temp_buf)
                            )
                        ))
                        print(f">>> Successfully set profile picture from URL (validated, JPEG + extension set)")
                    except Exception as pic_ex:
                        print(f">>> Image conversion or upload failed: {pic_ex}")
                else:
                    print(f">>> Failed to download profile picture or not an image. HTTP {response.status_code} Content-Type: {response.headers.get('Content-Type')}")
            else:
                print(f">>> No profile URL provided in config")
        except Exception as e:
            print(f">>> Failed to set profile picture: {str(e)}")
            # If setting profile picture fails, we continue with group creation
        
        try:
            await telethon_client(AddChatUserRequest(chat_id, bot, fwd_limit=10))
        except Exception as e:
            print(f"Failed to add bot to group: {str(e)}")

        # 🔹 Promote the bot to admin
        try:
            await telethon_client.edit_admin(
                chat_id,
                bot,
                is_admin=True,
                add_admins=False,
                pin_messages=True,
                delete_messages=True,
                ban_users=True,
                invite_users=True
            )
        except Exception as e:
            print(f"Failed to promote bot to admin: {str(e)}")

        # 🔹 Set group description (Only if needed)
        try:
            await telethon_client(functions.messages.EditChatAboutRequest(
                peer=chat_id,
                about=group_description
            ))
        except Exception as e:
            print(f"Failed to set group description: {str(e)}")

        # 🔹 Ensure chat history is visible
        try:
            await telethon_client(functions.messages.EditChatDefaultBannedRightsRequest(
                peer=chat_id,
                banned_rights=types.ChatBannedRights(
                    until_date=None,
                    view_messages=False,  # ✅ History visible
                    send_messages=None,
                    send_media=None,
                    send_stickers=None,
                    send_gifs=None,
                    send_games=None,
                    send_inline=None,
                    embed_links=None
                )
            ))
        except Exception as e:
            print(f"Skipping redundant chat permissions update: {str(e)}")

        # ---- DELETE RECENT SERVICE MESSAGES (created, photo, users added) ----
        try:
            from telethon.tl.types import MessageService
            messages = await telethon_client.get_messages(chat_id, limit=10)
            to_delete = [msg.id for msg in messages if isinstance(msg, MessageService)]
            if to_delete:
                await telethon_client.delete_messages(chat_id, to_delete)
                print(f">>> Deleted group service messages: {to_delete}")
        except Exception as e:
            print(f"Error cleaning up service messages: {str(e)}")

        # 🔹 Generate invite link
        try:
            invite = await telethon_client(ExportChatInviteRequest(
                peer=chat_id,
                legacy_revoke_permanent=True,
                expire_date=None,
                usage_limit=None
            ))
            invite_link = invite.link
        except Exception as e:
            print(f"Failed to generate invite link: {str(e)}")
            invite_link = "❌ Failed to generate link"

        # ✅ Send confirmation message
        await update.message.reply_text(
            "✅ Group created successfully!\n\n"
            f"Title: {group_title}\n\n"
            f"Join here: {invite_link}\n\n"
        )
        # ANNOUNCE to group how to start a deal
        try:
            msg_body = (
                f"<b>Welcome to {brand_name} ESCROW GROUP!</b>\n\n"
                f"To start a new deal, simply send in this group.\n"
                "<b>Ensure all instructions are followed carefully.</b>\n\n"
            )
            from telethon.tl.functions.messages import SendMessageRequest
            await telethon_client(SendMessageRequest(peer=chat_id, message=msg_body))
        except Exception as e:
            print(f"Could not send usage announcement: {e}")
        # Notify ADMIN_ID and log group
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Bot created group: <b>{group_title}</b>\nInvite link: {invite_link}",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Failed to notify admin of group creation: {str(e)}")
        # Log group info
        import datetime
        created_file = 'groups.json'
        log_entry = {
            "group_title": group_title,
            "invite_link": invite_link,
            "chat_id": chat_id,
            "created_at": datetime.datetime.now().isoformat()
        }
        try:
            if os.path.exists(created_file):
                with open(created_file, 'r') as f:
                    data = json.load(f)
            else:
                data = []
            data.append(log_entry)
            with open(created_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Failed to write groups.json: {str(e)}")
        
    except FloodWaitError as e:
        await update.message.reply_text(f"⚠️ Too many requests. Please try again after {e.seconds} seconds.")
    except UserNotMutualContactError:
        await update.message.reply_text("⚠️ The bot needs to be able to see your messages. Please start a chat with the bot first.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Creation failed: {str(e)}")
    finally:
        pass  # client is managed globally, do not disconnect

async def handle_startdeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_id = update.effective_chat.id
    user_id = update.effective_user.id
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("This command can only be used in a group.")
        return
    # Check bot admin status
    bot_id = (await context.bot.get_me()).id
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    if not any(admin.user.id == bot_id for admin in admins):
        await update.message.reply_text("Bot must be an admin to use /startdeal in this group.")
        return

    active_deals = get_all_active_deals()
    for d_id, deal in active_deals.items():
        if deal['group_id'] == group_id:
            if deal['status'] == 'completed':
                remove_active_deal(d_id)
                continue
            await update.message.reply_text("There's already an active deal in this group. Please wait for it to complete.")
            return

    deal_id = generate_deal_id(user_id, None, group_id)
    context.chat_data['deal_id'] = deal_id
    context.chat_data['deal_starter'] = user_id
    
    deal_data = {
        "status": "initiated",
        "starter": user_id,
        "group_id": group_id,
        "buyer": None,
        "seller": None,
        "amount": None,
        "deal_type": None,
        "timestamp": datetime.now().isoformat()
    }
    save_active_deal(deal_id, deal_data)
    keyboard = [
        [InlineKeyboardButton("Buyer", callback_data="buyer"),
         InlineKeyboardButton("Seller", callback_data="seller")],
        [InlineKeyboardButton("Back", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "A new deal has been started. Please select your role:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    message = query.message
    group_id = message.chat.id
    active_deals = get_all_active_deals()
    deal_id = None
    for d_id, deal in active_deals.items():
        if deal['group_id'] == group_id:
            deal_id = d_id
            break
    deal_data = get_active_deal(deal_id) if deal_id else None
    
    if query.data in ["buyer", "seller"] and not deal_data:
        user_id = query.from_user.id
        group_id = update.effective_chat.id
        deal_id = generate_deal_id(user_id, None, group_id)
        
        deal_data = {
            "status": "initiated",
            "starter": user_id,
            "group_id": group_id,
            "buyer": None,
            "seller": None,
            "amount": None,
            "deal_type": None,
            "timestamp": datetime.now().isoformat()
        }
        save_active_deal(deal_id, deal_data)
        context.chat_data['deal_id'] = deal_id

    # ---- BUTTON ABORT IF BOT NOT ADMIN + DEAL DEPOSITED ----
    action_buttons = {"release_payment", "check_timer", "mod", "back"}
    if deal_data and deal_data.get("status") == "deposited" and query.data in action_buttons:
        is_admin = await ensure_bot_admin_telethon(query.message.chat.id)
        if not is_admin:
           
            deal_info = json.dumps(deal_data, indent=2, default=str)
            buyer_link = f"<a href='tg://user?id={deal_data['buyer']}'>{deal_data.get('buyer_name','UNKNOWN')}</a>"
            seller_link = f"<a href='tg://user?id={deal_data['seller']}'>{deal_data.get('seller_name','UNKNOWN')}</a>"
            admin_warn = (
                    f"🚨<b>BOT IS NO LONGER ADMIN</b>\n\n"
                    f"Deal forcibly ended.\n"
                    f"Group ID: <code>{group_id}</code>\n"
                    f"<b>Buyer:</b> {buyer_link}\n"
                    f"<b>Seller:</b> {seller_link}\n\n"
                    f"<code>/leave {group_id}</code>\n to force bot exit this group."
            )
            remove_active_deal(deal_id)
            try:
                await context.bot.send_message(ADMIN_ID, admin_warn, parse_mode='HTML')
            except Exception as e:
                print(f"Error sending admin warning: {e}")
            try:
                await query.edit_message_text(
                    "❌ Deal ended: Bot is NOT admin. Contact the admin for resolution.", parse_mode='HTML'
                )
            except Exception:
                pass
            return
    
    if query.data == "start_deal":
        if update.effective_chat.type not in ['group', 'supergroup', 'channel']:
            await query.answer("This command can only be used in a group or channel ❌", show_alert=True)
            return
        user_id = query.from_user.id
        group_id = update.effective_chat.id
        deal_id = generate_deal_id(user_id, None, group_id)

        active_deals = get_all_active_deals()
        for d_id, deal in active_deals.items():
            if deal['group_id'] == group_id:
                if deal['status'] == 'completed':
                    remove_active_deal(d_id)
                    continue
                await query.answer("There's already an active deal in this group ❌\n\n Please wait for it to complete.")
                return
            

        
        # Save initial deal data
        deal_data = {
            "status": "initiated",
            "starter": user_id,
            "group_id": group_id,
            "buyer": None,
            "seller": None,
            "amount": None,
            "deal_type": None,
            "timestamp": datetime.now().isoformat()
        }
        save_active_deal(deal_id, deal_data)
        context.chat_data['deal_id'] = deal_id
        with open('custom.json', 'r', encoding='utf-8') as f:
            custom = json.load(f)

        brand_name = custom.get("brand_name", "FLUXX")
        keyboard = [
            [InlineKeyboardButton("Buyer", callback_data="buyer"),
             InlineKeyboardButton("Seller", callback_data="seller")],
            [InlineKeyboardButton("Back", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            format_text(f"{brand_name} ESCROW SERVICE\n\nPlease select your role:", "italic"),
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
   
    if query.data in ["buyer", "seller"]:
    
        if deal_data[query.data] is not None and deal_data[query.data] != query.from_user.id:
            await query.answer(f"Someone else already claimed the {query.data.capitalize()} role", show_alert=True)
            return

        # Check if user has already selected a different role
        other_role = 'seller' if query.data == 'buyer' else 'buyer'
        
        # If user already has the other role, switch roles
        if query.from_user.id == deal_data[other_role]:
            # Clear the user's previous role
            deal_data[other_role] = None
            update_active_deal(deal_id, {other_role: None})
            
        # Assign the user to the new role
        deal_data[query.data] = query.from_user.id
        update_active_deal(deal_id, {query.data: query.from_user.id})

        if deal_data['buyer'] and deal_data['seller']:
            buyer = await context.bot.get_chat(deal_data['buyer'])
            seller = await context.bot.get_chat(deal_data['seller'])
            
            keyboard = [
                [InlineKeyboardButton("P2P Trade", callback_data="p2p"),
                InlineKeyboardButton("Buy & Sell", callback_data="b_and_s")],
                [InlineKeyboardButton("Back", callback_data="back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Determine which role was filled first
            first_role = 'buyer' if deal_data['buyer'] != query.from_user.id else 'seller'
            first_user = buyer if first_role == 'buyer' else seller
            second_role = 'seller' if first_role == 'buyer' else 'buyer'
            
            await context.bot.send_message(  
                chat_id=group_id,  
                text=(  
                    f"ℋ𝑒𝓁𝓁𝑜, <a href='tg://user?id={first_user.id}'>{first_user.first_name}</a>, the 𝑟𝑜𝑙𝑒 {second_role} has been claimed by <a href='tg://user?id={query.from_user.id}'>{query.from_user.first_name}</a>. You can now proceed with 𝑑𝑒𝑎𝑙 selection "
                
            ),
                parse_mode="HTML"
            )
            
            await query.edit_message_text(
                "<b>𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b>\n\n"
                f"Buyer: <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
                f"Seller: <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>\n\n"
                f"𝗕𝘂𝘆𝗲𝗿, 𝗽𝗹𝗲𝗮𝘀𝗲 𝗰𝗵𝗼𝗼𝘀𝗲 𝘁𝗵𝗲 𝘁𝘆𝗽𝗲 𝗼𝗳 𝗱𝗲𝗮𝗹:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            buyer_text = 'Not selected'
            seller_text = 'Not selected'
            
            if deal_data['buyer']:
                buyer = await context.bot.get_chat(deal_data['buyer'])
                buyer_text = f"<a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>"
            
            if deal_data['seller']:
                seller = await context.bot.get_chat(deal_data['seller'])
                seller_text = f"<a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>"
            
            await query.edit_message_text(
                f"Buyer: {buyer_text}\nSeller: {seller_text}\n\nWaiting for both roles to be filled.",
                reply_markup=query.message.reply_markup,
                parse_mode='HTML'
            )


    elif query.data in ["p2p", "b_and_s"]:
        if query.from_user.id != deal_data['buyer']:
            await query.answer("Only the buyer can select the deal type", show_alert=True)
            return
                      
        

        deal_type_display = DEAL_TYPE_DISPLAY.get(query.data, query.data)
        deal_data["deal_type"] = query.data
        update_active_deal(deal_id, {"deal_type": query.data})
        buyer = await context.bot.get_chat(deal_data['buyer'])
        seller = await context.bot.get_chat(deal_data['seller'])
        
        keyboard = [
            [InlineKeyboardButton("1 Hour", callback_data="timer_1"),
            InlineKeyboardButton("2 Hours", callback_data="timer_2")],
            [InlineKeyboardButton("3 Hours", callback_data="timer_3"),
            InlineKeyboardButton("4 Hours", callback_data="timer_4")],
            [InlineKeyboardButton("5 Hours", callback_data="timer_5"),
            InlineKeyboardButton("Skip (Default 1h)", callback_data="timer_default")],
            [InlineKeyboardButton("❌", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"<b>𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b>\n\n"
            f"👤 Buyer: <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
            f"👥 Seller: <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>\n\n"
            f"🔵 Deal Type: <b>{deal_type_display}</b>\n\n"
            f"⏰ <b>Select Timer Duration</b>\n"
            f"• How long should the deal remain active?\n"
            f"• After this time, a moderator will be automatically involved\n"
            f"• Choose based on your transaction complexity\n"
            f"• Default is 1 hour for quick deals\n\n"
            f"<i>Please select your preferred timer...</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif query.data.startswith("timer_"):
        if query.from_user.id != deal_data['buyer']:
            await query.answer("Only the buyer can select the timer", show_alert=True)
            return
        
        timer_value = query.data.split("_")[1]
        
        if timer_value == "default":
            timer_hours = 1
            timer_display = "1 Hour (Default)"
        else:
            timer_hours = int(timer_value)
            timer_display = f"{timer_hours} Hour{'s' if timer_hours > 1 else ''}"
        
        # Save timer to deal data
        deal_data["timer_hours"] = timer_hours
        update_active_deal(deal_id, {"timer_hours": timer_hours})
        
        buyer = await context.bot.get_chat(deal_data['buyer'])
        seller = await context.bot.get_chat(deal_data['seller'])
        deal_type_display = DEAL_TYPE_DISPLAY.get(query.data, query.data)
        
        keyboard = [
            [InlineKeyboardButton("❌ Cancel Deal", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        msg = await query.edit_message_text(
            f"<b>𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b>\n\n"
            f"👤 Buyer: <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
            f"👥 Seller: <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>\n\n"
            f"🔵 Deal Type: <b>{deal_type_display}</b>\n"
            f"⏰ Timer: <b>{timer_display}</b>\n\n"
            f"💰 <b>Enter Deposit Amount</b>\n"
            f"• Only numbers (e.g. 100 or 100.50)\n"
            f"• Minimum amount: $1\n"
            f"• Maximum amount: $100,000\n"
            f"• Admin fee will likely be included in transaction\n"
            f"• Your funds will be held safely until transaction is complete\n"
            f"• Auto-moderator involvement after {timer_display.lower()}\n\n"
            f"<i>Waiting for buyer to enter amount...</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )        
        context.user_data["state"] = "AMOUNT"  
        context.user_data["deal_type"] = deal_data['deal_type']
        context.user_data["prompt_message_id"] = msg.message_id
    elif query.data == "help":
        keyboard = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="help_en"),
             InlineKeyboardButton("Hindi 🇮🇳", callback_data="help_hi")],
            [InlineKeyboardButton("Back 🔙", callback_data="mainmenu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Select your preferred language for help:",
            reply_markup=reply_markup
        )
    elif query.data == "rollback":
        await handle_rollback(update, context)
    elif query.data == "cancel_form":
        context.user_data.clear()
        await query.message.delete()

    elif query.data.startswith("help_"):
        await handle_help_language(update, context)
    elif query.data == "reviews":
        await handle_reviews(update, context)
    elif query.data == "release_payment":
        await handle_release_payment(update, context)

    elif query.data.startswith("coin_"):
        await handle_coin_selection(update, context)

    elif query.data.startswith("confirm_form_"):
        deal_id = query.data.split("_")[2]
        deal_data = get_active_deal(deal_id)
        # Telethon admin check
        is_admin = await ensure_bot_admin_telethon(query.message.chat.id)
        if not is_admin:
            await query.answer("Bot is not an admin in this group or admin session is missing ❌", show_alert=True)
            return
        
        if not deal_data:
            await query.answer("Deal not found", show_alert=True)
            return
        
        if query.from_user.id not in [deal_data['buyer'], deal_data['seller']]:
            await query.answer("Only buyer and seller can confirm", show_alert=True)
            return
            
        if 'confirmations' not in deal_data:
            deal_data['confirmations'] = []
            
        if query.from_user.id in deal_data['confirmations']:
            await query.answer("You've already confirmed", show_alert=True)
            return
            
        deal_data['confirmations'].append(query.from_user.id)
        update_active_deal(deal_id, {'confirmations': deal_data['confirmations']})

        # Always show the agreement message after each user's confirmation
        buyer_name = deal_data.get('buyer_name', '')
        seller_name = deal_data.get('seller_name', '')
        timer_hours = deal_data.get('timer_hours', 1)
        terms = deal_data.get('terms_and_conditions', None)
        timer_display = f"{timer_hours} Hour{'s' if timer_hours != 1 else ''}"
        confirm_msg = (
            f"<b>𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b>\n\n"
            f"👤 Buyer: <a href='tg://user?id={deal_data['buyer']}'>{buyer_name}</a>\n"
            f"👥 Seller: <a href='tg://user?id={deal_data['seller']}'>{seller_name}</a>\n"
            f"🔵 Deal: {deal_data['deal_type']}\n"
            f"💰 Amount: ${deal_data['amount']:.2f}\n\n"
            f"⏰ Timer: {timer_display}\n\n"
        )
        if terms:
            confirm_msg += f"<b>📑 TERMS AND CONDITIONS</b>:\n<i>{terms}</i>\n\n"
        confirm_msg += "<i>Both buyer and seller must confirm to proceed</i>"

        if len(deal_data['confirmations']) == 1:
            other_user_id = deal_data['seller'] if query.from_user.id == deal_data['buyer'] else deal_data['buyer']
            other_user = await context.bot.get_chat(other_user_id)
            await query.message.reply_text(
                f"Waiting for <a href='tg://user?id={other_user_id}'>{other_user.first_name}</a> to confirm",
                parse_mode='HTML'
            )
           
        
        if len(deal_data['confirmations']) == 2:
            # Both confirmed, proceed to deposit
            invoice = await create_invoice(deal_data['amount'], deal_id)
            if invoice.get("message") == "Successful operation" and invoice.get("result") == 100:
                payment_url = invoice["payLink"]
                track_id = invoice["trackId"]
                
                keyboard = [
                    [InlineKeyboardButton("🔗 Pay Now", url=payment_url)],
                    [InlineKeyboardButton("❌ End Deal", callback_data="back")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                msg = await query.edit_message_text(
                    f"<b>ESCROW SERVICE</b>\n\n"
                    f"Please complete your payment of ${deal_data['amount']:.2f}\n\n"
                    f"Use the Payment Link Below 👇\n"
                    f"Track ID: <code>{track_id}</code>\n"
                    "<code>⚠ Do Not Reuse This Link</code>\n"
                    "<code>⚠ Buyer must pay exact amount as seen in Link</code>",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                # PIN payment message, and handle pin slot limitation
                pins = context.chat_data.get('pins', [])
                try:
                    await context.bot.pin_chat_message(update.effective_chat.id, msg.message_id)
                    pins.append(msg.message_id)
                    # Unpin oldest if more than 4
                    if len(pins) > 4:
                        to_unpin = pins.pop(0)
                        try:
                            await context.bot.unpin_chat_message(update.effective_chat.id, to_unpin)
                        except Exception: pass
                    context.chat_data['pins'] = pins
                except Exception: pass
        else:
            await query.answer("Confirmation received, waiting for other party", show_alert=True)


    elif query.data == "seller_confirm_paid":
        await handle_seller_confirm(update, context)
    elif query.data == "confirm_withdrawal":
        await handle_confirm_withdrawal(update, context)
    elif query.data == "edit_withdrawal":
        await handle_edit_withdrawal(update, context)
    elif query.data == "change_coin":
        await handle_change_coin(update, context)
    elif query.data == "change_address":
        await handle_change_address(update, context)
    elif query.data == "mainmenu":
        await handle_start(update, context)
    elif query.data == "mod":
        user_id = query.from_user.id
        context.user_data['awaiting_complaint'] = True
        context.user_data['complaint_message_id'] = query.message.message_id
        await query.answer()
        await query.message.reply_text("Please type your complaint message.")

    elif query.data.startswith("review_"):
        _, action, seller_id = query.data.split("_")
        active_deals = get_all_active_deals()
        deal_data = None
        for deal in active_deals.values():
            if deal['seller'] == int(seller_id):
                deal_data = deal
                break
        
        if query.from_user.id != deal_data['buyer']:
            await query.answer("Only the buyer can leave a review ❌", show_alert=True)
            return
        seller = await context.bot.get_chat(int(seller_id))
        buyer = await context.bot.get_chat(deal_data['buyer'])
        
        if action == "positive":
            review_system.add_review(int(seller_id), seller.first_name, True, deal_data['deal_type'],  buyer.id, buyer.first_name)
            await query.edit_message_text(
                f"✅ You rated {seller.first_name} positively!\n\n"
                "Thank you for your feedback."
            )
        elif action == "negative":
            review_system.add_review(int(seller_id), seller.first_name, False, deal_data['deal_type'],  buyer.id, buyer.first_name)
            await query.edit_message_text(
                f"❌ You rated {seller.first_name} negatively.\n\n"
                "Thank you for your feedback."
            )
    elif query.data == "back":
        query = update.callback_query
        message = query.message
        group_id = message.chat.id
        active_deals = get_all_active_deals()
        deal_id = None
        for d_id, deal in active_deals.items():
            if deal['group_id'] == group_id:
                deal_id = d_id
                break
        if deal_id:
            deal_data = get_active_deal(deal_id)
            if deal_data:
                if deal_data.get('status') in ['waiting', 'deposited']:
                    if str(query.from_user.id) == ADMIN_ID:
                        remove_active_deal(deal_id)
                        context.user_data.clear()
                        context.user_data["state"] = None
                        if 'buyer' in deal_data:
                            context.user_data.pop('buyer', None)
                        if 'seller' in deal_data:
                            context.user_data.pop('seller', None)
                        
                        user_link = f'<a href="tg://user?id={query.from_user.id}">{query.from_user.first_name}</a>'
                        await query.edit_message_text(f"Deal cancelled by Admin {user_link}.", parse_mode="html")
                    else:
                        await query.answer("Only Moderator can cancel deals at this stage ❌", show_alert=True)
                else:
                    if query.from_user.id == deal_data['starter'] or str(query.from_user.id) == ADMIN_ID:
                        remove_active_deal(deal_id)
                        context.user_data.clear()
                        context.user_data["state"] = None
                        if 'buyer' in deal_data:
                            context.user_data.pop('buyer', None)
                        if 'seller' in deal_data:
                            context.user_data.pop('seller', None)
                        
                        user_link = f'<a href="tg://user?id={query.from_user.id}">{query.from_user.first_name}</a>'
                        await query.edit_message_text(f"Deal cancelled by {user_link}.", parse_mode="html")
                    else:
                        await query.answer("You are not authorized to cancel this deal ❌", show_alert=True)
            else:
                await query.answer("No active deal found.", show_alert=True)


    elif query.data.startswith("refunds_"):
        await handle_refund_coin_selection(update, context)

    elif query.data == "check_timer":
        group_id = update.effective_chat.id
        active_deals = get_all_active_deals()
        deal_id = None
        for d_id, deal in active_deals.items():
            if deal['group_id'] == group_id:
                deal_id = d_id
                break
                
        if not deal_id:
            await query.answer("No active deal found", show_alert=True)
            return
            
        deal_data = get_active_deal(deal_id)
        
        # Get custom timer or default to 1 hour
        timer_hours = deal_data.get('timer_hours', 1)
        timer_minutes = timer_hours * 60
        
        remaining_time = get_remaining_time(deal_data.get('payment_time'), timer_minutes)
        
        buyer = await context.bot.get_chat(deal_data['buyer'])
        seller = await context.bot.get_chat(deal_data['seller'])
        
        amount = deal_data['amount']
        fee = calculate_fee(amount, deal_data['deal_type'])
        total = amount + fee
        
        keyboard = [  
            [InlineKeyboardButton("💰 Release Payment", callback_data="release_payment")],  
            [InlineKeyboardButton("⏳ Check Timer", callback_data="check_timer")],  
            [InlineKeyboardButton("👨‍💼 Involve Moderator", callback_data="mod")],  
            [InlineKeyboardButton("🚫 End Deal", callback_data="back")]  
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Display timer in hours and minutes format
        timer_display = f"{timer_hours} Hour{'s' if timer_hours > 1 else ''}"
        
        await query.edit_message_text(
            f"<b>PAYMENT CONFIRMED ✅</b>\n\n"
            f"💵 <b>Deposit Amount:</b> ${amount:.2f}\n"
            f"✅ <b>Payment confirmed by:</b> <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
            f"🔄 <b>Escrow Fee:</b> ${fee:.2f}\n"
            f"💰 <b>Total Amount:</b> ${total:.2f}\n\n"
            f"<b>⚠️ IMPORTANT INSTRUCTIONS:</b>\n"
            f"1. Ensure the transaction is fully completed before proceeding.\n"
            f"2. <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a> Verify that all items/services meet your expectations.\n"
            f"3. <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a> Only click 'Release Payment' if fully satisfied with the transaction.\n"
            f"4. If you encounter any issues, click 'Involve Moderator' immediately.\n\n"
            f"<b>🚫 Do NOT release payment before deal completion to avoid disputes.</b>\n"
            f"❗ All disputes or suspected scams will be investigated thoroughly.\n\n"
            f"<b>👥 Participants:</b>\n"
            f"🔹 <b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
            f"🔹 <b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>\n"
            f"<b>⏱ Selected Timer Duration: {timer_display}</b>\n"
            f"<b>⏱ Time Remaining to Complete Trade: {remaining_time}</b>\n"
            f"⚠️ <i>Please complete the trade before the timer expires, or a moderator will be involved automatically.</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    await query.answer()

def get_remaining_time(payment_time, timer_minutes=60):
    if not payment_time:
        return "00:00"
    payment_datetime = datetime.fromisoformat(payment_time)
    time_limit = payment_datetime + timedelta(minutes=timer_minutes)
    remaining = time_limit - datetime.now()
    
    if remaining.total_seconds() <= 0:
        return "00:00"
        
    total_minutes = int(remaining.total_seconds() // 60)
    seconds = int(remaining.total_seconds() % 60)
    
    # Format as HH:MM if over 60 minutes, otherwise MM:SS
    if total_minutes >= 60:
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}:00"
    else:
        return f"{total_minutes:02d}:{seconds:02d}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fix: Check for awaiting_terms instead of AWAITING_TOS state
    if context.user_data.get('awaiting_terms'):
        tos_prompt_id = context.user_data.get('tos_prompt_msg_id')
        if not tos_prompt_id:
            await update.message.reply_text("Unexpected error: Terms prompt missing. Start the process again.")
            context.user_data['awaiting_terms'] = False
            context.user_data.pop('state', None)
            return
        if not update.message.reply_to_message or update.message.reply_to_message.message_id != tos_prompt_id:
            return
        # User replied to correct prompt: process the form as TOS step
        await process_form(update, context)
        return

    # Ensure only reply to the last form in group is accepted as form input
    if context.user_data.get('awaiting_form'):
        form_prompt_id = context.user_data.get('form_prompt_msg_id') or context.chat_data.get('awaiting_form_id')
        if not update.message.reply_to_message or update.message.reply_to_message.message_id != form_prompt_id:
            # Ignore random messages (don't spam invalid), unless it looks like form (e.g., starts with Buyer:/Seller:/Deal:/Price:)
            suspicious_starts = ["buyer:", "seller:", "deal:", "price:"]
            if any(update.message.text.strip().lower().startswith(s) for s in suspicious_starts):
                await update.message.reply_text("To submit a deal form, please REPLY to the bot's form instruction message.")
            return

    # Remove the redundant AWAITING_TOS check since we handle it above
    if context.user_data.get("state") == "AMOUNT":
        if not update.message.reply_to_message or update.message.reply_to_message.message_id != context.user_data.get("prompt_message_id"):
            return
        try:
            prompt_message_id = context.user_data.get("prompt_message_id")
            if prompt_message_id:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=prompt_message_id
                )
            amount = float(update.message.text)
            if amount < 1 or amount > 100000:
                msg = await update.message.reply_text("Amount must be between $1 and $100,000")
                context.user_data["prompt_message_id"] = msg.message_id
                return
                
            group_id = update.effective_chat.id
            active_deals = get_all_active_deals()
            deal_id = None

            for d_id, deal in active_deals.items():
                if deal['group_id'] == group_id:
                    deal_id = d_id
                    deal_data = deal
                    break

            if not deal_id:
                await update.message.reply_text("No active deal found. Please start a new deal.")
                context.user_data.clear()
                context.user_data["state"] = None
                return
            deal_data = get_active_deal(deal_id)
            deal_type = context.user_data.get("deal_type")
            fee = calculate_fee(amount, deal_type)
            total = amount + fee
            invoice = await create_invoice(total, deal_id)
            if invoice.get("message") == "Successful operation" and invoice.get("result") == 100:
                payment_url = invoice["payLink"]
                track_id = invoice["trackId"]
                
                deal_data['amount'] = total
                update_active_deal(deal_id, {
                    'amount': amount,
                    'status': 'waiting'  
                })
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "🔗 Pay Now", url=payment_url
                        )
                    ],
                    [
                        InlineKeyboardButton("❌ End Deal", callback_data="back")
                    ],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                msg = await update.message.reply_text(
                    f"<b>𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b>\n\n"
                    f"Please complete your payment of ${total:.3f}\n\n"
                    f"Use the Payment Link Below 👇\n"
                    f"Track ID: <code>{track_id}</code>\n"
                    "<code>⚠ Do Not Reuse This Link</code>\n"
                    "<code>⚠Buyer must pay exact amount as seen in Link</code>",
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
                context.user_data["prompt_message_id"] = msg.message_id
            else:
                await update.message.reply_text("Error creating payment invoice. Please try again.")
            context.user_data.clear()
        except ValueError:
            keyboard = [[InlineKeyboardButton("❌", callback_data="cancel_form")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            msg = await update.message.reply_text("Please enter a valid number ⚠️",reply_markup='reply_markup', parse_mode='HTML')
            context.user_data["prompt_message_id"] = msg.message_id
    elif context.user_data.get("state") == "AWAITING_REFUND_WALLET":
        await handle_refund_address(update, context)
    elif context.user_data.get("state") == "AWAITING_WALLET":
        await handle_wallet_address(update, context)
    elif context.user_data.get('awaiting_complaint'):
        await handle_complaint(update, context)
    elif context.user_data.get("state") == "AWAITING_MEMO":
        await handle_memo_input(update, context)
    elif context.user_data.get('awaiting_code'):
        await handle_code(update, context)
    elif context.user_data.get('awaiting_password'):
        await handle_2fa_password(update, context)
    else:
        # Only process the form if this is a reply to the instruction
        if context.user_data.get('awaiting_form'):
            form_prompt_id = context.user_data.get('form_prompt_msg_id') or context.chat_data.get('awaiting_form_id')
            if not update.message.reply_to_message or update.message.reply_to_message.message_id != form_prompt_id:
                return  # ignore random messages
            await process_form(update, context)
            if not context.user_data.get('awaiting_form'):
                context.chat_data.pop('awaiting_form_id', None)
                context.user_data.pop('form_prompt_msg_id', None)
        else:
            await process_form(update, context)
async def handle_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    complaint_text = update.message.text
    group_id = update.effective_chat.id
    active_deals = get_all_active_deals()
    deal_id = None
    deal_data = None
    
    for d_id, deal in active_deals.items():
        if deal['group_id'] == group_id:
            deal_id = d_id
            deal_data = deal
            break

    if not deal_data:
        await update.message.reply_text("Error: No active deal found.")
        return

    if user_id not in [deal_data['buyer'], deal_data['seller']]:
        await update.message.reply_text("You are not authorized to submit a complaint for this deal.")
        return

    complaint_message_id = context.user_data.get('complaint_message_id')
    if not complaint_message_id:
        await update.message.reply_text("Error: Unable to locate the original message.")
        return
    
    prompt_message_id = context.user_data.get("prompt_message_id")
    if prompt_message_id:
        await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=prompt_message_id
                )

    message_link = f"https://t.me/c/{str(update.effective_chat.id)[4:]}/{complaint_message_id}"

    admin_message = (
        "╔══════════════════════╗\n"
        "║   ESCROW SERVICE \n"
        "╚══════════════════════╝\n\n"
        "*COMPLAINT REPORT ⚠*\n"
        "───────────────────\n\n"
        f"*Deal Information:*\n"
        f"• Deal ID: `{deal_id}`\n"
        f"• Transaction Amount: `${deal_data['amount']:.2f}`\n\n"
        f"*Complainant Details:*\n"
        f"• User ID: `{user_id}`\n"
        f"• Role: `{'Buyer' if user_id == deal_data['buyer'] else 'Seller'}`\n\n"
        f"*Complaint Statement:*\n"
        f"`{complaint_text}`\n\n"
        f"*Reference:*\n"
        f"• Original Message:\n `{message_link}`"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, parse_mode="Markdown")
        await update.message.reply_text("*Your complaint has been sent to the admin ✅*\n\n They will review it shortly.", parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending complaint to admin: {e}")
        await update.message.reply_text("There was an error submitting your complaint. Please try again")

    context.user_data.pop('awaiting_complaint', None)
    context.user_data.pop('complaint_message_id', None)

async def handle_p2pfee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        new_fee = float(context.args[0])
        if 1 <= new_fee <= 40:
            with open('config.json', 'r') as f:
                config = json.load(f)
            config['p2p_fee'] = new_fee
            with open('config.json', 'w') as f:
                json.dump(config, f, indent=2)
            await update.message.reply_text(f"P2P fee updated to {new_fee}%")
        else:
            await update.message.reply_text("Fee must be between 1 and 40%")
    except (IndexError, ValueError):
        await update.message.reply_text("Please provide a valid fee percentage")

async def handle_bsfee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        new_fee = float(context.args[0])
        if 1 <= new_fee <= 40:
            with open('config.json', 'r') as f:
                config = json.load(f)
            config['bs_fee'] = new_fee
            with open('config.json', 'w') as f:
                json.dump(config, f, indent=2)
            await update.message.reply_text(f"Buy & Sell fee updated to {new_fee}%")
        else:
            await update.message.reply_text("Fee must be between 1 and 40%")
    except (IndexError, ValueError):
        await update.message.reply_text("Please provide a valid fee percentage")

async def handle_setfee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        new_fee = float(context.args[0])
        if 1 <= new_fee <= 40:
            with open('config.json', 'r') as f:
                config = json.load(f)
            config['allfee'] = new_fee
            with open('config.json', 'w') as f:
                json.dump(config, f, indent=2)
            await update.message.reply_text(f"General fee updated to {new_fee}%")
        else:
            await update.message.reply_text("Fee must be between 1 and 40%")
    except (IndexError, ValueError):
        await update.message.reply_text("Please provide a valid fee percentage")


async def handle_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /trades command - sends the trades.txt file to admin"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        with open("trades.txt", "r") as f:
            trades = f.read()
        if not trades:
            await update.message.reply_text("No trades found.")
            return
        # Send the trades.txt file directly
        await update.message.reply_document(
            document=trades.encode(),
            filename="trades.txt",
            caption="Here are all the trades."
        )
    except FileNotFoundError:
        await update.message.reply_text("No trades found.")



async def handle_seller_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    message = query.message
    group_id = message.chat.id
    active_deals = get_all_active_deals()
    deal_id = None
    for d_id, deal in active_deals.items():
        if deal['group_id'] == group_id:
            deal_id = d_id
            break

    if not deal_id:
        await query.edit_message_text("No active deal found for this group.")
        return
    deal_data = get_active_deal(deal_id)

    if query.from_user.id != deal_data['seller']:
        await query.answer("Only the seller can confirm the payment ❌", show_alert=True)
        return

    deal_data['status'] = 'completed'
    update_active_deal(deal_id, {'status': 'completed'})

    save_trade(
        buyer=deal_data['buyer'],
        seller=deal_data['seller'],
        amount=deal_data['amount'],
        status='successful'
    )

    msg = await query.edit_message_text("Payment confirmed ✅\n\n The deal has been marked as successful.")
    # PIN paid message, and handle pin slot limitation
    pins = context.chat_data.get('pins', [])
    try:
        await context.bot.pin_chat_message(update.effective_chat.id, msg.message_id)
        pins.append(msg.message_id)
        # Unpin oldest if more than 4
        if len(pins) > 4:
            to_unpin = pins.pop(0)
            try:
                await context.bot.unpin_chat_message(update.effective_chat.id, to_unpin)
            except Exception: pass
        context.chat_data['pins'] = pins
    except Exception: pass
    keyboard = [
            [InlineKeyboardButton("👍", callback_data=f"review_positive_{deal_data['seller']}"),
             InlineKeyboardButton("👎", callback_data=f"review_negative_{deal_data['seller']}")]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
        
    seller = await context.bot.get_chat(deal_data['seller'])
    buyer = await context.bot.get_chat(deal_data['buyer'])

    feedback_text = (
        "🎉 <b>Deal Successfully Completed!</b>\n\n"
        f"Hey <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>,\n"
        f"How was your experience with <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>?\n\n"
        "Please leave your feedback below 👇"
    )

    await context.bot.send_message(
        chat_id=group_id,
        text=feedback_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    sticker_id = config.get('success_sticker_id')
    if sticker_id and sticker_id.lower() != 'nosticker':
        try:
            await context.bot.send_sticker(chat_id=query.message.chat_id, sticker=sticker_id)
        except Exception as e:
            print(f"Error sending sticker: {e}")

    await query.answer()

async def handle_setsticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if update.message.reply_to_message and update.message.reply_to_message.sticker:
        new_sticker_id = update.message.reply_to_message.sticker.file_id
        
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        config['success_sticker_id'] = new_sticker_id
        
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=2)
        
        await update.message.reply_text(f"Success sticker updated to: ```{new_sticker_id}```", parse_mode='Markdown')
    else:
        await update.message.reply_text("Please reply to a sticker with this command to set it as the success sticker.")


async def handle_killdeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    target_user = None
    group_id = update.effective_chat.id

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user.id
    
    elif context.args:
        if update.message.entities and len(update.message.entities) > 1:
            for entity in update.message.entities:
                if entity.type == 'text_mention':
                    target_user = entity.user.id
                    break
        
        if not target_user:
            user_input = context.args[0]
            
            if user_input.startswith('@'):
                try:
                    username = user_input.lstrip('@') 
                    chat_member = await context.bot.getChatMember(group_id, username)
                    target_user = chat_member.user.id
                except BadRequest:
                    await update.message.reply_text(f"❌ User {user_input} not found in this group.")
                    return
            
            # Handle direct user ID
            else:
                try:
                    target_user = int(user_input)
                except ValueError:
                    await update.message.reply_text("❌ Invalid input. Use @username, mention user, or use user ID.")
                    return
    else:
        await update.message.reply_text("ℹ️ Usage: Reply to user, /killdeal @username, or /killdeal user_id")
        return

    active_deals = get_all_active_deals()
    deal_to_kill = None

    # Find deal in this group for the target user
    for deal_id, deal_data in active_deals.items():
        if deal_data['group_id'] == group_id and (
            deal_data['buyer'] == target_user or 
            deal_data['seller'] == target_user or 
            deal_data.get('starter') == target_user
        ):
            deal_to_kill = deal_id
            break

    if deal_to_kill:
        deal_data = active_deals[deal_to_kill]
        
        try:
            notification_text = "⚠️ This deal has been forcefully ended by an admin.\n\n"
            
            if deal_data.get('buyer'):
                buyer = await context.bot.get_chat(deal_data['buyer'])
                notification_text += f"Buyer: {buyer.first_name}\n"
                context.user_data.clear()
                context.user_data["state"] = None
                context.user_data.pop('buyer', None)
                
                
            if deal_data.get('seller'):
                seller = await context.bot.get_chat(deal_data['seller'])
                notification_text += f"Seller: {seller.first_name}\n"
                context.user_data.clear()
                context.user_data["state"] = None
                context.user_data.pop('seller', None)
                


            if deal_data.get('amount'):
                notification_text += f"Amount: ${deal_data['amount']:.2f}\n"
                
            notification_text += "\nIf you have any questions, please contact support."
            
            remove_active_deal(deal_to_kill)
            await update.message.reply_text("Deal has been forcefully ended.")
            await context.bot.send_message(
                chat_id=group_id,
                text=notification_text,
                parse_mode='HTML'
            )
            
        except BadRequest as e:
            remove_active_deal(deal_to_kill)
            await update.message.reply_text("Deal terminated. Could not fetch all participant details.")
    else:
        await update.message.reply_text("No active deal found for this user in this group.")




async def handle_killall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return
        
    active_deals = get_all_active_deals()
    for deal_id, deal_data in active_deals.items():
        
        if 'buyer' in deal_data:
            context.user_data.clear()
            context.user_data["state"] = None
            context.user_data.pop('buyer', None)
            
       
        if 'seller' in deal_data:
            context.user_data.clear()
            context.user_data["state"] = None
            context.user_data.pop('seller', None)
            
        remove_active_deal(deal_id)
    
    await update.message.reply_text("✅ All active deals have been terminated and user contexts cleared.")

async def send_withdrawal_update_to_seller(bot, seller_id, status, amount, currency):
    
    
    status_messages = {
        "Processing": "Your withdrawal request has been received and is being processed.",
        "Confirming": "Your withdrawal is being confirmed on the blockchain.",
        "Complete": "Your withdrawal has been successfully processed and sent to your wallet.",
        "Expired": "Your withdrawal request has expired. Please contact support for assistance.",
        "Rejected": "Your withdrawal request has been rejected."
    }
    
    message = f"Withdrawal Update:\n\n"
    message += f"Status: {status}\n"
    message += f"Amount: {amount} {currency}\n\n"
    message += status_messages.get(status, "An update has been received for your withdrawal.")
    
    if status == "Complete":
        keyboard = [[InlineKeyboardButton("Completed ✅", callback_data="seller_confirm_paid")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await bot.send_message(chat_id=seller_id, text=message, reply_markup=reply_markup)
    else:
        await bot.send_message(chat_id=seller_id, text=message)



async def handle_getdeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("This command can only be used in a group.")
        return

    group_id = update.effective_chat.id
    active_deals = get_all_active_deals()
    deal_id = None
    
    for d_id, deal in active_deals.items():
        if deal['group_id'] == group_id:
            deal_id = d_id
            deal_data = deal
            break
    
    if not deal_id:
        await update.message.reply_text("No active deal found in this group.")
        return
    
    if deal_data['status'] == 'completed':
        remove_active_deal(deal_id)
        await update.message.reply_text("The deal in this group was completed ✅\n\n Removed from active deals.")
        return
    if deal_data['status'] == 'initiated':
        if deal_data['buyer'] and deal_data['seller']:
            buyer = await context.bot.get_chat(deal_data['buyer'])
            seller = await context.bot.get_chat(deal_data['seller'])
            keyboard = [
                [InlineKeyboardButton("P2P Trade", callback_data="p2p"),
                InlineKeyboardButton("Buy & Sell", callback_data="b_and_s")],
                [InlineKeyboardButton("Back", callback_data="back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"<b>𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘</b>\n\n"
                f"Buyer: <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
                f"Seller: <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>\n\n"
                f"𝗕𝘂𝘆𝗲𝗿, 𝗽𝗹𝗲𝗮𝘀𝗲 𝗰𝗵𝗼𝗼𝘀𝗲 𝘁𝗵𝗲 𝘁𝘆𝗽𝗲 𝗼𝗳 𝗱𝗲𝗮𝗹:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            with open('custom.json', 'r', encoding='utf-8') as f:
                custom = json.load(f)

            brand_name = custom.get("brand_name", "FLUXX")
            
            keyboard = [
                [InlineKeyboardButton("Buyer", callback_data="buyer"),
                 InlineKeyboardButton("Seller", callback_data="seller")],
                [InlineKeyboardButton("Back", callback_data="back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                format_text(f"{brand_name} ESCROW SERVICE\n\nPlease select your role:", "italic"),
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

    elif deal_data['status'] == 'deposited' and deal_data['buyer'] and deal_data['seller'] and deal_data['amount']:
        from handlers import calculate_fee
        amount = deal_data['amount']
        fee = calculate_fee(amount, deal_data['deal_type'])
        total = amount + fee
        buyer = await context.bot.get_chat(deal_data['buyer'])
        seller = await context.bot.get_chat(deal_data['seller'])

        keyboard = [  
                [InlineKeyboardButton("💰 Release Payment", callback_data="release_payment")],  
                [InlineKeyboardButton("⏳ Check Timer", callback_data="check_timer")],  
                [InlineKeyboardButton("👨‍💼 Involve Moderator", callback_data="mod")],  
                [InlineKeyboardButton("🚫 End Deal", callback_data="back")]  
            ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"<b>PAYMENT CONFIRMED ✅</b>\n\n"
            f"💵 Deposit Amount: ${amount:.2f}\n"
            f"✅ Payment confirmed from <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
            f"🔄 Escrow Fee: ${fee:.2f}\n"
            f"💰 Total: ${total:.2f}\n\n"
            f"⚠️ IMPORTANT INSTRUCTIONS:\n"
            f"1. Complete your deal/transaction first\n"
            f"2. Buyer MUST verify everything is correct\n"
            f"3. <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>, Only click 'Release Payment' after full satisfaction\n"
            f"4. If ANY issues arise, click 'Involve Moderator' immediately\n\n"
            f"🚫 <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>, DO NOT RELEASE PAYMENT BEFORE DEAL COMPLETION\n"
            f"❗️ Any disagreements or scam attempts will be investigated\n\n"
            f"👥 Participants:\n"
            f"Buyer: <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
            f"Seller: <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )




async def handle_help_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = query.data.split('_')[1]
    with open('custom.json', 'r', encoding='utf-8') as f:
        custom = json.load(f)
    brand_name = custom.get("brand_name", "FLUXX")
    keyboard = [[InlineKeyboardButton("Back 🏠", callback_data="mainmenu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    help_texts = {
        'en': f"""
🔰 *How to use {brand_name} Escrow:*

1️⃣ *Start a Deal:*
- Click "Start Deal"
- Enter deal amount
- Choose deal type

2️⃣ *For Buyers:*
- Send payment within time limit
- Verify received goods/services
- Release payment when satisfied

3️⃣ *For Sellers:*
- Wait for buyer's payment
- Deliver goods/services
- Receive payment after buyer confirms

⚠️ *Safety Tips:*
- Always verify transaction details
- Report Scam to Moderator
- Contact mod if issues arise
        """,
        'hi': f"""
🔰 *{brand_name} Escrow ka upyog kaise karein:*

1️⃣ *Deal shuru karein:*
- "Start Deal" par click karein
- Rashi darj karein
- Deal prakar chunen

2️⃣ *Kharidaron ke liye:*
- Samay seema mein bhugtaan karein
- Praapt samaan/sevayon ki jaanch karein
- Santusht hone par bhugtaan jari karein

3️⃣ *Vikretaon ke liye:*
- Kharidar ke bhugtaan ki pratiksha karein
- Samaan/sevayein deliver karein
- Kharidar ki pushti ke baad bhugtaan praapt karein

⚠️ *Suraksha tips:*
- Hamesha len-den vivaran satyapit karein
- Agar aapko scam ka ahsas ho, to moderator ko report karein
- Samasya hone par mod se sampark karein
        """
    }
    
    await query.edit_message_text(
        help_texts.get(lang, "Language not supported"),
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

import random

async def handle_getgroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return
    try:
        with open("groups.json", "rb") as f:
            await update.message.reply_document(
                document=f,
                filename="groups.json",
                caption="Here are all groups created with bot as admin"
            )
    except FileNotFoundError:
        await update.message.reply_text("No groups.json group log found yet.")
    except Exception as e:
        await update.message.reply_text(f"Could not send file: {e}")

# REMOVED handle_on function

async def handle_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
        
    global telethon_client, client_listening
    
    if telethon_client is not None and telethon_client.is_connected():
        await telethon_client.disconnect()
        telethon_client = None
    await update.message.reply_text("Persistent Telethon client stopped/disconnected.")
