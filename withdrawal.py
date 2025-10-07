import aiohttp
from config import *
from utils import *
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from remarks import ReviewSystem
import traceback
import json
import mexc_spot_v3

review_system = ReviewSystem()
wallet = mexc_spot_v3.mexc_wallet()

NETWORK_MAPPING = {
    'USDT_TRC20': {'currency': 'USDT', 'network': 'Tron(TRC20)', 'display_name': 'USDT (TRC20)'},
    'USDT_ERC20': {'currency': 'USDT', 'network': 'Ethereum(ERC20)', 'display_name': 'USDT (ERC20)'},
    'USDT_BEP20': {'currency': 'USDT', 'network': 'BNB Smart Chain(BEP20)', 'display_name': 'USDT (BEP20)'},
    'USDT_SOL': {'currency': 'USDT', 'network': 'Solana(SOL)', 'display_name': 'USDT (SOL)'},
    'USDT_MATIC': {'currency': 'USDT', 'network': 'Polygon(MATIC)', 'display_name': 'USDT (MATIC)'},
    'USDT_TON': {'currency': 'USDT', 'network': 'Toncoin(TON)', 'display_name': 'USDT (TON)'},
    'BTC': {'currency': 'BTC', 'network': 'Bitcoin(BTC)', 'display_name': 'BTC'},
    'ETH': {'currency': 'ETH', 'network': 'Ethereum(ERC20)', 'display_name': 'ETH'},
    'XRP': {'currency': 'XRP', 'network': 'Ripple(XRP)', 'display_name': 'XRP'},
    'DOGE': {'currency': 'DOGE', 'network': 'Dogecoin(DOGE)', 'display_name': 'DOGE'},
    'SOL': {'currency': 'SOL', 'network': 'Solana(SOL)', 'display_name': 'SOL'},
    'LTC': {'currency': 'LTC', 'network': 'Litecoin(LTC)', 'display_name': 'LTC'},
    'TON': {'currency': 'TON', 'network': 'Toncoin(TON)', 'display_name': 'TON'},
    'BNB': {'currency': 'BNB', 'network': 'BNB Smart Chain(BEP20)', 'display_name': 'BNB'},
    'TRX': {'currency': 'TRX', 'network': 'Tron(TRC20)', 'display_name': 'TRX'}
}
def log_error(function_name, error, additional_info=None):
    """Enhanced error logging function"""
    error_msg = f"[{function_name}] ERROR: {str(error)}"
    if additional_info:
        error_msg += f" | Additional Info: {additional_info}"
    print(error_msg)
    print(f"[{function_name}] Traceback: {traceback.format_exc()}")
    return error_msg

def load_fees_json():
    """Load fees from fees.json"""
    try:
        with open('fees.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading fees.json: {e}")
        return []

async def get_withdraw_fee(coin, network):
    """Get withdraw fee from fees.json"""
    fees_data = load_fees_json()
    for entry in fees_data:
        if entry['coin'] == coin and entry['network'] == network:
            return float(entry['withdrawFee'])
    return None

async def convert_usd_to_coin(coin, usd_amount):
    """Convert USD amount to coin amount using current price"""
    try:
        if coin.upper() == 'USDT':
            return usd_amount
        
        url = f"https://min-api.cryptocompare.com/data/price?fsym={coin.upper()}&tsyms=USD"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'USD' in data:
                        price = float(data['USD'])
                        if price == 0:
                            return None
                        coin_amount = usd_amount / price
                        print(f"Converted ${usd_amount} to {coin_amount:.8f} {coin} at rate ${price}")
                        return coin_amount
                    return None
                return None
                
    except Exception as e:
        print(f"Error converting USD to {coin}: {e}")
        return None

async def create_mexc_withdrawal(coin, network, address, amount, memo=None, withdraw_order_id=None, remark=None):
    """Create withdrawal using MEXC API"""
    try:
        params = {
            "coin": coin,
            "network": network,
            "address": address,
            "amount": str(amount)
        }
        
        if memo:
            params["memo"] = memo
        if withdraw_order_id:
            params["withdrawOrderId"] = withdraw_order_id
        if remark:
            params["remark"] = remark

        print(f"[create_mexc_withdrawal] Request params: {params}")
        
        result = wallet.post_withdraw(params)
        print(f"[create_mexc_withdrawal] Response: {result}")
        return result
        
    except Exception as e:
        log_error("create_mexc_withdrawal", e, f"coin: {coin}, network: {network}, amount: {amount}")
        return {"success": False, "error": str(e)}

async def handle_release_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment release - directly ask for address with structured message"""
    try:
        query = update.callback_query if update.callback_query else None
        message = query.message if query else update.effective_message
        group_id = message.chat.id

        active_deals = get_all_active_deals()
        deal_id = None
        deal_data = None
        
        if query and query.data.startswith('release_payment_'):
            deal_id = query.data.split('_')[-1]
            deal_data = get_active_deal(deal_id)
        else:
            for d_id, deal in active_deals.items():
                if deal['group_id'] == group_id and deal['status'] == 'deposited':
                    deal_id = d_id
                    deal_data = deal
                    break

        if not deal_data:
            error_msg = "❌ No active deposited deal found"
            if query:
                await query.answer(error_msg, show_alert=True)
            else:
                await message.reply_text(error_msg)
            return

        releaser = 'seller' if deal_data['deal_type'] == 'p2p' else 'buyer'
        if query.from_user.id != deal_data[releaser]:
            await query.answer(f"❌ Only the {releaser} can release payment", show_alert=True)
            return

        coin = deal_data.get('deposited_coin')
        network = deal_data.get('deposited_network')
        
        if not coin or not network:
            await query.answer("❌ No deposit coin/network found", show_alert=True)
            return

        withdraw_fee = await get_withdraw_fee(coin, network)
        if withdraw_fee is None:
            await query.answer("❌ Could not get withdrawal fee", show_alert=True)
            return

        releaser_id = deal_data[releaser]
        receiver_role = 'buyer' if releaser == 'seller' else 'seller'
        receiver_id = deal_data[receiver_role]
        
        releaser_chat = await context.bot.get_chat(releaser_id)
        receiver_chat = await context.bot.get_chat(receiver_id)
        releaser_name = releaser_chat.first_name
        receiver_name = receiver_chat.first_name

        context.user_data['state'] = "AWAITING_RELEASE_ADDRESS"
        context.user_data['deal_id'] = deal_id
        context.user_data['coin'] = coin
        context.user_data['network'] = network

        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        prompt_msg = await query.edit_message_text(
            f"<b>PAYMENT RELEASED BY {releaser_name}</b>\n"
            f"<b>COIN: {coin}</b>\n"
            f"<b>NETWORK: {network}</b>\n"
            f"<b>FEE: {withdraw_fee} {coin}</b>\n"
            f"<a href='tg://user?id={receiver_id}'>{receiver_name}</a> please reply with your withdrawal address for {coin} on {network}.\n\n"
            f"<pre>⚠️ Reply to this message with the address</pre>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        context.user_data['prompt_message_id'] = prompt_msg.message_id
        
    except Exception as e:
        log_error("handle_release_payment", e)
        await query.answer(f"❌ Error: {str(e)}", show_alert=True)

async def show_release_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, deal_data, coin, network, address, memo=None):
    """Show confirmation before withdrawal"""
    try:
        message = update.effective_message
        group_id = message.chat.id
        
        releaser = 'seller' if deal_data['deal_type'] == 'p2p' else 'buyer'
        receiver_role = 'buyer' if releaser == 'seller' else 'seller'
        receiver_id = deal_data[receiver_role]
        receiver = await context.bot.get_chat(receiver_id)
        receiver_name = receiver.first_name
        
        amount_usd = deal_data['amount']
        withdraw_fee = await get_withdraw_fee(coin, network)
        if withdraw_fee is None:
            await message.reply_text("❌ Could not get withdrawal fee.")
            return
        
        memo_text = f"\nMEMO: {memo}" if memo else ""
        
        text = (
            f"<b>PAYMENT RELEASED TO {receiver_name}</b>\n"
            f"<b>COIN: {coin}</b>\n"
            f"<b>NETWORK: {network}<b>\n"
            f"<b>AMOUNT: ${amount_usd:.2f}<b>\n"
            f"<b>FEES: {withdraw_fee} {coin}<b><pre>{memo_text}</pre>"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_release_{deal_data['deal_id']}")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_release")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(text, reply_markup=reply_markup)
        
        context.user_data['address'] = address
        context.user_data['memo'] = memo
        
    except Exception as e:
        log_error("show_release_confirmation", e)
        await message.reply_text(f"❌ Error: {str(e)}")

async def handle_confirm_release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation and perform withdrawal"""
    query = update.callback_query
    deal_id = query.data.split('_')[-1]
    deal_data = get_active_deal(deal_id)
    
    if not deal_data:
        await query.answer("❌ Deal not found", show_alert=True)
        return
    
    releaser = 'seller' if deal_data['deal_type'] == 'p2p' else 'buyer'
    if query.from_user.id != deal_data[releaser]:
        await query.answer(f"❌ Only the {releaser} can confirm release", show_alert=True)
        return
    
    coin = deal_data.get('deposited_coin')
    network = deal_data.get('deposited_network')
    address = context.user_data.get('address')
    memo = context.user_data.get('memo')
    
    amount_usd = deal_data['amount']
    coin_amount = amount_usd if coin.upper() == 'USDT' else await convert_usd_to_coin(coin, amount_usd)
    
    if coin_amount is None:
        await query.answer("❌ Error converting amount", show_alert=True)
        return
    
    result = await create_mexc_withdrawal(coin, network, address, coin_amount, memo)
    
    if result.get('success', False):
        update_active_deal(deal_id, {'status': 'completed'})
        
        receiver_role = 'buyer' if releaser == 'seller' else 'seller'
        receiver_id = deal_data[receiver_role]
        receiver = await context.bot.get_chat(receiver_id)
        
        withdraw_fee = await get_withdraw_fee(coin, network)
        fee_text = f"{withdraw_fee} {coin}" if withdraw_fee is not None else "N/A"
        memo_text = f"\nMEMO: {memo}" if memo else ""
        
        success_text = (
            f"PAYMENT RELEASED TO {receiver.first_name}\n"
            f"COIN: {coin}\n"
            f"NETWORK: {network}\n"
            f"AMOUNT: ${amount_usd:.2f}\n"
            f"FEES: {fee_text}{memo_text}"
        )
        
        await query.edit_message_text(success_text)
        
    else:
        error = result.get('error', 'Unknown error')
        await query.answer(f"❌ Withdrawal failed: {error}", show_alert=True)

async def handle_back_release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back from confirmation"""
    query = update.callback_query
    deal_id = context.user_data.get('deal_id')
    deal_data = get_active_deal(deal_id)
    
    if not deal_data:
        await query.edit_message_text("❌ Deal not found.")
        return
    
    coin = deal_data.get('deposited_coin')
    network = deal_data.get('deposited_network')
    
    context.user_data['state'] = "AWAITING_RELEASE_ADDRESS"
    context.user_data.pop('address', None)
    context.user_data.pop('memo', None)
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    prompt_msg = await query.edit_message_text(
        f"Please reply with your withdrawal address for {coin} on {network}.\n"
        f"⚠️ Reply to this message with the address.",
        reply_markup=reply_markup
    )
    context.user_data['prompt_message_id'] = prompt_msg.message_id