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
    if update.effective_user.id != os.getenv('ADMIN_ID'):
        await update.message.reply_text("Only admin can use this command")
        return
    
    phone = update.message.text.split(' ')[1] if len(update.message.text.split(' ')) > 1 else None
    if not phone:
        await update.message.reply_text("Usage: /login +countrycode number\nExample: /login +1234567890")
        return
        
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.connect()
    
    if not await client.is_user_authorized():
        try:
            await client.send_code_request(phone)
            await update.message.reply_text("Code sent! Please enter the code you received\n\n`1 2 3 4 5`\n\nEnsure code is spaced out", parse_mode="Markdown")
            context.user_data['awaiting_code'] = True
            context.user_data['client'] = client
            context.user_data['phone'] = phone
        except Exception as e:
            await update.message.reply_text(f"Error sending code: {str(e)}")
            await client.disconnect()
            context.user_data.clear()
    else:
        await update.message.reply_text("Already logged in!")
        await client.disconnect()

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers import start_telethon_client
    if not context.user_data.get('awaiting_code'):
        return
        
    code = update.message.text
    client = context.user_data['client']
    phone = context.user_data['phone']
    
    try:
        await client.sign_in(phone=phone, code=code)
        await start_telethon_client()  # Ensures global admin Telethon client is authorized after login
        await update.message.reply_text("Successfully logged in! You can now use username resolution")
        context.user_data.clear()
    except SessionPasswordNeededError:
        context.user_data['awaiting_code'] = False  
        context.user_data['awaiting_password'] = True
        await update.message.reply_text("2FA enabled! Please enter your password")
    except Exception as e:
        await update.message.reply_text(f"Error signing in: {str(e)}")
        await client.disconnect()
        context.user_data.clear()

async def handle_2fa_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers import start_telethon_client
    if not context.user_data.get('awaiting_password'):
        return
        
    password = update.message.text
    client = context.user_data['client']
    
    try:
        await client.sign_in(password=password)
        await start_telethon_client()  # Ensures global admin Telethon client is authorized after login
        await update.message.reply_text("Successfully logged in with 2FA! You can now use username resolution")
    except Exception as e:
        await update.message.reply_text(f"Error with 2FA: {str(e)}")
    finally:
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



