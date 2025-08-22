import asyncio
import os
import hmac
import hashlib
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputFile
from config import TOKEN, OXAPAY_API_KEY, ADMIN_ID
from handlers import *
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
                await asyncio.sleep(5)
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
async def error_handler(update, context):
    print(f"Error occurred: {context.error}")

async def run_bot():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("sdeal", handle_startdeal))
    application.add_handler(CommandHandler("p2pfee", handle_p2pfee))
    application.add_handler(CommandHandler("bsfee", handle_bsfee))
    application.add_handler(CommandHandler("trades", handle_trades))
    application.add_handler(CommandHandler("enddeal", handle_killdeal))
    application.add_handler(CommandHandler("endall", handle_killall))
    application.add_handler(CommandHandler("setsticker", handle_setsticker))
    application.add_handler(CommandHandler("getdeal", handle_getdeal))
    application.add_handler(CommandHandler("refund", handle_refund))
    application.add_handler(CommandHandler("form", handle_form))
    application.add_handler(CommandHandler("login", handle_login))
    application.add_handler(CommandHandler("logout", handle_logout, filters=filters.User(user_id=ADMIN_ID)))
    application.add_handler(CommandHandler("setfee", handle_setfee, filters=filters.User(user_id=ADMIN_ID)))
    application.add_handler(CommandHandler("create", handle_create))
    application.add_handler(CommandHandler("fetch", handle_fetch))
    application.add_handler(CommandHandler("off", handle_off))
    application.add_handler(CommandHandler("getgroups", handle_getgroups))
    application.add_handler(CommandHandler("getcustom", handle_getcustom))
    application.add_handler(CommandHandler("setcustom", handle_setcustom))
    application.add_handler(CommandHandler("leave", handle_leave))




    application.add_handler(CallbackQueryHandler(handle_refund_agreement, pattern="^refund_(agree|deny)$"))
    application.add_handler(CallbackQueryHandler(handle_callback))  

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
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

@app.post("/oxapay_callback")
async def oxapay_callback(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.body()
        signature = request.headers.get('sign')
        
        if signature:
            calculated_signature = hmac.new(
                OXAPAY_API_KEY.encode(),
                payload,
                hashlib.sha256
            ).hexdigest()

            if signature != calculated_signature:
                raise HTTPException(status_code=400, detail="Invalid signature")

        data = await request.json()
        print(f"Callback Data Received: {data}")

        deal_id = data.get("orderId")
        if not deal_id:
            raise HTTPException(status_code=400, detail="Missing orderId")

        deal_data = get_active_deal(deal_id)
        if not deal_data:
            print(f"No active deal found for deal_id: {deal_id}")
            return {"message": "No active deal found"}
        
        group_id = deal_data['group_id']

        buyer = await bot.get_chat(deal_data['buyer'])
        seller = await bot.get_chat(deal_data['seller'])

        status = data.get("status")
        if status == "Waiting":
            await bot.send_message(
                chat_id=group_id,
                text=f"💳 Payment initiated by <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\nWaiting for deposit...",
                parse_mode='HTML'
            )
        elif status == "Confirming":
            await bot.send_message(
                chat_id=group_id,
                text=f"🔄 Payment is being confirmed for <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>",
                parse_mode='HTML'
            )
        
        elif status == "Paid":
            update_active_deal(deal_id, {
                'status': 'deposited',
                'payment_time': datetime.now().isoformat()
            })
            try:
                await bot.delete_message(
                    chat_id=group_id,
                    message_id=data.get("message_id")  
                )
            except:
                pass
            
            amount = deal_data['amount']
            fee = calculate_fee(amount, deal_data['deal_type'])
            total = amount + fee
            
            # Get custom timer or default to 1 hour
            timer_hours = deal_data.get('timer_hours', 1)
            timer_display = f"{timer_hours} Hour{'s' if timer_hours > 1 else ''}"

            keyboard = [  
                [InlineKeyboardButton("💰 Release Payment", callback_data="release_payment")],  
                [InlineKeyboardButton("⏳ Check Timer", callback_data="check_timer")],  
                [InlineKeyboardButton("👨‍💼 Involve Moderator", callback_data="mod")],  
                [InlineKeyboardButton("🚫 End Deal", callback_data="back")]  
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            sent_message = await bot.send_message(
                chat_id=group_id,
                text=(
                    f"<b>PAYMENT CONFIRMED ✅</b>\n\n"
                    f"💵 <b>Deposit Amount:</b> ${amount:.2f}\n"
                    f"✅ <b>Payment confirmed from:</b> <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
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
                    f"<b>⏱ Time Remaining to Complete Trade: {timer_display}</b>\n"
                    f"⚠️ <i>Please complete the trade before the timer expires, or a moderator will be involved automatically.</i>"
                ),
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            # --- Start background admin monitoring after payment confirmed ---
            mon_key = f"{group_id}_{deal_data['buyer']}_{deal_data['seller']}"
            if mon_key not in ADMIN_MONITORS:
                ADMIN_MONITORS[mon_key] = asyncio.create_task(
                    monitor_admin_main(group_id, deal_id, bot, sent_message.message_id)
                )
            pins = PIN_TRACKER.get(group_id, [])
            try:
                await bot.pin_chat_message(group_id, sent_message.message_id)
                pins.append(sent_message.message_id)
                if len(pins) > 4:
                    to_unpin = pins.pop(0)
                    try:
                        await bot.unpin_chat_message(group_id, to_unpin)
                    except Exception:
                        pass
                PIN_TRACKER[group_id] = pins
            except Exception:
                pass
            background_tasks.add_task(check_payment_timeout, bot, group_id, deal_id, sent_message.message_id)
            

                
        elif status == "Expired":
            await bot.send_message(
                chat_id=group_id,
                text=f"⚠️ Payment time expired for <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>",
                parse_mode='HTML'
            )
            remove_active_deal(deal_id)

    except Exception as e:
        print(f"Error in callback: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return {"message": "ok"}

@app.post("/withdraw")
async def withdraw_callback(request: Request):
    try:
        data = await request.json()
        print(f"Withdrawal Callback Data Received: {data}")

        description = data.get("description", "")
        seller_id = description.split()[-1]

        status = data.get("status")
        amount = data.get("amount")
        currency = data.get("currency")

        await send_withdrawal_update_to_seller(bot, seller_id, status, amount, currency)

    except Exception as e:
        print(f"Error in withdrawal callback: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return {"message": "ok"}


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

