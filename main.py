import asyncio
import os
import hmac
import hashlib
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputFile
from config import TOKEN, OXAPAY_API_KEY, ADMIN_ID
from handlers import *
from callback import handle_callback
from deposit import handle_deposit
from telegram.error import BadRequest
from refund import handle_refund, handle_refund_agreement
from utils import get_active_deal, update_active_deal, remove_active_deal
from datetime import datetime, timedelta
import httpx
import time
from fastapi.responses import PlainTextResponse
from login import *
from config import DEAL_TYPE_DISPLAY
import json 

app = FastAPI()

# Initialize bot
bot = Application.builder().token(TOKEN).build().bot

# Pin tracker for group pins (max 4 per group)
PIN_TRACKER = {}
ADMIN_MONITORS = {}

async def monitor_admin_main(group_id, deal_id, bot, main_msg_id):
    mon_key = f"{group_id}_{get_active_deal(deal_id).get('buyer')}_{get_active_deal(deal_id).get('seller')}"
    try:
        try:
            while True:
                active_deal = get_active_deal(deal_id)
                if not active_deal or active_deal.get("status") != "deposited":
                    break
                is_admin = await ensure_bot_admin_telethon(group_id)
                if not is_admin:
                    buyer_link = f"<a href='tg://user?id={active_deal['buyer']}'>{active_deal.get('buyer_name', 'UNKNOWN')}</a>"
                    seller_link = f"<a href='tg://user?id={active_deal['seller']}'>{active_deal.get('seller_name', 'UNKNOWN')}</a>"
                    text = (
                        f"🚨<b>BOT IS NO LONGER ADMIN</b>\n\n"
                        f"Deal forcibly ended.\n"
                        f"Group ID: <code>{group_id}</code>\n"
                        f"<b>Buyer:</b> {buyer_link}\n"
                        f"<b>Seller:</b> {seller_link}\n\n"
                        f"<code>/leave {group_id}</code>\n to force bot exit this group."
                    )
                    await bot.send_message(ADMIN_ID, text, parse_mode='HTML')
                    remove_active_deal(deal_id)
                    try:
                        await bot.edit_message_text(
                            chat_id=group_id,
                            message_id=main_msg_id,
                            text="<b>❌ DEAL FORCIBLY ENDED\n\n Bot was REMOVED as admin. Please contact support.</b>",
                            parse_mode='HTML'
                        )
                    except Exception:
                        pass
                    break
                await asyncio.sleep(20)
        except Exception as e:
            print(f"[monitor_admin_main] Background admin monitor error: {e}")
    finally:
        if mon_key in ADMIN_MONITORS:
            del ADMIN_MONITORS[mon_key]


async def handle_getcustom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends custom.json to the admin."""
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("You are not authorized to use this command.")
        return
    try:
        if os.path.exists("custom.json"):
            with open("custom.json", "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename="custom.json",
                    caption="Here is the current custom.json configuration."
                )
        else:
            await update.message.reply_text("custom.json not found.")
    except Exception as e:
        await update.message.reply_text(f"Error sending custom.json: {e}")

async def handle_setcustom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Allows admin to update custom.json by replying to /setcustom with a document.
    Usage:
      1. /setcustom
      2. Reply with new custom.json
    """
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if update.message.reply_to_message and update.message.reply_to_message.document:
        document = update.message.reply_to_message.document
        if document.file_name != "custom.json":
            await update.message.reply_text("Please upload a file named custom.json.")
            return

        try:
            file = await document.get_file()
            file_path = "custom.json"
            await file.download_to_drive(file_path)
            # Validate JSON
            with open(file_path, "r", encoding="utf-8") as f:
                json.load(f)
            await update.message.reply_text("custom.json updated successfully ✅")
        except Exception as e:
            await update.message.reply_text(f"Failed to update custom.json: {e}")
    else:
        await update.message.reply_text(
            "To update custom.json:\n1. Upload/send the new custom.json file.\n2. Reply to this message with the document attached."
        )

import traceback
import sys

from telegram.constants import ParseMode

async def error_handler(update, context):
    """Enhanced error handler for Telegram bots, with suggestions and traceback."""

    # Gather error info
    exc_type, exc_value, exc_tb = sys.exc_info()
    tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    error_message = f"Error occurred: {context.error}\n\nTraceback:\n{tb_str}"

    # Suggest code fix if common known issues detected (simple demo logic)
    suggestion = ""
    error_text = str(context.error)
    if "'NoneType' object has no attribute 'groups'" in error_text:
        suggestion = (
            "⚡ *Code suggestion*: This error often happens when you try to use `.groups()` on a failed regex match (None).\n"
            "- Check any `re.match`/`re.search` calls: always verify the match object is not `None` before using `.groups()`!\n"
            "Example fix:\n"
            "```python\n"
            "match = re.match(pattern, text)\n"
            "if match:\n"
            "   print(match.groups())\n"
            "else:\n"
            "   print('No match!')\n"
            "```\n"
        )
    # Add more error suggestions as needed...

    output_msg = f"{error_message}\n\n{suggestion}"

    # Optionally, print to console and/or log file
    print(output_msg)

    


async def handle_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = update.effective_user.id == ADMIN_ID
    commands = [
        "/start - Start the bot",
        "/stats - View your stats",
        "/withdpercent {amount} {coin} {address} [memo] - Withdraw referral balance",
        "/rank  - View top users with highest escrow deal", 
        "/leaderboard - Same for /rank command",
    ]
    if is_admin:
        commands += [
            "/setmaxdeal {amount} - Set max deal amount",
            "/setfreelimit {amount} - Set free escrow limit",
            "/setlogchannel {channel_id} - Set log channel",
            "/setreferpercent {percent} - Set referral percent",
            "/allow {group_id} - Allow group for deals",
            "/disallow {group_id} - Disallow group",
            "/close {deal_id/user_id/@mention} - Close deal/user deals",
            "/enddeal {deal_id} - End deal",
            "/killdeal {deal_id} - Kill deal",
            "/refund {deal_id} - Refund deal",
            "/release {deal_id} - Release payment",
            "/withdfee {amount} {coin} {address} [memo] - Withdraw admin fee",
            "/gbstats - Global stats",
            "/logout - Logout admin",
            "/setfee {p2p_fee} {bs_fee} - Set fees",
            "/getcustom - Get current custom.json",
            "/setcustom - Update custom.json (reply with file)",
            "/fetch - Fetch new groups",
            "/on - Turn admin telethon ON",
            "/off - Turn admin telethon OFF",
            "/getgroups - List allowed groups",
            "/leave {group_id} - Force bot to leave group",
            "/create - Create a new group",
            "setsticker [sticker_id] - Set deal sticker",
            '/trades - get log of completed trades',          
            '/bio_single / bio_duo  [disount] - set bio discount',
            '/login +1234567890 - admin login',
            '/kickall - kick all users (without deal) from a group'
        ]
    
    command_text = "<b>Available Commands:</b>\n" + "\n".join([f"<code>{cmd}</code>" for cmd in commands])
    await update.message.reply_text(command_text, parse_mode='HTML')

async def run_bot():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("p2pfee", handle_p2pfee))
    application.add_handler(CommandHandler("bsfee", handle_bsfee))
    application.add_handler(CommandHandler("trades", handle_trades))
    application.add_handler(CommandHandler("enddeal", handle_killdeal))
    application.add_handler(CommandHandler("killdeal", handle_killdeal))
    application.add_handler(CommandHandler("endall", handle_killall))
    application.add_handler(CommandHandler("setsticker", handle_setsticker))
    application.add_handler(CommandHandler("getdeal", handle_getdeal))
    application.add_handler(CommandHandler("refund", handle_refund))
    # application.add_handler(CommandHandler("form", handle_form))
    application.add_handler(CommandHandler("login", handle_login))
    application.add_handler(CommandHandler("list", handle_list))

    application.add_handler(CommandHandler("logout", handle_logout, filters=filters.User(user_id=ADMIN_ID)))
    application.add_handler(CommandHandler("setfee", handle_setfee, filters=filters.User(user_id=ADMIN_ID)))
    application.add_handler(CommandHandler("create", handle_create))
    application.add_handler(CommandHandler("fetch", handle_fetch))
    application.add_handler(CommandHandler("on", handle_on))
    application.add_handler(CommandHandler("off", handle_off))
    application.add_handler(CommandHandler("getgroups", handle_getgroups))
    application.add_handler(CommandHandler("getcustom", handle_getcustom))
    application.add_handler(CommandHandler("setcustom", handle_setcustom))
    application.add_handler(CommandHandler("leave", handle_leave))
    application.add_handler(CommandHandler("setmaxdeal", handle_setmaxdeal))
    application.add_handler(CommandHandler("setfreelimit", handle_setfreelimit))
    application.add_handler(CommandHandler("setlogchannel", handle_setlogchannel))
    application.add_handler(CommandHandler("setreferpercent", handle_setreferpercent))
    application.add_handler(CommandHandler("stats", handle_stats))
    application.add_handler(CommandHandler("gbstats", handle_gbstats))
    application.add_handler(CommandHandler("allow", handle_allow))
    application.add_handler(CommandHandler("release", handle_release))
    application.add_handler(CommandHandler("disallow", handle_disallow))
    application.add_handler(CommandHandler("close", handle_close))
    application.add_handler(CommandHandler("bio_single", handle_bio_single))
    application.add_handler(CommandHandler("bio_duo", handle_bio_duo))
    application.add_handler(CommandHandler("kickall", handle_kickall))
    application.add_handler(CommandHandler("rank", handle_rank))
    application.add_handler(CommandHandler("leaderboard", handle_rank))
    application.add_handler(CommandHandler("broadcast", handle_broadcast))
    # Add for cancel, refund, release
    application.add_handler(CommandHandler("withdfee", handle_withdfee))
    application.add_handler(CommandHandler("withdpercent", handle_withdpercent))



    application.add_handler(CallbackQueryHandler(handle_callback))  
    application.add_handler(CallbackQueryHandler(handle_refund_agreement, pattern="^refund_(agree|deny)$"))
    

    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_form))
    application.add_error_handler(error_handler)

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

@app.on_event("startup")
async def startup_event():
    
    asyncio.create_task(run_bot())
    await start_telethon_client()
   

@app.get("/")
async def home():
    return {"message": "Welcome to the FastAPI App!"}

@app.api_route("/ping", methods=["GET", "HEAD"], response_class=PlainTextResponse)
async def ping():
    start_time = time.time()
    async with httpx.AsyncClient() as client:
        response = await client.get("https://httpbin.org/get")
    end_time = time.time()
    response_time = round((end_time - start_time) * 1000)
    return f"PONG {response_time}ms"




async def check_payment_timeout(bot, group_id, deal_id, message_id):
    deal_data = get_active_deal(deal_id)
    if not deal_data:
        return
    
    timer_hours = deal_data.get('timer_hours', 1)
    check_interval = 10 
    total_seconds = int(timer_hours * 3600)
    elapsed = 0

    while elapsed < total_seconds:
        current_deal = get_active_deal(deal_id)
        if not current_deal or current_deal.get('status') != 'deposited':
            return  # End early if deal not active/deposited anymore
        await asyncio.sleep(check_interval)
        elapsed += check_interval

    # Timer expired, check again before action
    current_deal = get_active_deal(deal_id)
    if not current_deal or current_deal.get('status') != 'deposited':
        return

    try:
        # Get the group's invite link
        try:
            group_invite_link = await bot.export_chat_invite_link(group_id)
        except Exception:
            group_invite_link = "(Unable to fetch invite link)"

        await bot.edit_message_text(
            chat_id=group_id,
            message_id=message_id,
            text=f"⚠️ <b>TIMER EXPIRED - MODERATOR INVOLVED</b>\n\n"
                 f"The {timer_hours}-hour timer has expired.\n"
                 f"A moderator has been automatically notified.\n\n"
                 f"Deal ID: <code>{deal_id}</code>",
            parse_mode='HTML'
        )
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 <b>AUTO-ESCALATION</b>\n\n"
                 f"Deal ID: <code>{deal_id}</code>\n"
                 f"Timer: {timer_hours} hours expired\n"
                 f"Group: {group_id}\n"
                 f"Link: {group_invite_link}\n"
                 f"Status: Requires moderator intervention",
            parse_mode='HTML'
        )
    except Exception as e:
        print(f"Error in timeout handler: {e}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

