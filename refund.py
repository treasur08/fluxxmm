from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ADMIN_ID
from utils import *

DEAL_TYPE_DISPLAY = {
    'b_and_s': 'Buy and Sell',
    'p2p': 'P2P Transfer'
}
kbd = [
    [InlineKeyboardButton("TON ₮", callback_data="refunds_TON"),
     InlineKeyboardButton("SOL ◎", callback_data="refunds_SOL")],
    [InlineKeyboardButton("LTC Ł", callback_data="refunds_LTC"),
     InlineKeyboardButton("USDT BSC ₮", callback_data="refunds_USDT")],
    [InlineKeyboardButton("POL ⚛", callback_data="refunds_POL"),
     InlineKeyboardButton("DOGE Ð", callback_data="refunds_DOGE")]
]
async def handle_refund(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    group_id = update.effective_chat.id
    
    if update.effective_chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("This command can only be used in a group.")
        return
    
    # Handle admin refund case
    is_admin = str(user_id) == ADMIN_ID
    if is_admin and update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user.id
    else:
        target_user = user_id

    # Find active deal in the group
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

    # Verify user authorization and deal status
    if not is_admin and user_id not in [deal_data['buyer'], deal_data['seller']]:
        await update.message.reply_text("You are not authorized to request a refund.")
        return

    if deal_data['status'] != 'deposited':
        await update.message.reply_text("Refund is only available for deals with deposited status.")
        return
    
    if deal_data.get('refund_status') == 'initiated':
        await update.message.reply_text("A refund has already been initiated for the ongoing deal.")
        return


    buyer = await context.bot.get_chat(deal_data['buyer'])
    seller = await context.bot.get_chat(deal_data['seller'])

    # If admin initiates refund for buyer
    if is_admin and target_user == deal_data['buyer']:
        
        reply_markup = InlineKeyboardMarkup(kbd)
        await update.message.reply_text(
            f"Admin initiated refund process for buyer {buyer.first_name}.\n"
            f"Please select your preferred coin for refund.",
            reply_markup=reply_markup
        )
        deal_data['refund_status'] = 'initiated'
        update_active_deal(deal_id, {'refund_status': 'initiated'})
        return

    # Regular refund process
    keyboard = [
        [
            InlineKeyboardButton("Yes ✅", callback_data="refund_agree"),
            InlineKeyboardButton("No ❌", callback_data="refund_deny")
        ],
        [InlineKeyboardButton("Involve Moderator 👮", callback_data="mod")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"<b>DEAL REFUND REQUEST</b>\n\n"
        f"<b>DEAL INFO</b>\n"
        f"BUYER: <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
        f"SELLER: <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>\n"
        f"DEAL TYPE: {DEAL_TYPE_DISPLAY.get(deal_data['deal_type'], deal_data['deal_type'])}\n\n"
        f"<a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a> is going to be refunded "
        f"an amount of ${deal_data['amount']}\n\n"
        f"<a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>, do you agree with this ordeal?",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

async def handle_refund_agreement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    active_deals = get_all_active_deals()
    deal_id = None
    for d_id, deal in active_deals.items():
        if deal['group_id'] == query.message.chat.id:
            deal_id = d_id
            deal_data = deal
            break

    if not deal_id:
        await query.answer("No active deal found.", show_alert=True)
        return

    if user_id != deal_data['seller']:
        await query.answer("Only the seller can respond to refund request.", show_alert=True)
        return

    if query.data == "refund_agree":
        if not deal_id:
            await query.edit_message_text("No active deal found.")
            return
        if deal_data['status'] != 'deposited':
                await query.answer("Refund is not available for Buyer at this Point", show_alert=True)
                return
                
        deal_data['refund_status'] = 'initiated'
        update_active_deal(deal_id, {'refund_status': 'initiated'})
        reply_markup = InlineKeyboardMarkup(kbd)
        await query.edit_message_text(
                "Seller has agreed to the refund.\n"
                "Buyer, please select your preferred coin for refund.",
                reply_markup=reply_markup
            )

    elif query.data == "refund_deny":
        keyboard = [[InlineKeyboardButton("Involve Moderator 👮", callback_data="mod")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Seller has denied the refund request.\n"
            "Please involve a moderator to resolve this issue.",
            reply_markup=reply_markup
        )
    await query.answer()

 

async def handle_refund_coin_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    coin = query.data.split("_")[1]
    active_deals = get_all_active_deals()
    deal_id = None
    for d_id, deal in active_deals.items():
        if deal['group_id'] == query.message.chat.id:
            deal_id = d_id
            deal_data = deal
            break
            
    if query.from_user.id != deal_data['buyer']:
        await query.answer("Only the buyer can select refund options", show_alert=True)
        return
        
    valid_coins = ['BTC', 'ETH', 'TON', 'SOL', 'LTC', 'USDT', 'POL', 'DOGE']
    if coin in valid_coins:
        context.user_data['selected_coin'] = coin
        context.user_data['state'] = 'AWAITING_REFUND_WALLET'
        context.user_data['deal_id'] = deal_id

        network = None
        if coin == 'USDT':
            network = 'BEP20'
        elif coin == 'ETH':
            network = "erc20"
        elif coin == "TON":
            network = 'Ton'
        elif coin == "SOL":
            network = 'solana'
        elif coin == 'POL':
            network = 'polygon'
        await query.edit_message_text(
            f"You selected {coin} for refund.\n"
            f"Please enter your {coin} wallet address:"
            + (f"\nNetwork: {network}" if network else ""),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="back")]])
        )
    else:
        await query.answer("Invalid coin selection", show_alert=True)

    await query.answer()

async def handle_refund_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet_address = update.message.text
    selected_coin = context.user_data.get('selected_coin')
    deal_id = context.user_data.get('deal_id')
    network = None
    if selected_coin == 'USDT':
        network = 'BEP20'
    elif selected_coin == 'ETH':
        network = 'erc20'
    elif selected_coin == 'TON':
        network = 'Ton'
    elif selected_coin == 'SOL':
        network = 'solana'
    elif selected_coin == 'POL':
        network = 'polygon'
    if not all([selected_coin, deal_id, network]):
        await update.message.reply_text("Missing required information. Please start the refund process again.")
        return

    deal_data = get_active_deal(deal_id)
    if not deal_data:
        await update.message.reply_text("The deal no longer exists. Please contact support.")
        return

    # Implement payout request
    payout_result = await request_payout(deal_data['amount'], selected_coin, wallet_address, network)
    
    if payout_result.get('result') == 100:
        await update.message.reply_text("Refund request successful! The funds will be sent to your wallet shortly.")
        
        # Update deal status
        deal_data['status'] = 'completed'
        deal_data['refund_status'] = 'completed'
        update_active_deal(deal_id, {'status': 'completed', 'refund_status': 'completed'})
        
        # Notify seller
        seller_id = deal_data['seller']
        await context.bot.send_message(
            chat_id=seller_id,
            text=f"The refund for deal {deal_id} has been processed and completed."
        )
    else:
        deal_data.pop('refund_status', None)
        update_active_deal(deal_id, {'refund_status': None})
        await update.message.reply_text("There was an error processing your refund. Please contact support.")

    # Clear user data
    context.user_data.clear()

import aiohttp
from config import OXAPAY_PAYOUT_KEY, WEBHOOK_URL

async def request_payout(amount, coin, address, network):
    url = "https://api.oxapay.com/api/send"
    headers = {
        "Authorization": f"Bearer {OXAPAY_PAYOUT_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "key": OXAPAY_PAYOUT_KEY,
        "amount": str(amount),
        "currency": coin,
        "network": network,
        "address": address,
        "callbackUrl": f"{WEBHOOK_URL}/withdraw"
    }

    print(f"Payout Request Data: {payload}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers) as response:
                response_data = await response.json()
                print(f"Payout Response: {response_data}")
                return response_data
        except Exception as e:
            print(f"Payout Error: {str(e)}")
            return {"error": str(e)}