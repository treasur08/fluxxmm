# from quart import Quart, request
# from config import OXAPAY_API_KEY, ADMIN_ID, TOKEN
# import hmac
# import hashlib
# from utils import *
# from handlers import send_withdrawal_update_to_seller
# from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
# from telegram.ext import Application, ContextTypes, ApplicationBuilder
# from config import TOKEN
# from datetime import datetime, timedelta
# import asyncio

# DEAL_TYPE_DISPLAY = {
#     'b_and_s': 'Buy and Sell',
#     'p2p': 'P2P Transfer'
# }

# # Initialize bot
# bot = Application.builder().token(TOKEN).build().bot

# app = Quart(__name__)
# @app.route('/')
# async def home():
#     return "Welcome to the Quart App!"

# @app.route("/webhook", methods=["GET"])
# async def webhook():
#     return "Webhook is working!"

# @app.route("/oxapay_callback", methods=["POST"])
# async def oxapay_callback():
#     try:
#         # Parse the incoming data
#         if not request.headers.get('sign'):
#             print("✅ No signature provided - processing callback anyway")
#             data = await request.get_json()
#         else:
#             signature = request.headers.get('sign')
#             payload = await request.get_data()
#             calculated_signature = hmac.new(
#                 OXAPAY_API_KEY.encode(),
#                 payload,
#                 hashlib.sha256
#             ).hexdigest()

#             if signature != calculated_signature:
#                 print("❌ Invalid signature detected")
#                 return "Invalid signature", 400

#             print("✅ Signature verified")
#             data = await request.get_json()
#         print(f"Callback Data Received: {data}")

#         deal_id = data.get("orderId")
#         if not deal_id:
#             return "Missing orderId", 400

#         group_id = deal_id.split("None")[-1][:14]  

#         deal_data = get_active_deal(deal_id)
#         if not deal_data:
#             print(f"No active deal found for deal_id: {deal_id}")
#             return "", 200

#         # Fetch buyer and seller information
#         buyer = await bot.get_chat(deal_data['buyer'])
#         seller = await bot.get_chat(deal_data['seller'])

#         # Process the status
#         status = data.get("status")
#         if status == "Waiting":
#             await bot.send_message(
#                 chat_id=group_id,
#                 text=f"💳 Payment initiated by <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\nWaiting for deposit...",
#                 parse_mode='HTML'
#             )

#         elif status == "Confirming":
#             await bot.send_message(
#                 chat_id=group_id,
#                 text=f"🔄 Payment is being confirmed for <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>",
#                 parse_mode='HTML'
#             )

#         elif status == "Paid":
#             update_active_deal(deal_id, {
#                 'status': 'deposited',
#                 'payment_time': datetime.now().isoformat()
#             })
#             try:
#                 await bot.delete_message(
#                     chat_id=group_id,
#                     message_id=data.get("message_id")  
#                 )
#             except:
#                 pass
            
#             from handlers import calculate_fee
#             amount = deal_data['amount']
#             fee = calculate_fee(amount, deal_data['deal_type'])
#             total = amount + fee

#             keyboard = [  
#                 [InlineKeyboardButton("💰 Release Payment", callback_data="release_payment")],  
#                 [InlineKeyboardButton("⏳ Check Timer", callback_data="check_timer")],  
#                 [InlineKeyboardButton("👨‍💼 Involve Moderator", callback_data="mod")],  
#                 [InlineKeyboardButton("🚫 End Deal", callback_data="back")]  
#             ]
#             reply_markup = InlineKeyboardMarkup(keyboard)

#             sent_message = await bot.send_message(
#                 chat_id=group_id,
#                 text=(
#                     f"<b>⚠️ FLUXX ESCROW BOT - PAYMENT CONFIRMED ✅</b>\n\n"
#                     f"💵 <b>Deposit Amount:</b> ${amount:.2f}\n"
#                     f"✅ <b>Payment confirmed from:</b> <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
#                     f"🔄 <b>Escrow Fee:</b> ${fee:.2f}\n"
#                     f"💰 <b>Total Amount:</b> ${total:.2f}\n\n"
#                     f"<b>⚠️ IMPORTANT INSTRUCTIONS:</b>\n"
#                     f"1. Ensure the transaction is fully completed before proceeding.\n"
#                     f"2. <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a> Verify that all items/services meet your expectations.\n"
#                     f"3. <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a> Only click 'Release Payment' if fully satisfied with the transaction.\n"
#                     f"4. If you encounter any issues, click 'Involve Moderator' immediately.\n\n"
#                     f"<b>🚫 Do NOT release payment before deal completion to avoid disputes.</b>\n"
#                     f"❗ All disputes or suspected scams will be investigated thoroughly.\n\n"
#                     f"<b>👥 Participants:</b>\n"
#                     f"🔹 <b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
#                     f"🔹 <b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>\n"
#                     f"<b>⏱ Time Remaining to Complete Trade: 60:00 Minutes</b> \n"
#                     f"⚠️ <i>Please complete the trade before the timer expires, or a moderator will be involved automatically.</i>"
#                 ),
#                 reply_markup=reply_markup,
#                 parse_mode='HTML'
#             )
#             asyncio.create_task(check_payment_timeout(bot, group_id, deal_id, sent_message.message_id))
#         elif status == "Expired":
#             await bot.send_message(
#                 chat_id=group_id,
#                 text=f"⚠️ Payment time expired for <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>",
#                 parse_mode='HTML'
#             )
#             remove_active_deal(deal_id)

#     except Exception as e:
#         print(f"Error in callback: {e}")
#         return "Internal Server Error", 500

#     return "ok", 200

# @app.route("/withdraw", methods=["POST"])
# async def withdraw_callback():
#     try:
#         # Parse the incoming data
#         data = await request.get_json()
#         print(f"Withdrawal Callback Data Received: {data}")

#         # Extract the necessary information
#         description = data.get("description", "")
#         seller_id = description.split()[-1]

#         status = data.get("status")
#         amount = data.get("amount")
#         currency = data.get("currency")

#         # Send update to seller
#         await send_withdrawal_update_to_seller(bot, seller_id, status, amount, currency)

#     except Exception as e:
#         print(f"Error in withdrawal callback: {e}")
#         return "Internal Server Error", 500

#     return "ok", 200

# async def check_payment_timeout(bot, group_id, deal_id, message_id):
#     """Check if payment has been released within 60 minutes"""
    
#     await asyncio.sleep(3600)  # 60 minutes in seconds
    
#     deal_data = get_active_deal(deal_id)
#     if not deal_data or deal_data['status'] != 'deposited':
#         return
        
#     buyer = await bot.get_chat(deal_data['buyer'])
#     seller = await bot.get_chat(deal_data['seller'])
    
#     # Alert group members
#     group_alert = (
#         "⚠️ <b>Payment Release Timeout</b>\n\n"
#         "60 minutes have passed without payment release.\n"
#         "A moderator has been automatically involved to assist.\n\n"
#         f"Buyer: <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
#         f"Seller: <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>"
#     )
    
#     await bot.send_message(
#         chat_id=group_id,
#         text=group_alert,
#         parse_mode='HTML'
#     )
    
#     # Alert moderator
#     mod_alert = (
#         "<b>⚠️ Payment Release Timeout Alert</b>\n\n"
#         f"Buyer: <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
#         f"Seller: <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>\n"
#         f"Amount: ${deal_data['amount']:.2f}\n"
#         f"Deal Type: {DEAL_TYPE_DISPLAY.get(deal_data['deal_type'], deal_data['deal_type'])}\n\n"
#         f"<a href='https://t.me/c/{str(group_id)[4:]}/{message_id}'>View Deal Message</a>\n\n"
#         "Please review this case immediately."
#     )
    
#     await bot.send_message(
#         chat_id=ADMIN_ID,
#         text=mod_alert,
#         parse_mode='HTML'
#     )

