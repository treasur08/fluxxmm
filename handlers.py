from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import json
import os
import asyncio
from telethon import TelegramClient
from telethon import functions, types
from telethon.tl.functions.messages import CreateChatRequest, ExportChatInviteRequest,  AddChatUserRequest, EditChatPhotoRequest
from telethon.tl.functions.channels import GetParticipantRequest, EditBannedRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import ChatAdminRights, ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.errors import UserNotParticipantError, ChatAdminRequiredError, ChannelPrivateError, UsernameNotOccupiedError, UserAdminInvalidError
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
from broadcast import *

telethon_client = None
client_listening = False

P2P_FORM_REGEX = re.compile(r"""
    ^Buyer:\s*(.+?)\n
    Seller:\s*(.+?)\n
    Amount\s*\[USDT\]:\s*\$?(\d+\.?\d*)\n
    Time:\s*(.+?)$
""", re.MULTILINE | re.VERBOSE | re.IGNORECASE)

PRODUCT_FORM_REGEX = re.compile(r"""
    ^Buyer:\s*(.+?)\n
    Seller:\s*(.+?)\n
    Amount\s*\[USDT\]:\s*\$?(\d+\.?\d*)\n
    Deal\s*details:\s*(.+?)\n
    Time:\s*(.+?)$
""", re.MULTILINE | re.VERBOSE | re.IGNORECASE)

async def start_telethon_client():
    import os
    global telethon_client
    session_file = "admin_session.session"
    if not os.path.exists(session_file):
        print("[Telethon] Admin has not logged in (session file missing).")
        return False
    if telethon_client is None:
        print("[Telethon] Creating new TelegramClient instance for admin_session.")
        telethon_client = TelegramClient("admin_session", API_ID, API_HASH)
        await telethon_client.connect()
        print("[Telethon] Admin Telethon client connected.")
    # Always check authorization after connect
    if not await telethon_client.is_user_authorized():
        print("[Telethon] Session not authorized. Disconnecting client and clearing global reference.")
        await telethon_client.disconnect()
        telethon_client = None
        return False
    print("[Telethon] Client is authorized and ready.")
    return True



def load_fees():
    with open('config.json', 'r') as f:
        config = json.load(f)
    return config['p2p_fee'], config['bs_fee'], config['allfee']

def load_fee_json():
        try:
            with open('fees.json', 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading fees.json: {e}")
            return []


fees_data = load_fee_json()

def calculate_fee(amount, deal_type, fee_payer='buyer', discount_percentage=0.0):
    settings = load_settings()
    free_limit = settings.get('free_limit', DEFAULT_FREE_LIMIT)
    
    if amount <= free_limit:
        return 0.0  # Free escrow
    
    p2p_fee, bs_fee, allfee = load_fees()
    fee_percentage = p2p_fee if deal_type == "p2p" else bs_fee if deal_type == "b_and_s" else allfee
    fee = amount * (fee_percentage / 100)
    
    if discount_percentage > 0:
        fee *= (1 - discount_percentage / 100)  # Apply discount
    
    if fee_payer == 'split':
        fee /= 2
    return round(fee, 2)
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
    if update.effective_user.id != ADMIN_ID:
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
    user_id = str(update.effective_user.id)
    users = load_users()
    if user_id not in users:
        users[user_id] = {'total_deals': 0, 'completed_deals': 0, 'referrer': None, 'balance': 0.0}
    
    # Check for referral
    if context.args and context.args[0].startswith('ref_'):
        ref_id = context.args[0].split('_')[1]
        if users[user_id]['referrer'] is None and ref_id != user_id:
            users[user_id]['referrer'] = ref_id
    save_users(users)

    # Load custom messages from custom.json
    with open('custom.json', 'r', encoding='utf-8') as f:
        custom_texts = json.load(f)
    
    welcome_text = (
        f"𝗪𝗲𝗹𝗰𝗼𝗺𝗲 𝘁𝗼 𝘁𝗵𝗲 {custom_texts['escrow_bot_name']}! 🤝\n"
        f"{custom_texts['start_message']}"
        f"{custom_texts['form_message']}"
        f"\n\n💰 Your Balance: <code>{users[user_id]['balance']}</code>\n"
        f"\n\n👤 Your ID: <code>{user_id}</code>\n"

    )
    group_text = (
        f"𝗪𝗲𝗹𝗰𝗼𝗺𝗲 𝘁𝗼 𝘁𝗵𝗲 {custom_texts['escrow_bot_name']}! 🤝\n"
        f"{custom_texts['form_message']}"
    )

    # Only add keyboards in private chats
    reply_markup = None
    if update.effective_chat.type == 'private':
        keyboard = [
            [InlineKeyboardButton("Help ⚠️", callback_data="help")],
            [InlineKeyboardButton("Contact Mod 📞", url=f"https://t.me/{ADMIN_USERNAME}")]
        ]
        if user_id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("Admin Balance 💲", callback_data="check_admin_balance")])
        reply_markup = InlineKeyboardMarkup(keyboard)

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
    else:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                group_text,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                group_text,
                parse_mode='HTML'
            )


# async def handle_form(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if update.effective_chat.type not in ['group', 'supergroup']:
#         await update.message.reply_text("This command can only be used in a group.")
#         return
#     # created = await start_telethon_client()
#     # if not created:
#     #     await update.message.reply_text("*Admin needs to login first ⚠*", parse_mode='Markdown')
#     #     return
    
#     is_admin = await ensure_bot_admin_telethon(update.effective_chat.id)
#     if not is_admin:
#         await update.message.reply_text("❌ Bot must be an admin in this group to perform this action.")
#         return
#     # Don't allow multiple awaiting forms in the same group
#     if context.chat_data.get('awaiting_form_id'):
#         await update.message.reply_text("A form is already being filled out in this group. Complete or cancel it before starting a new one.")
#         return
   
#     group_id = update.effective_chat.id
#     active_deals = get_all_active_deals()
#     deal_id = None
#     cur_deal = None
#     for d_id, deal in active_deals.items():
#         if deal.get('group_id') == group_id and deal.get('status') != 'completed':
#             deal_id = d_id
#             cur_deal = deal
#             break
#     if cur_deal:
#         kb = []
#         if update.effective_user.id == cur_deal.get('starter') or str(update.effective_user.id) == str(ADMIN_ID):
#             kb = [[InlineKeyboardButton("End Deal", callback_data="back")]]
#         reply_markup = InlineKeyboardMarkup(kb) if kb else None
#         msg = "*There is already an active deal in this group ❌\n\n You must end the current deal before starting a new one*"
#         await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
#         return
    
#     notified_flag = f"admin_notified_{update.effective_chat.id}"
#     groups_file = "groups.json"
#     group_entry = {
#         "group_id": update.effective_chat.id,
#         "title": update.effective_chat.title,
#     }
#     if not context.bot_data.get(notified_flag):
#         try:
#             try:
#                 invite_link = await context.bot.export_chat_invite_link(update.effective_chat.id)
#             except Exception:
#                 invite_link = "❌ Could not generate invite link"
#             group_entry["invite_link"] = invite_link
#             try:
#                 if os.path.exists(groups_file):
#                     with open(groups_file, "r") as f:
#                         all_groups = json.load(f)
#                 else:
#                     all_groups = []
#                 if not any(x.get("group_id") == update.effective_chat.id for x in all_groups):
#                     group_entry["logged_at"] = datetime.now().isoformat()
#                     all_groups.append(group_entry)
#                     with open(groups_file, "w") as f:
#                         json.dump(all_groups, f, indent=2)
#             except Exception as e:
#                 print(f"Failed to log group in groups.json: {e}")
#             # Send ADMIN message only once for this group
#             await context.bot.send_message(
#                 ADMIN_ID,
#                 f"📢 Bot is admin in group:\n\n <b>{update.effective_chat.title}</b>\n (ID: <code>{update.effective_chat.id}</code>)\n\n"
#                 f"Invite link:\n <code>{invite_link}</code>",
#                 parse_mode='HTML'
#             )
#             context.bot_data[notified_flag] = True
#         except Exception as e:
#             print(f"Failed to notify admin/log group: {e}")
#     # Mark group as having an awaiting form
#     context.user_data['awaiting_form'] = True
#     # Save the message id, so form replies must reply to this message
#     keyboard = [[InlineKeyboardButton("❌", callback_data="cancel_form")]]
#     reply_markup = InlineKeyboardMarkup(keyboard)
#     # Load custom messages from custom.json
#     with open('custom.json', 'r', encoding='utf-8') as f:
#         custom_texts = json.load(f)
    
#     msg = await update.message.reply_text(
#         custom_texts['form_message'],
#         parse_mode="HTML",
#         reply_markup=reply_markup
#     )
#     context.chat_data['awaiting_form_id'] = msg.message_id
#     context.user_data['form_prompt_msg_id'] = msg.message_id

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


async def process_form(update: Update, context: ContextTypes.DEFAULT_TYPE, match, deal_type):
    buyer_str, seller_str, amount_str, *extra = match.groups()
    amount = float(amount_str)
    time_str = extra[-1]  # Time is always last
    deal_details = extra[0] if deal_type == 'b_and_s' else None
    settings = load_settings()
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    
    if update.effective_chat.id not in settings.get('allowed_groups', []):
        await update.message.reply_text(
            f"*This group is not allowed for deals ❌*\nContact [admin](https://t.me/{ADMIN_USERNAME})",
            parse_mode="markdown",
            disable_web_page_preview=True
        )
        return
    group_id = update.effective_chat.id
    starter_id = update.effective_user.id
    starter_name = update.effective_user.first_name or update.effective_user.username
    # Check for existing active deal
    active_deals = get_all_active_deals()
    existing_deal_id = None
    for d_id, deal in active_deals.items():
        if deal['group_id'] == group_id and deal['status'] not in ['completed', 'cancelled']:
            existing_deal_id = d_id
            break
    
    if existing_deal_id:
        try:
            deal_data = get_active_deal(existing_deal_id)
            message_id = deal_data.get('message_id')
            await update.message.reply_text(
                f"There is already an active deal in this group. Please complete or cancel it first.\n"
                f"Current Deal: {existing_deal_id}",
                reply_to_message_id=message_id if message_id else None
            )
        except Exception as e:
            print(f"Error replying with existing deal: {e}")
            await update.message.reply_text("There is already an active deal in this group. Please complete or cancel it first.")
        return
    
    # Resolve buyer/seller to user IDs (assume mentions or text; use Telegram API to fetch)
    buyer = await resolve_user(context, buyer_str, update.effective_chat.id)
    if buyer == "TELETHON_NOT_CONNECTED":
        await update.message.reply_text("Admin needs to login ⚠")
        return
    if not buyer:
        await update.message.reply_text(f"Buyer {buyer_str} is not in the group or could not be resolved. Invite them first.")
        return
    
    seller = await resolve_user(context, seller_str, update.effective_chat.id)
    if seller == "TELETHON_NOT_CONNECTED":
        await update.message.reply_text("Admin needs to login ⚠")
        return
    if not seller:
        await update.message.reply_text(f"Seller {seller_str} is not in the group or could not be resolved. Invite them first.")
        return
    
    
    bot_username = f"@{BOT_USERNAME}"
    buyer_bio = ""
    seller_bio = ""
    try:
        buyer_profile = await context.bot.get_chat(buyer.id)
        buyer_bio = buyer_profile.bio or ""
    except Exception as e:
        print(f"[process_form] Error fetching buyer bio: {e}")
        # Fallback to Telethon
        if telethon_client and telethon_client.is_connected() and await telethon_client.is_user_authorized():
            try:
                buyer_entity = await telethon_client.get_entity(buyer.id)
                buyer_bio = buyer_entity.about or ""
            except Exception as e:
                print(f"[process_form] Telethon error fetching buyer bio: {e}")
    
    try:
        seller_profile = await context.bot.get_chat(seller.id)
        seller_bio = seller_profile.bio or ""
    except Exception as e:
        print(f"[process_form] Error fetching seller bio: {e}")
        # Fallback to Telethon
        if telethon_client and telethon_client.is_connected() and await telethon_client.is_user_authorized():
            try:
                seller_entity = await telethon_client.get_entity(seller.id)
                seller_bio = seller_entity.about or ""
            except Exception as e:
                print(f"[process_form] Telethon error fetching seller bio: {e}")
    
    # Determine discount
    both_bio_discount = settings.get('both_bio_discount', 50.0)  # Default 50%
    single_bio_discount = settings.get('single_bio_discount', 20.0)  # Default 20%
    buyer_has_bot = bot_username.lower() in buyer_bio.lower()
    seller_has_bot = bot_username.lower() in seller_bio.lower()
    discount_percentage = both_bio_discount if buyer_has_bot and seller_has_bot else single_bio_discount if buyer_has_bot or seller_has_bot else 0.0
    discount_text = ""
    if discount_percentage == both_bio_discount:
        discount_text = f"\n\n🎉 <b>50% escrow fee discount applied\n (both profiles include {bot_username})</b>"
    elif discount_percentage == single_bio_discount:
        discount_text = f"\n\n🎉 <b>20% escrow fee discount applied\n(one profile includes {bot_username})</b>"
    
    settings = load_settings()
    max_deal = settings.get('max_deal', DEFAULT_MAX_DEAL)
    if amount > max_deal:
        await update.message.reply_text(f"Deal amount ${amount} exceeds maximum allowed (${max_deal}). Contact admin to increase limit.")
        return
    if amount < 1:
        await update.message.reply_text(f"Deal amount ${amount} is less than $1")
        return
    
    # Parse time (e.g., "1 hour" -> 1)
    try:
        time_hours = parse_time(time_str)  # Implement below
    except:
        await update.message.reply_text("Invalid time format. Use e.g., '1 hour'.")
        return
    
    # Generate deal_id and init deal
    deal_id = generate_order_id()  # Your util
    deal_data = {
        'buyer': buyer.id,
        'seller': seller.id,
        'buyer_name': buyer.first_name or buyer.username or "Unknown",
        'seller_name': seller.first_name or seller.username or "Unknown",
        'starter': starter_id,
        'amount': amount,
        'deal_type': deal_type,
        'timer_hours': time_hours,
        'group_id': update.effective_chat.id,
        'status': 'initiated',
        'deal_details': deal_details,
        'created_at': datetime.now().isoformat(),
        'buyer_confirmed': False,  
        'seller_confirmed': False,
        'fee_payer': None,
        'pay_currency': None,
        'network': None,
        'track_id': None,
        'payment_status': None,
        'discount_percentage': discount_percentage
    }
    save_active_deal(deal_id, deal_data)  # Your util
    context.user_data['deal_id'] = deal_id  # For deposit
    buyer_link = f"<a href='tg://user?id={buyer.id}'>{deal_data['buyer_name']}</a>"
    seller_link = f"<a href='tg://user?id={seller.id}'>{deal_data['seller_name']}</a>"
    conf_text = (
        "✅ <b>NEW ESCROW DEAL STARTED</b>\n\n"
        f"👤 <b>Buyer:</b> {buyer_link}\n"
        f"👤 <b>Seller:</b> {seller_link}\n"
        f"💰 <b>Amount [USDT]: ${amount:.2f}</b>\n"
    )
    if deal_details:
        conf_text += f"📝 <b>Deal details:</b> {deal_details}\n"
    conf_text += f"⏱ Time: {time_str}\n\n"
    conf_text += "<b>Both must confirm this form below to proceed</b>"

    keyboard = [
        [
            InlineKeyboardButton("Buyer Confirm", callback_data=f"form_confirm_buyer_{deal_id}"),
            InlineKeyboardButton("Seller Confirm", callback_data=f"form_confirm_seller_{deal_id}")
        ],
        [InlineKeyboardButton("Back ❌", callback_data=f"form_cancel_{deal_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    sent_msg = await update.message.reply_text(conf_text, reply_markup=reply_markup, parse_mode='HTML')
    update_active_deal(deal_id, {'form_message_id': sent_msg.message_id})


    # # Log deal creation (basic; expand in Step 2)
    # print(f"Deal created: {deal_data}")
    # users = load_users()
    # seller_id = str(seller.id)
    # if seller_id not in users:
    #     users[seller_id] = {'total_deals': 0, 'completed_deals': 0, 'referrer': None, 'balance': 0.0}
    # users[seller_id]['total_deals'] += 1
    # save_users(users)
    # await log_deal_creation(context.bot, deal_data, deal_id)
    
    # # Prompt for fee payer confirmation
    # keyboard = [
    #     [InlineKeyboardButton("Buyer Pays Fee", callback_data=f"fee_buyer_{deal_id}")],
    #     [InlineKeyboardButton("Seller Pays Fee", callback_data=f"fee_seller_{deal_id}")],
    #     [InlineKeyboardButton("Split Fee", callback_data=f"fee_split_{deal_id}")]
    # ]
    # reply_markup = InlineKeyboardMarkup(keyboard)
    # buyer_link = f"<a href='tg://user?id={buyer.id}'>{deal_data['buyer_name']}</a>"
    # seller_link = f"<a href='tg://user?id={seller.id}'>{deal_data['seller_name']}</a>"
    # details_section = f"<b>Deal Details:</b> {deal_details}\n" if deal_details else ""
    # msg = (
    #     f"<b>✅ Deal Initiated</b>\n\n"
    #     f"<b>Buyer:</b> {buyer_link}\n"
    #     f"<b>Seller:</b> {seller_link}\n"
    #     f"<b>Amount:</b> <code>${amount}</code>\n"
    #     f"{details_section}"
    #     f"<b>Time:</b> <code>{time_hours} hour{'s' if time_hours != 1 else ''}</code>\n"
    #     f"{discount_text}\n\n"
    #     f"<b>Who will pay the escrow fee?</b>"
    # )
    # await update.message.reply_text(
    #     msg,
    #     reply_markup=reply_markup,
    #     parse_mode='HTML'
    # )

async def resolve_user(context, user_str, chat_id):
    """Resolve user_str (@username, ID, or name) to user object and verify group membership using Telethon."""
    global telethon_client
    
    # Check Telethon connection
    if telethon_client is None or not telethon_client.is_connected() or not await telethon_client.is_user_authorized():
        print(f"[resolve_user] Telethon not connected for {user_str}")
        return "TELETHON_NOT_CONNECTED"
    
    try:
        # Resolve entity
        if user_str.startswith('@'):
            username = user_str.lstrip('@')
            entity = await telethon_client.get_entity(username)
        elif user_str.isdigit():
            user_id = int(user_str)
            entity = await telethon_client.get_entity(user_id)
        else:
            # Fallback for name: search in group participants
            async for participant in telethon_client.iter_participants(chat_id):
                if (participant.first_name and user_str.lower() == participant.first_name.lower()) or \
                   (participant.username and user_str.lower() == participant.username.lower()):
                    return participant
            print(f"[resolve_user] No match for name {user_str} in group {chat_id}")
            return None
        
        user_id = entity.id
        # Verify group membership
        try:
            await telethon_client(GetParticipantRequest(channel=chat_id, participant=user_id))
            return entity
        except UserNotParticipantError:
            print(f"[resolve_user] {user_str} not in group {chat_id}")
            return None
        except Exception as e:
            print(f"[resolve_user] Telethon membership check error for {user_str}: {e}")
            return None
    except UsernameNotOccupiedError:
        print(f"[resolve_user] Username {user_str} not found")
        return None
    except Exception as e:
        print(f"[resolve_user] Telethon error resolving {user_str}: {e}")
        return None


async def resolve_username(update: Update, context, user_str):
    """Resolve @mention or username to user ID (Telegram API or Telethon fallback)."""
    try:
        chat = await context.bot.get_chat(user_str)
        return chat.id
    except:
        if telethon_client and telethon_client.is_connected():
            try:
                entity = await telethon_client.get_entity(user_str.lstrip('@'))
                return entity.id
            except UsernameNotOccupiedError:
                return None
            except Exception as e:
                print(f"Telethon error resolving {user_str}: {e}")
                return None
        else:
            await update.message.reply_text("Admin needs to login ⚠")
        return None
    
def parse_time(time_str):
    time_str = time_str.lower()
    if 'hour' in time_str:
        return int(re.search(r'\d+', time_str).group())
    elif 'min' in time_str:
        return int(re.search(r'\d+', time_str).group()) / 60
    raise ValueError("Invalid time")


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
        group_title = f"{brand_name} 𝙴S𝙲𝚁𝙾𝚄𝙿 {unique_id}"
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


async def proceed_to_fee_payer(bot, deal_id, deal_data, query=None):
    selector = 'seller' if deal_data['deal_type'] == 'p2p' else 'buyer'
    selector_name = deal_data[f'{selector}_name']
    selector_id = deal_data[selector]
    
    buyer_link = f"<a href='tg://user?id={deal_data['buyer']}'>{deal_data['buyer_name']}</a>"
    seller_link = f"<a href='tg://user?id={deal_data['seller']}'>{deal_data['seller_name']}</a>"
    details_section = f"<b>Deal Details:</b> {deal_data['deal_details']}\n" if deal_data.get('deal_details') else ""
    
    text = (
        "<b>BACK TO FEE PAYER SELECTION ✅</b>\n\n"
        f"<b>Buyer:</b> {buyer_link}\n"
        f"<b>Seller:</b> {seller_link}\n"
        f"<b>Amount:</b> <code>${deal_data['amount']:.2f}</code>\n"
        f"{details_section}"
        f"<b>Time:</b> <code>{deal_data['timer_hours']} hour{'s' if deal_data['timer_hours'] != 1 else ''}</code>\n\n"
        f"<b>{selector_name}, select who will pay the escrow fees:</b>"
    )
    keyboard = [
        [
            InlineKeyboardButton("Buyer Pays", callback_data=f"fee_buyer_{deal_id}"),
            InlineKeyboardButton("Seller Pays", callback_data=f"fee_seller_{deal_id}")
        ],
        [InlineKeyboardButton("Split", callback_data=f"fee_split_{deal_id}")],
        [InlineKeyboardButton("Cancel", callback_data=f"fee_cancel_{deal_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if query: 
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            update_active_deal(deal_id, {'fee_message_id': query.message.message_id})
            print(f"[DEBUG] Edited query message {query.message.message_id} for fee payer selection, deal {deal_id}")
        else:  # Called from form confirmation
            sent_msg = await bot.send_message(
                chat_id=deal_data['group_id'],
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            update_active_deal(deal_id, {'fee_message_id': sent_msg.message_id})
            print(f"[DEBUG] Sent fee payer selection message {sent_msg.message_id} for deal {deal_id}")
    except Exception as e:
        print(f"[DEBUG] Error in proceed_to_fee_payer for deal {deal_id}: {e}")
        # Fallback: Send new message
        try:
            sent_msg = await bot.send_message(
                chat_id=deal_data['group_id'],
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            update_active_deal(deal_id, {'fee_message_id': sent_msg.message_id})
            print(f"[DEBUG] Sent fallback fee payer selection message {sent_msg.message_id} for deal {deal_id}")
        except Exception as e:
            print(f"[DEBUG] Error sending fallback fee payer message for deal {deal_id}: {e}")



async def handle_form_confirmation(query, data, context):
    role = 'buyer' if 'buyer' in data else 'seller' if 'seller' in data else None
    if role:
        deal_id = data.split('_')[-1]
        deal_data = get_active_deal(deal_id)
        if not deal_data:
            await query.answer("Invalid or expired form.")
            return
        if query.from_user.id != deal_data[role]:
            await query.answer(f"Only the {role} can confirm this.", show_alert=True)
            return
        confirmed_key = f'{role}_confirmed'
        if confirmed_key not in deal_data:
            deal_data[confirmed_key] = False  # Safety: Initialize if missing
        if deal_data[confirmed_key]:
            await query.answer("You have already confirmed.")
            return
        # Update confirmation status
        deal_data[confirmed_key] = True
        print(f"[DEBUG] Setting {confirmed_key} to True for deal {deal_id}")
        update_active_deal(deal_id, deal_data)
        # Refresh deal_data to ensure latest state
        deal_data = get_active_deal(deal_id)
        print(f"[DEBUG] After update: buyer_confirmed={deal_data.get('buyer_confirmed', False)}, seller_confirmed={deal_data.get('seller_confirmed', False)}")
        # Update message to reflect current state
        form_msg_id = deal_data.get('form_message_id')
        if form_msg_id:
            await update_form_confirmation_message(context.bot, deal_data['group_id'], form_msg_id, deal_id, deal_data)
        else:
            # If missing, send a new message and save its id
            sent_msg = await context.bot.send_message(
                chat_id=deal_data['group_id'],
                text="Confirmation status updated.",
                parse_mode='HTML'
            )
            update_active_deal(deal_id, {'form_message_id': sent_msg.message_id})
            await update_form_confirmation_message(context.bot, deal_data['group_id'], sent_msg.message_id, deal_id, deal_data)
        # Check if both confirmed
        if deal_data.get('buyer_confirmed', False) and deal_data.get('seller_confirmed', False):
            print(f"[DEBUG] Both confirmed for deal {deal_id}, proceeding to fee confirmation")
            await proceed_to_fee_confirmation(context.bot, deal_id, deal_data, context)
        else:
            await query.answer(f"{role.capitalize()} confirmed! Waiting for the other party.")
    elif data.startswith('form_cancel_'):
        deal_id = data.split('_')[-1]
        deal_data = get_active_deal(deal_id)
        if not deal_data:
            await query.answer("Invalid deal.")
            return
        if query.from_user.id != deal_data['starter']:
            await query.answer("You cannot cancel this form.", show_alert=True)
            return
        try:
            await query.message.delete()
        except:
            pass
        remove_active_deal(deal_id)
        await query.answer("Form cancelled.")

  
async def update_form_confirmation_message(bot, group_id, msg_id, deal_id, deal_data):
    text = (
        "✅ <b>NEW ESCROW DEAL STARTED</b>\n\n"
        f"👤 <b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{deal_data['buyer_name']}</a>\n"
        f"👤 <b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{deal_data['seller_name']}</a>\n"
        f"💰 <b>Amount [USDT]:</b> ${deal_data['amount']:.2f}\n"
    )
    if deal_data.get('deal_details'):
        text += f"📝 <b>Deal Details:</b> {deal_data['deal_details']}\n"
    text += f"⏱ <b>Time:</b> {deal_data['timer_hours']} hour{'s' if deal_data['timer_hours'] > 1 else ''}\n\n"
    text += f"<b>Buyer Confirmed:</b> {'✅' if deal_data['buyer_confirmed'] else '❌'}\n"
    text += f"<b>Seller Confirmed:</b> {'✅' if deal_data['seller_confirmed'] else '❌'}\n"
    
    # Only show "Waiting for confirmations" if not both confirmed
    if not (deal_data['buyer_confirmed'] and deal_data['seller_confirmed']):
        text += "\n<b>Waiting for confirmations...</b>"

    buyer_btn_text = "Buyer Confirmed ✅" if deal_data['buyer_confirmed'] else "Buyer Confirm"
    buyer_cd = f"form_confirm_buyer_{deal_id}" if not deal_data['buyer_confirmed'] else "dummy"
    seller_btn_text = "Seller Confirmed ✅" if deal_data['seller_confirmed'] else "Seller Confirm"
    seller_cd = f"form_confirm_seller_{deal_id}" if not deal_data['seller_confirmed'] else "dummy"

    # Only include Back button if not both confirmed
    keyboard = [
        [InlineKeyboardButton(buyer_btn_text, callback_data=buyer_cd)],
        [InlineKeyboardButton(seller_btn_text, callback_data=seller_cd)]
    ]
    if not (deal_data['buyer_confirmed'] and deal_data['seller_confirmed']):
        keyboard.append([InlineKeyboardButton("Back ❌", callback_data=f"form_cancel_{deal_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await bot.edit_message_text(
            chat_id=group_id,
            message_id=msg_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        print(f"[DEBUG] Successfully updated message {msg_id} for deal {deal_id}")
        # Pin the message if both confirmed
        if deal_data['buyer_confirmed'] and deal_data['seller_confirmed']:
            try:
                await bot.pin_chat_message(chat_id=group_id, message_id=msg_id, disable_notification=True)
                print(f"[DEBUG] Pinned message {msg_id} for deal {deal_id}")
            except Exception as e:
                print(f"[DEBUG] Error pinning message {msg_id} for deal {deal_id}: {e}")
    except Exception as e:
        print(f"[DEBUG] Error updating message {msg_id} for deal {deal_id}: {e}")
        # Fallback: Send new message
        try:
            sent_msg = await bot.send_message(
                chat_id=group_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            update_active_deal(deal_id, {'form_message_id': sent_msg.message_id})
            print(f"[DEBUG] Sent new message {sent_msg.message_id} for deal {deal_id}")
            # Pin the new message if both confirmed
            if deal_data['buyer_confirmed'] and deal_data['seller_confirmed']:
                try:
                    await bot.pin_chat_message(chat_id=group_id, message_id=sent_msg.message_id, disable_notification=True)
                    print(f"[DEBUG] Pinned new message {sent_msg.message_id} for deal {deal_id}")
                except Exception as e:
                    print(f"[DEBUG] Error pinning new message {sent_msg.message_id} for deal {deal_id}: {e}")
        except Exception as e:
            print(f"[DEBUG] Error sending new message for deal {deal_id}: {e}")

async def proceed_to_fee_confirmation(bot, deal_id, deal_data, context: ContextTypes.DEFAULT_TYPE):
    """Send fee confirmation message and update deal/user data."""
    # Validate deal_data
    required_fields = ['buyer', 'seller', 'buyer_name', 'seller_name', 'amount', 'timer_hours', 'group_id']
    if not all(field in deal_data for field in required_fields):
        print(f"[DEBUG] Missing fields in deal_data for deal {deal_id}: {deal_data}")
        try:
            await bot.send_message(
                chat_id=deal_data.get('group_id', ADMIN_ID),
                text="❌ Error: Invalid deal data. Please contact support."
            )
        except Exception as e:
            print(f"[DEBUG] Failed to send error message for deal {deal_id}: {e}")
        return

    try:
        buyer_link = f"<a href='tg://user?id={deal_data['buyer']}'>{deal_data['buyer_name']}</a>"
        seller_link = f"<a href='tg://user?id={deal_data['seller']}'>{deal_data['seller_name']}</a>"
        details_section = f"<b>Deal Details:</b> {deal_data['deal_details']}\n" if deal_data.get('deal_details') else ""
        text = (
            "<b>Form confirmed by both parties ✅</b>\n\n"
            f"<b>Buyer:</b> {buyer_link}\n"
            f"<b>Seller:</b> {seller_link}\n"
            f"<b>Amount:</b> <code>${deal_data['amount']:.2f}</code>\n"
            f"{details_section}"
            f"<b>Time:</b> <code>{deal_data['timer_hours']} hour{'s' if deal_data['timer_hours'] != 1 else ''}</code>\n\n"
            "<b>Now, select who will pay the escrow fees:</b>"
        )
        keyboard = [
            [
                InlineKeyboardButton("Buyer Pays", callback_data=f"fee_buyer_{deal_id}"),
                InlineKeyboardButton("Seller Pays", callback_data=f"fee_seller_{deal_id}")
            ],
            [InlineKeyboardButton("Split", callback_data=f"fee_split_{deal_id}")],
            [InlineKeyboardButton("Cancel", callback_data=f"fee_cancel_{deal_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        sent_msg = await bot.send_message(
            chat_id=deal_data['group_id'],
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        update_active_deal(deal_id, {'fee_message_id': sent_msg.message_id, 'status': 'fee_pending'})

        users = load_users()
        buyer_id = str(deal_data['buyer'])
        seller_id = str(deal_data['seller'])

        # Ensure both buyer and seller exist in users
        if buyer_id not in users:
            users[buyer_id] = {'total_deals': 0, 'completed_deals': 0, 'referrer': None, 'balance': 0.0, 'total_wagered': 0.0}
        if seller_id not in users:
            users[seller_id] = {'total_deals': 0, 'completed_deals': 0, 'referrer': None, 'balance': 0.0, 'total_wagered': 0.0}

        # Increment total_deals for both
        users[buyer_id]['total_deals'] += 1
        users[seller_id]['total_deals'] += 1

        save_users(users)
        await log_deal_creation(context.bot, deal_data, deal_id)
    except Exception as e:
        print(f"[DEBUG] Error in proceed_to_fee_confirmation for deal {deal_id}: {e}")
        try:
            await bot.send_message(
                chat_id=deal_data.get('group_id', ADMIN_ID),
                text=f"❌ Error processing fee confirmation for deal {deal_id}: {e}"
            )
        except Exception as err:
            print(f"[DEBUG] Failed to send error message for deal {deal_id}: {err}")


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
     
    
    group_id = update.effective_chat.id
    message_text = update.message.text.strip() if update.message.text else ""
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    text = message.text or ""
    # Check for existing active deal in group
    active_deals = get_all_active_deals()
    existing_deal_id = None
    for d_id, deal in active_deals.items():
        if deal['group_id'] == group_id and deal['status'] not in ['completed', 'cancelled']:
            existing_deal_id = d_id
            break
    
    

    # Detect P2P form
    p2p_match = P2P_FORM_REGEX.match(message_text)
    if p2p_match:
        if existing_deal_id:
            try:
                deal_data = get_active_deal(existing_deal_id)
                message_id = deal_data.get('message_id')
                await update.message.reply_text(
                    f"There is already an active deal in this group. Please complete or cancel it first.\n"
                    f"Current Deal: {existing_deal_id}",
                    reply_to_message_id=message_id if message_id else None
                )
            except Exception as e:
                print(f"Error replying with existing deal: {e}")
                await update.message.reply_text("There is already an active deal in this group. Please complete or cancel it first.")
            return
        await process_form(update, context, p2p_match, deal_type='p2p')
        return
    
    # Detect Product form
    product_match = PRODUCT_FORM_REGEX.match(message_text)
    if product_match:
        if existing_deal_id:
            try:
                deal_data = get_active_deal(existing_deal_id)
                message_id = deal_data.get('message_id')
                await update.message.reply_text(
                    f"There is already an active deal in this group. Please complete or cancel it first.\n"
                    f"Current Deal: {existing_deal_id}",
                    reply_to_message_id=message_id if message_id else None
                )
            except Exception as e:
                print(f"Error replying with existing deal: {e}")
                await update.message.reply_text("There is already an active deal in this group. Please complete or cancel it first.")
            return
        await process_form(update, context, product_match, deal_type='b_and_s')
        return
    
    if message_text.lower().startswith('buyer:'):
        lines = message_text.split('\n')
        expected_p2p = 4  # Buyer, Seller, Amount, Time
        expected_product = 5  # Buyer, Seller, Amount, Deal details, Time
        error_msg = "Invalid deal form. Please check the format:\n\n"
        
        if len(lines) == expected_p2p:
            error_msg += (
                "<b>P2P Form (expected):</b>\n"
                "<code>Buyer: @username\nSeller: @username\nAmount [USDT]: $amount\nTime: duration</code>\n\n"
                "Issue: Ensure 'Amount [USDT]' is a number (e.g., $100 or 100) and all fields are correct."
            )
        elif len(lines) == expected_product:
            error_msg += (
                "<b>Product Form (expected):</b>\n"
                "<code>Buyer: @username\nSeller: @username\nAmount [USDT]: $amount\nDeal details: description\nTime: duration</code>\n\n"
                "Issue: Ensure 'Amount [USDT]' is a number (e.g., $100 or 100) and all fields are correct."
            )
        else:
            error_msg += (
                "<b>P2P Form:</b>\n"
                "<code>Buyer: @username\nSeller: @username\nAmount [USDT]: $amount\nTime: duration</code>\n\n"
                "<b>Product Form:</b>\n"
                "<code>Buyer: @username\nSeller: @username\nAmount [USDT]: $amount\nDeal details: description\nTime: duration</code>\n\n"
                "Issue: Incorrect number of fields or formatting."
            )
        
        await update.message.reply_text(error_msg, parse_mode='HTML')
        return
   
    elif chat.type == 'private' and str(user.id) == str(ADMIN_ID) and context.user_data.get('broadcast_state') == 'awaiting_content':
        await handle_broadcast_content(update, context)
        return
    
    if context.user_data.get("state") == "AWAITING_RELEASE_ADDRESS":
            if not message.reply_to_message or message.reply_to_message.message_id != context.user_data.get('prompt_message_id'):
                return

            address = message.text.strip()
            if not address:
                await message.reply_text("❌ Invalid address. Please reply with a valid address.")
                return

            deal_id = context.user_data['deal_id']
            deal_data = get_active_deal(deal_id)
            coin = context.user_data['coin']
            network = context.user_data['network']

            needs_memo = (coin == 'TON' or (coin == 'USDT' and network == 'Toncoin(TON)'))
            
            context.user_data['address'] = address
            if needs_memo:
                context.user_data['state'] = "AWAITING_RELEASE_MEMO"
                keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="back")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                prompt_msg = await message.reply_text(
                    "Please reply with memo (or type 'skip' if none):",
                    reply_markup=reply_markup
                )
                context.user_data['prompt_message_id'] = prompt_msg.message_id
            else:
                await show_release_confirmation(update, context, deal_data, coin, network, address)
            
    elif context.user_data.get("state") == "AWAITING_RELEASE_MEMO":
            if not message.reply_to_message or message.reply_to_message.message_id != context.user_data.get('prompt_message_id'):
                return
            memo = message.text.strip().lower()
            if memo == 'skip':
                memo = None

            deal_id = context.user_data['deal_id']
            deal_data = get_active_deal(deal_id)
            coin = context.user_data['coin']
            network = context.user_data['network']
            address = context.user_data['address']

            await show_release_confirmation(update, context, deal_data, coin, network, address, memo)

    
    elif context.user_data.get("state") == "AWAITING_REFUND_WALLET":
        await handle_refund_address(update, context)
   
    elif context.user_data.get('awaiting_complaint'):
        await handle_complaint(update, context)
  
    elif context.user_data.get('awaiting_code'):
        await handle_code(update, context)
    elif context.user_data.get('awaiting_password'):
        await handle_2fa_password(update, context)
    else:
        print("no message received.")# Only process the form if this is a reply to the instruction
        return  # No match, will notify user
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

    users = load_users()
    seller_id = str(deal_data['seller'])
    if seller_id in users:
        users[seller_id]['completed_deals'] += 1
    
    # Calculate fee (if >0)
    fee = calculate_fee(deal_data['amount'], deal_data['deal_type'], deal_data['fee_payer'])
    if fee > 0:
        # Add to admin_balance
        settings = load_settings()
        settings['admin_balance'] = settings.get('admin_balance', 0.0) + fee
        save_settings(settings)
        
        # If referrer, add share to referrer balance
        if seller_id in users and users[seller_id]['referrer']:
            referrer_id = users[seller_id]['referrer']
            refer_percent = settings.get('refer_percent', DEFAULT_REFER_PERCENT)
            referrer_share = fee * (refer_percent / 100)
            if referrer_id in users:
                users[referrer_id]['balance'] += referrer_share
        save_users(users)
    
    # Update global stats and log
    stats = load_stats()
    stats['total_escrows'] += 1
    stats['total_worth'] += deal_data['amount']
    save_stats(stats)
    await log_deal_completion(context.bot, deal_data, deal_id)
    
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
        f"Hey <a href='tg://user?id={buyer.id}'>{buyer.first_name}</a>,\n"
        f"How was your experience with <a href='tg://user?id={seller.id}'>{seller.first_name}</a>?\n\n"
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

async def handle_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /close {deal_id or user_id or @mention}")
        return
    
    arg = context.args[0]
    target_user = None
    deal_id = None

    # Check if arg is a deal_id
    if get_active_deal(arg):
        deal_id = arg
        await handle_killdeal(update, context)  # Reuse killdeal logic
        return
    
    # Not a deal_id, try resolving as user_id or @mention
    if arg.startswith('@'):
        # Check Telethon login for username resolution
        
        target_user = await resolve_username(update, context, arg)
        if not target_user:
            await update.message.reply_text(f"❌ User {arg} not found.")
            return
    elif update.message.entities and any(e.type == 'text_mention' for e in update.message.entities):
        for entity in update.message.entities:
            if entity.type == 'text_mention':
                target_user = entity.user.id
                break
    else:
        # Handle direct user ID
        try:
            target_user = int(arg)
        except ValueError:
            await update.message.reply_text("❌ Invalid input. Use deal_id, @username, mention user, or user ID.")
            return
    
    # Find deals involving user (buyer or seller)
    active_deals = get_all_active_deals()
    user_deals = [d_id for d_id, deal in active_deals.items() if deal['buyer'] == target_user or deal['seller'] == target_user]
    
    if not user_deals:
        await update.message.reply_text("No active deals found for this user.")
        return
    elif len(user_deals) == 1:
        context.args = [user_deals[0]]  # Set for handle_killdeal
        await handle_killdeal(update, context)
    else:
        deal_list = "\n".join([f"- {d_id}" for d_id in user_deals])
        await update.message.reply_text(f"Multiple deals found for user. Specify deal_id:\n{deal_list}")

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
        await update.message.reply_text("ℹ️ Usage: Reply to user, /enddeal @username, or /killdeal user_id")
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
    """Handle /getdeal command to show active deal status in a group."""
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("Only admin can use this command.")
        return
    
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("This command can only be used in a group.")
        return

    group_id = update.effective_chat.id
    active_deals = get_all_active_deals()
    deal_id = None
    deal_data = None
    
    for d_id, deal in active_deals.items():
        if deal['group_id'] == group_id:
            deal_id = d_id
            deal_data = deal
            break
    
    if not deal_id:
        await update.message.reply_text("No active deal found in this group.")
        return
    
    # Validate required fields
    required_fields = ['buyer', 'seller', 'buyer_name', 'seller_name', 'amount', 'timer_hours', 'deal_type']
    if not all(field in deal_data for field in required_fields):
        print(f"[DEBUG] Missing fields in deal_data for deal {deal_id}: {deal_data}")
        await update.message.reply_text(f"❌ Error: Invalid deal data for deal {deal_id}. Please contact support.")
        return

    try:
        buyer = await context.bot.get_chat(deal_data['buyer'])
        seller = await context.bot.get_chat(deal_data['seller'])
        buyer_name = buyer.first_name or deal_data['buyer_name']
        seller_name = seller.first_name or deal_data['seller_name']

        if deal_data['status'] == 'completed':
            remove_active_deal(deal_id)
            await update.message.reply_text(
                f"<b>✅ Deal {deal_id} Completed</b>\n\nRemoved from active deals.",
                parse_mode='HTML'
            )
            return

        
        elif deal_data['status'] == 'deposited':
            amount = deal_data['amount']
            fee = calculate_fee(amount, deal_data['deal_type'], deal_data.get('fee_payer', 'buyer'))
            total = amount + fee
            timer_hours = deal_data['timer_hours']
            remaining_time = get_remaining_time(deal_data.get('payment_time'), timer_hours * 60)  # Remove await
            deal_type_display = DEAL_TYPE_DISPLAY.get(deal_data['deal_type'], deal_data['deal_type'])
            fee_payer = deal_data.get('fee_payer', 'buyer').capitalize()
            
            details_section = f"<b>Deal Details:</b> {deal_data['deal_details']}\n" if deal_data.get('deal_details') else ""
            if deal_data['deal_type'] == 'p2p':
                instructions = (
                    "👤 <b>Buyer:</b> Send INR on time.\n"
                    "👤 <b>Seller:</b> Release payment only after receiving INR."
                )
            else:  # product
                instructions = (
                    "👤 <b>Buyer:</b> Release payment only after receiving product/service.\n"
                    "👤 <b>Seller:</b> Deliver promptly; wait for buyer confirmation."
                )

            keyboard = [
                [InlineKeyboardButton("💰 Release Payment", callback_data=f"release_payment_{deal_id}")],
                [InlineKeyboardButton("⏳ Check Timer", callback_data=f"check_timer_{deal_id}")],
                [InlineKeyboardButton("👨‍💼 Involve Moderator", callback_data=f"mod_{deal_id}")],
                [InlineKeyboardButton("🚫 End Deal", callback_data=f"form_cancel_{deal_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"<b>✅ PAYMENT CONFIRMED</b>\n\n"
                f"<b>Deal ID:</b> <code>{deal_id}</code>\n"
                f"<b>Type:</b> {deal_type_display}\n"
                f"<b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{buyer_name}</a>\n"
                f"<b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{seller_name}</a>\n"
                f"{details_section}"
                f"<b>Amount:</b> <code>${amount:.2f}</code>\n"
                f"<b>Fee (Paid by {fee_payer}):</b> <code>${fee:.2f}</code>\n"
                f"<b>Total:</b> <code>${total:.2f}</code>\n"
                f"<b>Time Remaining:</b> <code>{remaining_time}</code>\n\n",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                f"<b>📋 Deal Status</b>\n\n"
                f"Deal ID: <code>{deal_id}</code>\n"
                f"Status: {deal_data['status'].capitalize()}\n"
                f"Please wait for the next step or contact support.",
                parse_mode='HTML'
            )
    except Exception as e:
        print(f"[DEBUG] Error in handle_getdeal for deal {deal_id}: {e}")
        await update.message.reply_text(
            f"❌ Error retrieving deal {deal_id}: {e}",
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

async def handle_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global telethon_client
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
    # If client already running/connected:
    if telethon_client is not None and telethon_client.is_connected():
        await update.message.reply_text("Telethon client is already ON and connected.")
        return
    # Check for session file
    session_file = "admin_session.session"
    if not os.path.exists(session_file):
        await update.message.reply_text("Cannot start persistent Telethon client. Admin has not logged in (session missing). Use /login to login first.")
        return
    try:
        started = await start_telethon_client()
        if started:
            await update.message.reply_text("Persistent Telethon client started and connected.")
        else:
            await update.message.reply_text("Failed to start Telethon client. Session may be invalid or not authorized. Use /login again.")
    except Exception as e:
        await update.message.reply_text(f"Error starting Telethon client: {str(e)}")

async def handle_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
        
    global telethon_client, client_listening
    
    if telethon_client is not None and telethon_client.is_connected():
        await telethon_client.disconnect()
        telethon_client = None
    await update.message.reply_text("Persistent Telethon client stopped/disconnected.")


async def log_deal_creation(bot, deal_data, deal_id):
    settings = load_settings()
    log_channel = settings.get('log_channel')
    if not log_channel:
        return  # Skip if not set

    timestamp = datetime.fromisoformat(deal_data['created_at']).strftime('%Y-%m-%d %H:%M:%S')
    deal_desc = deal_data.get('deal_details', 'P2P Transfer') if deal_data['deal_type'] == 'b_and_s' else 'P2P Transfer'

    log_text = (
        "╔═════════════════╗\n"
        "║   <b>🚀 New Escrow Deal Created!</b> \n"
        "╚═════════════════╝\n\n"
        f"👤 <b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{deal_data['buyer_name']}</a>\n"
        f"👤 <b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{deal_data['seller_name']}</a>\n"
        f"📄 <b>Deal:</b> <code>{deal_desc}</code>\n"
        f"💰 <b>Amount:</b> <code>${deal_data['amount']:.2f}</code>\n"
        f"⏱ <b>Timer:</b> <code>{deal_data['timer_hours']} hours</code>\n"
        f"🆔 <b>Deal ID:</b> <code>{deal_id}</code>\n"
        f"🕒 <b>Timestamp:</b> <code>{timestamp}</code>\n"
    )

    try:
        await bot.send_message(chat_id=log_channel, text=log_text, parse_mode='HTML')
    except Exception as e:
        print(f"Error logging to channel {log_channel}: {e}")

async def log_deal_completion(bot, deal_data, deal_id):
    settings = load_settings()
    log_channel = settings.get('log_channel')
    if not log_channel:
        return
    
    stats = load_stats()
    stats['total_escrows'] += 1
    stats['total_worth'] += deal_data['amount']
    save_stats(stats)
    
    buyer_masked = f"{deal_data['buyer_name'][0]}****{deal_data['buyer_name'][-1]}" if len(deal_data['buyer_name']) > 1 else deal_data['buyer_name']
    seller_masked = f"{deal_data['seller_name'][0]}****{deal_data['seller_name'][-1]}" if len(deal_data['seller_name']) > 1 else deal_data['seller_name']
    
    log_text = (
        f"✅ Escrow Deal-Done!\n"
        f"➥ ID - {deal_id}\n"
        f"➥ Buyer - {buyer_masked}\n"
        f"➥ Seller - {seller_masked}\n"
        f"➥ Amount - ${deal_data['amount']:.2f}\n"
        f"➥ Total Worth - ${stats['total_worth']:.2f}\n"
        f"➥ Total Escrows - {stats['total_escrows']}"
    )
    
    try:
        await bot.send_message(chat_id=log_channel, text=log_text)
    except Exception as e:
        print(f"Error logging to channel {log_channel}: {e}")

# Add admin command handlers
async def handle_setmaxdeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setmaxdeal {amount}")
        return
    try:
        amount = float(context.args[0])
        settings = load_settings()
        settings['max_deal'] = amount
        save_settings(settings)
        await update.message.reply_text(f"Max deal amount set to ${amount}.")
    except ValueError:
        await update.message.reply_text("Invalid amount.")

async def handle_setfreelimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setfreelimit {amount}")
        return
    try:
        amount = float(context.args[0])
        settings = load_settings()
        settings['free_limit'] = amount
        save_settings(settings)
        await update.message.reply_text(f"Free escrow limit set to ${amount} (deals <= this are free).")
    except ValueError:
        await update.message.reply_text("Invalid amount.")

async def handle_setlogchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setlogchannel {channel_id or @username}")
        return
    channel = context.args[0]
    # Resolve if @username
    if channel.startswith('@'):
        try:
            chat = await context.bot.get_chat(channel)
            channel = chat.id
        except:
            await update.message.reply_text("Invalid channel username.")
            return
    else:
        try:
            channel = int(channel)
        except:
            await update.message.reply_text("Invalid channel ID.")
            return
    
    settings = load_settings()
    settings['log_channel'] = channel
    save_settings(settings)
    await update.message.reply_text(f"Log channel set to {channel}.")

async def handle_setreferpercent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setpercent {percent}")
        return
    try:
        percent = float(context.args[0])
        settings = load_settings()
        settings['refer_percent'] = percent
        save_settings(settings)
        await update.message.reply_text(f"Referral percent set to {percent}%.")
    except ValueError:
        await update.message.reply_text("Invalid percent.")


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display user stats with bold labels and values."""
    user_id = str(update.effective_user.id)
    users = load_users()
    if user_id not in users:
        await update.message.reply_text("No stats available. Start a deal to create your profile.")
        return
    
    user_data = users[user_id]
    ref_link = f"t.me/{BOT_USERNAME}?start=ref_{user_id}"

    # Calculate rank based on total_wagered
    sorted_users = sorted(
        users.items(),
        key=lambda x: x[1].get("total_wagered", 0.0),
        reverse=True
    )
    rank = next((i + 1 for i, (uid, _) in enumerate(sorted_users) if uid == user_id), 0)

    # Get first name
    try:
        chat = await context.bot.get_chat(int(user_id))
        first_name = chat.first_name or "Unknown"
    except Exception as e:
        print(f"[DEBUG] Error getting chat for user {user_id}: {e}")
        first_name = "Unknown"

    await update.message.reply_text(
        f"<b>👤 Your Escrow Stats</b>\n\n"
        f"<b>👤 User ID:</b> <b>{user_id}</b>\n"
        f"<b>Name:</b> <b>{first_name}</b>\n"
        f"<b>Total Escrows:</b> <b>{user_data.get('total_deals', 0)}</b>\n"
        f"<b>Escrowed Amount:</b> <b>${user_data.get('total_wagered', 0.0):.2f}</b>\n"
        f"<b>Rank:</b> <b>{rank}</b>\n"
        f"<b>Referral Link:</b> <b>{ref_link}</b>",
        parse_mode='HTML'
    )



async def handle_gbstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
    
    settings = load_settings()
    stats = load_stats()
    users = load_users()
    
    total_deals = sum(u['total_deals'] for u in users.values())
    total_finished = sum(u['completed_deals'] for u in users.values())
    total_users = len(users)
    
    keyboard = [[InlineKeyboardButton("Check Fee Balance", callback_data="check_admin_balance")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"<b>🌐 Global Escrow Stats</b>\n\n"
        f"<b>Total Fees Collected:</b> <code>${settings.get('admin_balance', 0.0):.2f}</code>\n"
        f"<b>Total Deals:</b> <code>{total_deals}</code>\n"
        f"<b>Completed Deals:</b> <code>{total_finished}</code>\n"
        f"<b>Total Escrow Amount:</b> <code>${stats['total_worth']:.2f}</code>\n"
        f"<b>Total Users:</b> <code>{total_users}</code>\n"
        f"<b>Referral Percent:</b> <code>{settings.get('refer_percent', DEFAULT_REFER_PERCENT)}%</code>\n"
        f"<b>Max Amount/Deal:</b> <code>${settings.get('max_deal', DEFAULT_MAX_DEAL)}</code>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def handle_allow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /allow {groupid}")
        return
    try:
        group_id = int(context.args[0])
        settings = load_settings()
        allowed = settings.get('allowed_groups', [])
        if group_id not in allowed:
            allowed.append(group_id)
            settings['allowed_groups'] = allowed
            save_settings(settings)
        await update.message.reply_text(f"Group {group_id} allowed.")
    except ValueError:
        await update.message.reply_text("Invalid group ID.")

async def handle_disallow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Similar to allow, but remove
    # ... implement similarly ...
    pass

async def handle_withdfee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin fee withdrawal using MEXC API"""
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return

    if len(context.args) < 3:
        await update.message.reply_text("Usage: /withdfee {amount} {coin} {address} [memo] [network]")
        return

    try:
        amount = float(context.args[0])
        coin = context.args[1].upper()
        address = context.args[2]
        memo = context.args[3] if len(context.args) > 3 else None
        network_input = context.args[4].upper() if len(context.args) > 4 else None

        # Map coin and network
        coin_key = coin
        if coin == 'USDT':
            if not network_input:
                await update.message.reply_text("For USDT, specify network (e.g., TRC20, ERC20): /withdfee {amount} USDT {address} [memo] {network}")
                return
            network_mappings = {
                'TRC20': 'Tron(TRC20)',
                'ERC20': 'Ethereum(ERC20)',
                'BEP20': 'BNB Smart Chain(BEP20)',
                'SOL': 'Solana(SOL)',
                'MATIC': 'Polygon(MATIC)',
                'TON': 'Toncoin(TON)'
            }
            network = network_mappings.get(network_input)
            if not network:
                await update.message.reply_text(f"Invalid network. Supported for USDT: {', '.join(network_mappings.keys())}")
                return
            coin_key = f"USDT_{network_input}"

        coin_info = NETWORK_MAPPING.get(coin_key)
        if not coin_info:
            await update.message.reply_text(f"Invalid coin or network. Supported: {', '.join(NETWORK_MAPPING.keys())}")
            return

        # Load fees.json
        fees_data = load_fees_json()
        withdraw_min = None
        withdraw_fee = await get_withdraw_fee(coin_info['currency'], coin_info['network'])
        if withdraw_fee is None:
            await update.message.reply_text(f"Could not retrieve withdrawal fee for {coin_info['currency']} on {coin_info['network']}.")
            return

        for fee_entry in fees_data:
            if fee_entry['coin'] == coin_info['currency'] and fee_entry['network'] == coin_info['network']:
                withdraw_min = float(fee_entry['withdrawMin'])
                break

        if withdraw_min is None:
            await update.message.reply_text(f"Could not retrieve minimum withdrawal amount for {coin_info['currency']} on {coin_info['network']}.")
            return

        # Convert amounts if necessary
        amount_usd = amount if coin.upper() == 'USDT' else await convert_coin_to_usd(coin, amount)
        withdraw_min_usd = withdraw_min if coin.upper() == 'USDT' else await convert_coin_to_usd(coin, withdraw_min)
        withdraw_fee_usd = withdraw_fee if coin.upper() == 'USDT' else await convert_coin_to_usd(coin, withdraw_fee)

        if amount_usd is None or withdraw_min_usd is None or withdraw_fee_usd is None:
            await update.message.reply_text(f"Error converting amounts for {coin_info['currency']}.")
            return

        # Check minimum withdrawal
        if amount < withdraw_min:
            await update.message.reply_text(
                f"Amount {amount} {coin_info['currency']} is below minimum withdrawal of {withdraw_min} {coin_info['currency']} "
                f"(${withdraw_min_usd:.2f} USD)."
            )
            return

        # Check balance
        settings = load_settings()
        total_usd = amount_usd + withdraw_fee_usd
        if total_usd > settings.get('admin_balance', 0.0):
            await update.message.reply_text(
                f"Insufficient admin balance. Required: ${total_usd:.2f} USD (Amount: ${amount_usd:.2f} + Fee: ${withdraw_fee_usd:.2f}). "
                f"Available: ${settings.get('admin_balance', 0.0):.2f}."
            )
            return

        # Perform withdrawal
        payout = await create_mexc_withdrawal(
            coin=coin_info['currency'],
            network=coin_info['network'],
            address=address,
            amount=amount,
            memo=memo
        )

        if payout.get('success', False):
            settings['admin_balance'] -= total_usd
            save_settings(settings)
            memo_text = f"\nMemo: {memo}" if memo else ""
            await update.message.reply_text(
                f"Withdrawal successful:\n"
                f"Amount: {amount} {coin_info['display_name']}\n"
                f"Fee: {withdraw_fee} {coin_info['currency']}\n"
                f"Address: {address}{memo_text}"
            )
        else:
            error = payout.get('error', 'Unknown error')
            await update.message.reply_text(f"Withdrawal failed: {error}")

    except ValueError:
        await update.message.reply_text("Invalid amount or parameters.")
    except Exception as e:
        await update.message.reply_text(f"Error processing withdrawal: {str(e)}")

async def handle_withdpercent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user referral balance withdrawal using MEXC API"""
    user_id = str(update.effective_user.id)
    users = load_users()
    if user_id not in users or users[user_id]['balance'] <= 0:
        await update.message.reply_text("No balance to withdraw.")
        return

    if len(context.args) < 3:
        await update.message.reply_text("Usage: /withdpercent {amount} {coin} {address} [memo] [network]")
        return

    try:
        amount = float(context.args[0])
        coin = context.args[1].upper()
        address = context.args[2]
        memo = context.args[3] if len(context.args) > 3 else None
        network_input = context.args[4].upper() if len(context.args) > 4 else None

        # Map coin and network
        coin_key = coin
        if coin == 'USDT':
            if not network_input:
                await update.message.reply_text("For USDT, specify network (e.g., TRC20, ERC20): /withdpercent {amount} USDT {address} [memo] {network}")
                return
            network_mappings = {
                'TRC20': 'Tron(TRC20)',
                'ERC20': 'Ethereum(ERC20)',
                'BEP20': 'BNB Smart Chain(BEP20)',
                'SOL': 'Solana(SOL)',
                'MATIC': 'Polygon(MATIC)',
                'TON': 'Toncoin(TON)'
            }
            network = network_mappings.get(network_input)
            if not network:
                await update.message.reply_text(f"Invalid network. Supported for USDT: {', '.join(network_mappings.keys())}")
                return
            coin_key = f"USDT_{network_input}"

        coin_info = NETWORK_MAPPING.get(coin_key)
        if not coin_info:
            await update.message.reply_text(f"Invalid coin or network. Supported: {', '.join(NETWORK_MAPPING.keys())}")
            return

        # Load fees.json
        fees_data = load_fees_json()
        withdraw_min = None
        withdraw_fee = await get_withdraw_fee(coin_info['currency'], coin_info['network'])
        if withdraw_fee is None:
            await update.message.reply_text(f"Could not retrieve withdrawal fee for {coin_info['currency']} on {coin_info['network']}.")
            return

        for fee_entry in fees_data:
            if fee_entry['coin'] == coin_info['currency'] and fee_entry['network'] == coin_info['network']:
                withdraw_min = float(fee_entry['withdrawMin'])
                break

        if withdraw_min is None:
            await update.message.reply_text(f"Could not retrieve minimum withdrawal amount for {coin_info['currency']} on {coin_info['network']}.")
            return

        # Convert amounts if necessary
        amount_usd = amount if coin.upper() == 'USDT' else await convert_coin_to_usd(coin, amount)
        withdraw_min_usd = withdraw_min if coin.upper() == 'USDT' else await convert_coin_to_usd(coin, withdraw_min)
        withdraw_fee_usd = withdraw_fee if coin.upper() == 'USDT' else await convert_coin_to_usd(coin, withdraw_fee)

        if amount_usd is None or withdraw_min_usd is None or withdraw_fee_usd is None:
            await update.message.reply_text(f"Error converting amounts for {coin_info['currency']}.")
            return

        # Check minimum withdrawal
        if amount < withdraw_min:
            await update.message.reply_text(
                f"Amount {amount} {coin_info['currency']} is below minimum withdrawal of {withdraw_min} {coin_info['currency']} "
                f"(${withdraw_min_usd:.2f} USD)."
            )
            return

        # Check balance
        total_usd = amount_usd + withdraw_fee_usd
        if total_usd > users[user_id]['balance']:
            await update.message.reply_text(
                f"Insufficient referral balance. Required: ${total_usd:.2f} USD (Amount: ${amount_usd:.2f} + Fee: ${withdraw_fee_usd:.2f}). "
                f"Available: ${users[user_id]['balance']:.2f}."
            )
            return

        # Perform withdrawal
        payout = await create_mexc_withdrawal(
            coin=coin_info['currency'],
            network=coin_info['network'],
            address=address,
            amount=amount,
            memo=memo
        )

        if payout.get('success', False):
            users[user_id]['balance'] -= total_usd
            save_users(users)
            memo_text = f"\nMemo: {memo}" if memo else ""
            await update.message.reply_text(
                f"Withdrawal successful:\n"
                f"Amount: {amount} {coin_info['display_name']}\n"
                f"Fee: {withdraw_fee} {coin_info['currency']}\n"
                f"Address: {address}{memo_text}"
            )
        else:
            error = payout.get('error', 'Unknown error')
            await update.message.reply_text(f"Withdrawal failed: {error}")

    except ValueError:
        await update.message.reply_text("Invalid amount or parameters.")
    except Exception as e:
        await update.message.reply_text(f"Error processing withdrawal: {str(e)}")

async def handle_release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /release {deal_id}")
        return
    deal_id = context.args[0]
    deal_data = get_active_deal(deal_id)
    if not deal_data:
        await update.message.reply_text("Deal not found.")
        return
    
    try:
        context.user_data['deal_id'] = deal_id
        await handle_release_payment(update, context)
        await update.message.reply_text(f"Release initiated for deal {deal_id}.")
    except Exception as e:
        await update.message.reply_text(f"Error releasing deal: {e}")

async def log_deal_event(bot, deal_data, deal_id, event_type):
    settings = load_settings()
    log_channel = settings.get('log_channel')
    if not log_channel:
        return
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    event_desc = {
        'cancelled': 'Deal Cancelled',
        'refunded': 'Deal Refunded'
    }.get(event_type, event_type)
    
    log_text = (
        f"⚠️ Escrow {event_desc}!\n"
        f"➥ ID - {deal_id}\n"
        f"➥ Buyer - {deal_data['buyer_name']}\n"
        f"➥ Seller - {deal_data['seller_name']}\n"
        f"➥ Amount - ${deal_data['amount']:.2f}\n"
        f"➥ Timestamp: {timestamp}"
    )
    
    try:
        await bot.send_message(chat_id=log_channel, text=log_text)
    except Exception as e:
        print(f"Error logging {event_type} to channel {log_channel}: {e}")
    


async def handle_kickall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        print("[handle_kickall]Only admin can use this command.")
        return

    # Determine group ID
    group_id = update.effective_chat.id if update.effective_chat.type in ['group', 'supergroup'] else None
    if context.args:
        try:
            group_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid group ID. Usage: /kickall [group_id]")
            return

    if not group_id:
        await update.message.reply_text("This command must be used in a group or with a valid group_id.")
        return

    # Check bot admin permissions
    if not await is_bot_admin(context, group_id):
        await update.message.reply_text("Bot must be an admin with permission to kick members.")
        return

    # Get users involved in active deals
    active_deals = get_all_active_deals()
    active_users = set()
    for deal_id, deal in active_deals.items():
        if deal['group_id'] == group_id and deal['status'] not in ['completed', 'cancelled']:
            active_users.add(deal['buyer'])
            active_users.add(deal['seller'])

    # Fetch all group members using Telegram Bot API
    members = []
    try:
        global telethon_client
        if telethon_client is None or not telethon_client.is_connected():
            await update.message.reply_text("Telethon client not connected.")
            return
        async for member in telethon_client.iter_participants(group_id):
            members.append(member.id)
    except Exception as e:
        print(f"[kickall] Error fetching members: {e}")
        await update.message.reply_text("Error fetching group members. Ensure bot has access to the group.")
        return

    # Get bot's user ID
    bot_user = await context.bot.get_me()
    bot_id = bot_user.id

    # Kick non-active, non-protected members
    kicked_count = 0
    for user_id in members:
        if user_id not in active_users and user_id != bot_id and user_id != ADMIN_ID:
            try:
                # Kick using Telegram API
                await context.bot.ban_chat_member(group_id, user_id)
                await context.bot.unban_chat_member(group_id, user_id)  # Unban to allow rejoin
                kicked_count += 1
            except BadRequest as e:
                if 'admin' in str(e).lower():
                    print(f"[kickall] Cannot kick admin user {user_id}")
                    continue
                print(f"[kickall] Error kicking user {user_id}: {e}")
                continue

    # Send summary
    total_members = len(members) - 2  # Exclude bot and admin
    active_count = len(active_users)
    await update.message.reply_text(
        f"Kicked {kicked_count} members not in active deals.\n"
        f"Total members: {total_members}\n"
        f"Active deal participants: {active_count}"
    )

async def handle_bio_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /bio_single {discount}")
        return
    try:
        discount = float(context.args[0])
        settings = load_settings()
        settings['single_bio_discount'] = discount
        save_settings(settings)
        await update.message.reply_text(f"Single bio discount set to {discount}%.")
    except ValueError:
        await update.message.reply_text("Invalid discount value. Use a number (e.g., 20).")

async def handle_bio_duo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /bio_duo discount")
        return
    try:
        discount = float(context.args[0])
        settings = load_settings()
        settings['both_bio_discount'] = discount
        save_settings(settings)
        await update.message.reply_text(f"Duo bio discount set to {discount}%.")
    except ValueError:
        await update.message.reply_text("Invalid discount value. Use a number (e.g., 50).")


async def handle_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display top 10 users by escrowed volume with hyperlinked first names."""
    users = load_users()
    sorted_users = sorted(
        users.items(),
        key=lambda x: x[1].get("total_wagered", 0.0),
        reverse=True
    )[:10]

    if not sorted_users or all(data.get("total_wagered", 0.0) == 0 for _, data in sorted_users):
        await update.message.reply_text(
            "📊 <b>No escrow deals completed yet.</b>",
            parse_mode='HTML'
        )
        return

    text = "<b>🏆 Top by Escrowed Volume</b>\n\n"
    for rank, (user_id, data) in enumerate(sorted_users, 1):
        wagered = data.get("total_wagered", 0.0)
        if wagered == 0:
            continue
        try:
            chat = await context.bot.get_chat(int(user_id))
            first_name = chat.first_name or "Unknown"
        except Exception as e:
            print(f"[DEBUG] Error getting chat for user {user_id}: {e}")
            first_name = "Unknown"
        text += f"{rank}. <a href='tg://user?id={user_id}'>{first_name}</a> - <b>${wagered:.2f}</b>\n"

    if text == "<b>🏆 Top by Escrowed Volume</b>\n\n":
        text = "📊 <b>No escrow deals completed yet.</b>"

    await update.message.reply_text(text, parse_mode='HTML')