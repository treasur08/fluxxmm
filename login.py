from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telegram import Update
from telegram.ext import ContextTypes
import os
from dotenv import load_dotenv
import asyncio
from config import ADMIN_ID

load_dotenv()

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_FILE = 'admin_session'


async def handle_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[LOGIN] handle_login called.")
    if update.effective_user.id != ADMIN_ID:
        print(f"[LOGIN] Unauthorized user: {update.effective_user.id}")
        return
    if update.message.chat.type != "private":
        await update.message.reply_text("Please use this command in bots dm")
        return

    # Check if persistent Telethon client is running, abort if yes
    from handlers import telethon_client
    if telethon_client is not None:
        try:
            if telethon_client.is_connected():
                await update.message.reply_text("Admin Telethon client is running. Please use /off to turn it off before logging in.")
                print("[LOGIN] Aborted: Telethon client is running.")
                return
        except Exception as e:
            print(f"[LOGIN] Could not check telethon_client connection: {e}")

    phone = update.message.text.split(' ')[1] if len(update.message.text.split(' ')) > 1 else None
    print(f"[LOGIN] Phone provided: {phone}")
    if not phone:
        await update.message.reply_text("Usage: /login +countrycode number\nExample: /login +1234567890")
        print("[LOGIN] No phone provided, instruct usage.")
        return

    print("[LOGIN] Creating TelegramClient instance (not connecting yet)...")
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    # DO NOT connect or check authorization yet!
    context.user_data['awaiting_code'] = False
    context.user_data['awaiting_password'] = False
    context.user_data['client'] = client
    context.user_data['phone'] = phone
    try:
        print("[LOGIN] Connecting client to send code request...")
        await client.connect()
        if not await client.is_user_authorized():
            print("[LOGIN] User not authorized. Sending code request...")
            await client.send_code_request(phone)
            await update.message.reply_text("Code sent! Please enter the code you received\n\n`1 2 3 4 5`\n\nEnsure code is spaced out", parse_mode="Markdown")
            context.user_data['awaiting_code'] = True
            print("[LOGIN] Code sent, context updated: awaiting_code=True.")
        else:
            print("[LOGIN] Already authorized, disconnecting.")
            await update.message.reply_text("Already logged in!")
            await client.disconnect()
    except Exception as e:
        print(f"[LOGIN] Error in login flow: {e}")
        await update.message.reply_text(f"Error during login: {str(e)}")
        await client.disconnect()
        context.user_data.clear()

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers import start_telethon_client, telethon_client
    print("[LOGIN] handle_code called.")
    
    # Check if in private chat; if not, remind user
    if update.message.chat.type != "private":
        if context.user_data.get('awaiting_code'):
            
            print("[LOGIN] handle_code: Ignored because message is not in a private chat.")
        return
    
    # Check if persistent Telethon client is running, abort if yes
    if telethon_client is not None:
        try:
            if telethon_client.is_connected():
                await update.message.reply_text("Admin Telethon client is running. Please use /off to turn it off before logging in.")
                print("[LOGIN] Aborted: Telethon client is running.")
                return
        except Exception as e:
            print(f"[LOGIN] Could not check telethon_client connection: {e}")
    if not context.user_data.get('awaiting_code'):
        print("[LOGIN] Not awaiting code, returning.")
        return

    code = update.message.text.strip()
    print(f"[LOGIN] Code received: {code}")
    client = context.user_data['client']
    phone = context.user_data['phone']

    try:
        print("[LOGIN] Connecting client for code sign-in...")
        await client.connect()
        print("[LOGIN] Signing in with code...")
        await client.sign_in(phone, code)
        await update.message.reply_text("Successfully logged in as Admin!")
        await client.disconnect()
        del client
        context.user_data.clear()
        print("[LOGIN] Waiting 2 seconds before starting Telethon client to ensure clean disconnect...")
        await asyncio.sleep(2)  # Prevent session file contention
        print("[LOGIN] About to call start_telethon_client after successful code login...")
        import handlers
        handlers.telethon_client = None
        await start_telethon_client()
        print("[LOGIN] start_telethon_client completed.")
    except SessionPasswordNeededError:
        print("[LOGIN] SessionPasswordNeededError, 2FA required.")
        context.user_data['awaiting_code'] = False
        context.user_data['awaiting_password'] = True
        await update.message.reply_text("2FA enabled! Please enter your password")
    except Exception as e:
        print(f"[LOGIN] Error signing in: {e}")
        await update.message.reply_text(f"Error signing in: {str(e)}")
        await client.disconnect()
        context.user_data.clear()

async def handle_2fa_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers import start_telethon_client, telethon_client
    print("[LOGIN] handle_2fa_password called.")
    
    # Check if in private chat; if not, remind user
    if update.message.chat.type != "private":
        if context.user_data.get('awaiting_password'):
            await update.message.reply_text("Please send the 2FA password in private DM with the bot.")
        print("[LOGIN] handle_2fa_password: Ignored because message is not in a private chat.")
        return
    
    # Check if persistent Telethon client is running, abort if yes
    if telethon_client is not None:
        try:
            if telethon_client.is_connected():
                await update.message.reply_text("Admin Telethon client is running. Please use /off to turn it off before logging in.")
                print("[LOGIN] Aborted: Telethon client is running.")
                return
        except Exception as e:
            print(f"[LOGIN] Could not check telethon_client connection: {e}")
    if not context.user_data.get('awaiting_password'):
        print("[LOGIN] Not awaiting password, returning.")
        return

    password = update.message.text
    print(f"[LOGIN] Password received (truncated for privacy): {password[:2]}... [hidden]")
    client = context.user_data['client']

    try:
        print("[LOGIN] Connecting client for 2FA password sign-in...")
        await client.connect()
        print("[LOGIN] Signing in with 2FA password...")
        await client.sign_in(password=password)
        await update.message.reply_text("Successfully logged in with 2FA as Admin!")
        await client.disconnect()
        del client
        context.user_data.clear()
        print("[LOGIN] Waiting 2 seconds before starting Telethon client to ensure clean disconnect...")
        await asyncio.sleep(2)  # Ensure session file to close
        print("[LOGIN] About to call start_telethon_client after successful 2FA login...")
        import handlers
        handlers.telethon_client = None
        await start_telethon_client()
        print("[LOGIN] start_telethon_client completed.")
    except Exception as e:
        print(f"[LOGIN] Error with 2FA: {e}")
        await update.message.reply_text(f"Error with 2FA: {str(e)}")
        print("[LOGIN] Disconnecting client and clearing context after 2FA attempt (error case).")
        await client.disconnect()
        context.user_data.clear()

async def handle_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
   
    try:
        if os.path.exists(f'{SESSION_FILE}.session'):
            os.remove(f'{SESSION_FILE}.session')
            await update.message.reply_text("Successfully logged out! Session terminated ✅")
        else:
            await update.message.reply_text("No active session found")
    except Exception as e:
        await update.message.reply_text(f"Error during logout: {str(e)}")