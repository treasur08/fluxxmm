import aiohttp
from config import *
from utils import *
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from remarks import ReviewSystem
import traceback

review_system = ReviewSystem()

WITHDRAWAL_FEES = {
    "LTC": 0.12,
    "ETH": 2.18,
    "DOGE": 0.16,
    "USDT": 0.28,
    "TON": 0.16,
    "POL": 0.16,
    "TRX": 0.28,
    'SOL': 0.40,
    "BTC": 2.89
}

# Fixed and more explicit network mapping
NETWORK_MAPPING = {
    "BTC": {"currency": "BTC", "network": "Bitcoin", "display_name": "Bitcoin"},
    "LTC": {"currency": "LTC", "network": "litecoin", "display_name": "Litecoin"},
    "ETH": {"currency": "ETH", "network": "ERC20", "display_name": "Ethereum"},
    "DOGE": {"currency": "DOGE", "network": "dogecoin", "display_name": "Dogecoin"},
    "USDT_BEP20": {"currency": "USDT", "network": "BEP20", "display_name": "USDT (BEP20)"},
    "USDT_TON": {"currency": "USDT", "network": "TON", "display_name": "USDT (TON)"},
    "TON": {"currency": "TON", "network": "ton", "display_name": "TON"},
    "POL": {"currency": "POL", "network": "polygon", "display_name": "Polygon"},
    "TRX": {"currency": "TRX", "network": "TRC20", "display_name": "TRON"},
    "SOL": {"currency": "SOL", "network": "solana", "display_name": "Solana"}
}

COIN_KEYBOARD = [
    [InlineKeyboardButton("Bitcoin", callback_data="coin_BTC"),
     InlineKeyboardButton("Ethereum", callback_data="coin_ETH")],
    [InlineKeyboardButton("TON", callback_data="coin_TON"),
     InlineKeyboardButton("SOL", callback_data="coin_SOL"),
     InlineKeyboardButton("LTC", callback_data="coin_LTC")],
    [InlineKeyboardButton("USDT (TON)", callback_data="coin_USDT_TON"),
     InlineKeyboardButton("USDT (BEP20)", callback_data="coin_USDT_BEP20")],
    [InlineKeyboardButton("POL", callback_data="coin_POL"),
     InlineKeyboardButton("DOGE", callback_data="coin_DOGE")]
]

def log_error(function_name, error, additional_info=None):
    """Enhanced error logging function"""
    error_msg = f"[{function_name}] ERROR: {str(error)}"
    if additional_info:
        error_msg += f" | Additional Info: {additional_info}"
    print(error_msg)
    print(f"[{function_name}] Traceback: {traceback.format_exc()}")
    return error_msg

def get_coin_info(selected_coin):
    """
    Get currency and network info for a selected coin with proper error handling
    
    Args:
        selected_coin: The coin identifier (e.g., 'BTC', 'USDT_TON')
    
    Returns:
        dict: Contains currency, network, and display_name or None if invalid
    """
    try:
        if not selected_coin:
            print(f"[get_coin_info] ERROR: selected_coin is None or empty")
            return None
            
        if selected_coin not in NETWORK_MAPPING:
            print(f"[get_coin_info] ERROR: selected_coin '{selected_coin}' not found in NETWORK_MAPPING")
            print(f"[get_coin_info] Available coins: {list(NETWORK_MAPPING.keys())}")
            return None
            
        coin_info = NETWORK_MAPPING[selected_coin]
        print(f"[get_coin_info] SUCCESS: {selected_coin} -> {coin_info}")
        return coin_info
        
    except Exception as e:
        log_error("get_coin_info", e, f"selected_coin: {selected_coin}")
        return None

async def create_payout(amount, address, currency, network, seller_id, memo=None):
    """Create payout with enhanced error handling"""
    try:
        url = "https://api.oxapay.com/api/send"
        headers = {
            "Authorization": f"Bearer {OXAPAY_PAYOUT_KEY}",
            "Content-Type": "application/json"
        }
        
        # Special handling for TON network
        if network.upper() == "TON" and currency == "USDT":
            network = "Ton"

        payload = {
            "key": OXAPAY_PAYOUT_KEY,
            "amount": str(amount),
            "currency": currency,
            "network": network.lower(),
            "address": address,
            "description": f"Withdrawal to {seller_id}",
            "callbackUrl": f"{WEBHOOK_URL}/withdraw"
        }
        
        if memo:
            payload["memo"] = memo

        print(f"[create_payout] Payout Request Data: {payload}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                result = await response.json()
                print(f"[create_payout] Payout Response: {result}")
                return result
                
    except Exception as e:
        error_msg = log_error("create_payout", e, f"amount: {amount}, currency: {currency}, network: {network}")
        return {"result": 0, "message": f"Payout creation failed: {str(e)}"}

async def handle_release_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment release with enhanced error handling"""
    try:
        query = update.callback_query
        message = query.message
        group_id = message.chat.id

        # Find active deal
        active_deals = get_all_active_deals()
        deal_id = None
        deal_data = None
        
        for d_id, deal in active_deals.items():
            if deal['group_id'] == group_id:
                deal_id = d_id
                deal_data = deal
                break

        if not deal_id or not deal_data:
            await query.edit_message_text("❌ No active deal found for this group.")
            return

        # Permission checks
        if query.from_user.id == deal_data['seller']:
            await query.answer("❌ Sellers cannot release the payment", show_alert=True)
            return

        if query.from_user.id != deal_data['buyer'] and str(query.from_user.id) != ADMIN_ID:
            await query.answer("❌ Only the buyer or admin can release the payment", show_alert=True)
            return

        # Status checks
        if deal_data.get('refund_status') == 'initiated':
            await query.answer("❌ Refund is in process on this deal", show_alert=True)
            return
            
        if deal_data.get('refund_status') == 'completed':
            await query.edit_message_text("❌ This deal was ended due to buyer getting refunded")
            return
            
        if deal_data.get('status') == 'completed':
            await query.edit_message_text("ℹ️ This deal has ended")
            return
        
        if deal_data.get('status') == 'released':
            await query.answer("⚠️ Payment release button has been clicked already", show_alert=True)
            return

        # Update deal status
        deal_data['status'] = 'released'
        update_active_deal(deal_id, {'status': 'released'})
        
        # Get seller info
        seller = await context.bot.get_chat(deal_data['seller'])
        seller_link = f'<a href="tg://user?id={seller.id}">{seller.first_name}</a>'
        
        # Show coin selection
        reply_markup = InlineKeyboardMarkup(COIN_KEYBOARD)
        await query.edit_message_text(
            f"<b>Dear {seller_link}, please select your preferred withdrawal currency:</b>\n\n"
            "Available networks for USDT:\n"
            "• TON Network\n"
            "• BEP20 (BSC)\n\n"
            "⚠️ Please select carefully as this cannot be changed after confirmation.",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        await query.answer()
        
    except Exception as e:
        error_msg = log_error("handle_release_payment", e)
        try:
            # Add rollback button on error
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await query.edit_message_text(
                f"❌ Error occurred: {str(e)}\n\nClick below to return to coin selection.",
                reply_markup=rollback_markup
            )
        except:
            await query.answer(f"❌ Error occurred: {str(e)}", show_alert=True)

async def handle_coin_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle coin selection with enhanced error handling"""
    try:
        query = update.callback_query
        message = query.message
        group_id = message.chat.id
        
        # Find active deal
        active_deals = get_all_active_deals()
        deal_id = None
        deal_data = None
        
        for d_id, deal in active_deals.items():
            if deal['group_id'] == group_id:
                deal_id = d_id
                deal_data = deal
                break

        if not deal_id or not deal_data:
            await query.edit_message_text("❌ No active deal found for this group.")
            return

        # Permission check
        if query.from_user.id != deal_data['seller']:
            await query.answer("❌ Only the seller can select the withdrawal currency", show_alert=True)
            return

        # Validate callback data
        if not query.data or not query.data.startswith("coin_"):
            await query.edit_message_text("❌ Invalid coin selection. Please try again.")
            return

        # Extract selected coin
        selected_coin = query.data.replace("coin_", "")
        print(f"[handle_coin_selection] Selected coin: {selected_coin}")
        
        # Get coin information
        coin_info = get_coin_info(selected_coin)
        if not coin_info:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await query.edit_message_text(
                f"❌ Invalid coin selection: '{selected_coin}'\n\n"
                "Please select a valid cryptocurrency.",
                reply_markup=rollback_markup
            )
            return

        # Check minimum amount for expensive coins
        if selected_coin in ['BTC', 'ETH'] and deal_data['amount'] < 3:
            await query.answer(f"❌ Minimum deal amount for {coin_info['display_name']} is $3", show_alert=True)
            return

        # Update deal data
        deal_data['selected_coin'] = selected_coin
        deal_data['currency'] = coin_info['currency']
        deal_data['network'] = coin_info['network']
        
        update_active_deal(deal_id, {
            'selected_coin': selected_coin,
            'currency': coin_info['currency'],
            'network': coin_info['network']
        })

        print(f"[handle_coin_selection] Updated deal data: selected_coin={selected_coin}, "
              f"currency={coin_info['currency']}, network={coin_info['network']}")

        # Get seller info
        seller = await context.bot.get_chat(deal_data['seller'])
        seller_link = f'<a href="tg://user?id={seller.id}">{seller.first_name}</a>'

        # Prompt for wallet address with rollback button
        rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
        rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
        
        msg = await query.edit_message_text(
            f"<b>✅ Selected: {coin_info['display_name']}</b>\n"
            f"<b>Network: {coin_info['network']}</b>\n\n"
            f"Please {seller_link}, reply to this message with your wallet address for withdrawal:\n\n"
            f"⚠️ Make sure the address is correct for the {coin_info['network']} network.\n"
            f"⚠️ You must REPLY to this message with your address.",
            reply_markup=rollback_markup,
            parse_mode="HTML"
        )
        
        context.user_data["prompt_message_id"] = msg.message_id
        context.user_data['state'] = "AWAITING_WALLET"
        await query.answer()
        
    except Exception as e:
        error_msg = log_error("handle_coin_selection", e, f"query.data: {getattr(query, 'data', 'None')}")
        try:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await query.edit_message_text(
                f"❌ Error occurred during coin selection: {str(e)}",
                reply_markup=rollback_markup
            )
        except:
            await query.answer(f"❌ Error occurred: {str(e)}", show_alert=True)

async def handle_wallet_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle wallet address input with enhanced error handling and reply validation"""
    try:
        # Check if user replied to the bot's prompt message
        prompt_message_id = context.user_data.get("prompt_message_id")
        if not update.message.reply_to_message or update.message.reply_to_message.message_id != prompt_message_id:
            await update.message.reply_text(
                "⚠️ Please reply directly to the bot's wallet address prompt message above."
            )
            return

        # Find active deal for this seller
        active_deals = get_all_active_deals()
        deal_id = None
        deal_data = None
        
        for d_id, deal in active_deals.items():
            if deal.get('seller') == update.message.from_user.id:
                deal_id = d_id
                deal_data = deal
                break

        # Clean up prompt message
        if prompt_message_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=prompt_message_id
                )
            except:
                pass

        if not deal_data:
            context.user_data.clear()
            context.user_data['state'] = None
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await update.message.reply_text(
                "❌ No active deal found. Please start over.",
                reply_markup=rollback_markup
            )
            return

        # Permission check
        if update.message.from_user.id != deal_data['seller']:
            return

        wallet_address = update.message.text.strip()
        
        # Validate wallet address is not empty
        if not wallet_address:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await update.message.reply_text(
                "❌ Please enter a valid wallet address.",
                reply_markup=rollback_markup
            )
            return

        # Check if coin selection data exists
        if 'selected_coin' not in deal_data:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await update.message.reply_text(
                "❌ Coin selection data missing. Please start over.",
                reply_markup=rollback_markup
            )
            return

        selected_coin = deal_data['selected_coin']
        print(f"[handle_wallet_address] Processing wallet for coin: {selected_coin}")

        # Check if memo is required (TON and USDT_TON)
        if selected_coin in ['USDT_TON', 'TON']:
            context.user_data['state'] = 'AWAITING_MEMO'
            context.user_data['wallet_address'] = wallet_address
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            msg = await update.message.reply_text(
                "📝 Please reply to this message with the memo tag for this wallet address.\n\n"
                "If a memo tag is not required, type `skip`\n\n"
                "⚠️ You must REPLY to this message with your memo.",
                reply_markup=rollback_markup,
                parse_mode="Markdown"
            )
            context.user_data["prompt_message_id"] = msg.message_id
            return

        # Process withdrawal directly if no memo needed
        await process_withdrawal(update, context, wallet_address)
        
    except Exception as e:
        error_msg = log_error("handle_wallet_address", e)
        rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
        rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
        await update.message.reply_text(
            f"❌ Error processing wallet address: {str(e)}",
            reply_markup=rollback_markup
        )
        context.user_data.clear()
        context.user_data['state'] = None

async def handle_memo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle memo input with enhanced error handling and reply validation"""
    try:
        if context.user_data.get('state') != 'AWAITING_MEMO':
            context.user_data.clear()
            context.user_data['state'] = None
            return

        # Check if user replied to the bot's prompt message
        prompt_message_id = context.user_data.get("prompt_message_id")
        if not update.message.reply_to_message or update.message.reply_to_message.message_id != prompt_message_id:
            await update.message.reply_text(
                "⚠️ Please reply directly to the bot's memo prompt message above."
            )
            return

        # Clean up prompt message
        if prompt_message_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=prompt_message_id
                )
            except:
                pass

        memo = update.message.text.strip()
        wallet_address = context.user_data.get('wallet_address')

        if not wallet_address:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await update.message.reply_text(
                "❌ Wallet address missing. Please start over.",
                reply_markup=rollback_markup
            )
            context.user_data.clear()
            context.user_data['state'] = None
            return

        # Handle skip memo
        if memo.lower() == 'skip':
            memo = None

        await process_withdrawal(update, context, wallet_address, memo)
        
    except Exception as e:
        error_msg = log_error("handle_memo_input", e)
        rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
        rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
        await update.message.reply_text(
            f"❌ Error processing memo: {str(e)}",
            reply_markup=rollback_markup
        )
        context.user_data.clear()
        context.user_data['state'] = None

async def process_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE, wallet_address, memo=None):
    """Process withdrawal with comprehensive error handling"""
    try:
        # Clear user state
        context.user_data.clear()
        context.user_data['state'] = None

        # Find active deal
        active_deals = get_all_active_deals()
        deal_id = None
        deal_data = None
        
        for d_id, deal in active_deals.items():
            if deal.get('seller') == update.message.from_user.id:
                deal_id = d_id
                deal_data = deal
                break

        if not deal_data:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await update.message.reply_text(
                "❌ No active deal found. Please start over.",
                reply_markup=rollback_markup
            )
            return

        # Validate required data
        if 'selected_coin' not in deal_data:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await update.message.reply_text(
                "❌ Coin selection missing. Please start over.",
                reply_markup=rollback_markup
            )
            return

        selected_coin = deal_data['selected_coin']
        coin_info = get_coin_info(selected_coin)
        
        if not coin_info:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await update.message.reply_text(
                f"❌ Invalid coin data: '{selected_coin}'. Please start over.",
                reply_markup=rollback_markup
            )
            return

        # Calculate amounts
        from handlers import calculate_fee
        from convert import exchange_rate

        amount = deal_data['amount']
        fee = calculate_fee(amount, deal_data['deal_type'])
        payout_amount = amount - fee

        currency = coin_info['currency']
        network = coin_info['network']
        withdrawal_fee = WITHDRAWAL_FEES.get(currency, 0)
        payout_amount_after_fee = payout_amount - withdrawal_fee

        print(f"[process_withdrawal] Calculations: amount={amount}, fee={fee}, "
              f"payout_amount={payout_amount}, withdrawal_fee={withdrawal_fee}, "
              f"final_amount_before_conversion={payout_amount_after_fee}")

        # Handle currency conversion
        if currency != "USDT":
            try:
                exchange_result = exchange_rate(payout_amount_after_fee, currency)
                print(f"[process_withdrawal] Exchange rate result: {exchange_result}")
                
                if isinstance(exchange_result, dict) and exchange_result.get('result') == 100:
                    final_payout_amount = float(exchange_result['toAmount'])
                else:
                    error_msg = exchange_result.get('message', 'Unknown exchange error') if isinstance(exchange_result, dict) else str(exchange_result)
                    rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
                    rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
                    await update.message.reply_text(
                        f"❌ Exchange rate calculation failed: {error_msg}",
                        reply_markup=rollback_markup
                    )
                    return
            except Exception as e:
                log_error("process_withdrawal", e, "Exchange rate calculation")
                rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
                rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
                await update.message.reply_text(
                    f"❌ Error calculating exchange rate: {str(e)}",
                    reply_markup=rollback_markup
                )
                return
        else:
            final_payout_amount = payout_amount_after_fee

        # Validate final amount
        if final_payout_amount <= 0:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await update.message.reply_text(
                f"❌ Final payout amount is too low: {final_payout_amount:.6f} {currency}\n"
                f"This may be due to high network fees. Please try a different cryptocurrency.",
                reply_markup=rollback_markup
            )
            return

        # Prepare payout request
        payout_request = {
            "amount": final_payout_amount,
            "address": wallet_address,
            "currency": currency,
            "network": network,
            "seller_id": deal_data['seller']
        }
        
        if memo:
            payout_request["memo"] = memo

        print(f"[process_withdrawal] Final payout request: {payout_request}")

        # Show confirmation with rollback option
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Proceed", callback_data="confirm_withdrawal"),
             InlineKeyboardButton("✏️ No, Edit", callback_data="edit_withdrawal")],
            [InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        confirmation_message = (
            "★━━━━━━━━━━★\n"
            "┃ 𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘  \n"
            "★━━━━━━━━━━★\n\n"
            "📤 *Withdrawal Details*\n\n"
            f"💰 *Amount:* `{final_payout_amount:.6f} {currency}`\n"
            f"🌐 *Network:* `{network}`\n"
            f"📍 *Address:* `{wallet_address}`\n"
            f"💸 *Network Fee:* `{withdrawal_fee} {currency}`\n"
        )
        
        if memo:
            confirmation_message += f"🔖 *Memo:* `{memo}`\n"
            
        confirmation_message += (
            "\n⚠️ Please review and confirm the above details carefully.\n"
            "Once confirmed, this transaction cannot be reversed.\n\n"
            "Do you want to proceed?"
        )

        await update.message.reply_text(
            confirmation_message, 
            reply_markup=reply_markup, 
            parse_mode="Markdown"
        )
        context.user_data['payout_request'] = payout_request
        
    except Exception as e:
        error_msg = log_error("process_withdrawal", e)
        rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
        rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
        await update.message.reply_text(
            f"❌ Error processing withdrawal: {str(e)}",
            reply_markup=rollback_markup
        )
        context.user_data.clear()
        context.user_data['state'] = None

async def handle_confirm_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal confirmation with enhanced error handling"""
    try:
        query = update.callback_query
        message = query.message
        group_id = message.chat.id
        
        # Find active deal
        active_deals = get_all_active_deals()
        deal_id = None
        deal_data = None
        
        for d_id, deal in active_deals.items():
            if deal['group_id'] == group_id:
                deal_id = d_id
                deal_data = deal
                break

        if not deal_data:
            await query.edit_message_text("❌ No active deal found for this group.")
            return

        # Permission check
        if query.from_user.id != deal_data['seller']:
            await query.answer("❌ Only the seller can confirm the withdrawal", show_alert=True)
            return

        # Get payout request
        payout_request = context.user_data.get('payout_request')
        if not payout_request:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await query.edit_message_text(
                "❌ Withdrawal information not found. Please start over.",
                reply_markup=rollback_markup
            )
            return

        print(f"[handle_confirm_withdrawal] Processing payout: {payout_request}")

        # Handle currency conversion if needed
        currency = payout_request['currency']
        if currency != "USDT":
            try:
                from convert import request_exchange
                amount = deal_data['amount']
                from handlers import calculate_fee
                fee = calculate_fee(amount, deal_data['deal_type'])
                payout_amount = amount - fee
                
                exchange_request = request_exchange(payout_amount, "USDT", currency)
                if not isinstance(exchange_request, dict) or 'result' not in exchange_request:
                    rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
                    rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
                    await query.edit_message_text(
                        "❌ Currency conversion failed. Please try again.",
                        reply_markup=rollback_markup
                    )
                    return
            except Exception as e:
                log_error("handle_confirm_withdrawal", e, "Currency conversion")
                rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
                rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
                await query.edit_message_text(
                    f"❌ Currency conversion error: {str(e)}",
                    reply_markup=rollback_markup
                )
                return

        # Create payout
        payout_result = await create_payout(**payout_request)
        print(f"[handle_confirm_withdrawal] Payout result: {payout_result}")
        
        if payout_result.get('result') == 100:
            # Success
            seller = await context.bot.get_chat(deal_data['seller'])
            keyboard = [[InlineKeyboardButton(f"🟢 Confirm Payment Received", callback_data="seller_confirm_paid")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"🌟 *Withdrawal Successfully Initiated*\n\n"
                f"💰 Amount: `{payout_request['amount']:.6f} {payout_request['currency']}`\n"
                f"🌐 Network: `{payout_request['network']}`\n"
                f"📝 Address: `{payout_request['address']}`\n"
                f"{'🔖 Memo: `' + payout_request.get('memo', '') + '`' if payout_request.get('memo') else ''}\n\n"
                f"_Please {seller.first_name}, confirm once you have received the funds in your wallet._",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            # Failure
            error_msg = payout_result.get('message', 'Unknown error occurred')
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            
            await query.edit_message_text(
                f"❌ *Withdrawal Failed*\n\n"
                f"Error: `{error_msg}`\n\n"
                f"Click below to start over with different details.",
                reply_markup=rollback_markup,
                parse_mode='Markdown'
            )
            
        context.user_data.clear()
        
    except Exception as e:
        error_msg = log_error("handle_confirm_withdrawal", e)
        try:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await query.edit_message_text(
                f"❌ Error confirming withdrawal: {str(e)}",
                reply_markup=rollback_markup
            )
        except:
            await query.answer(f"❌ Error occurred: {str(e)}", show_alert=True)
        context.user_data.clear()

# NEW: Handle rollback function
async def handle_rollback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle rollback to coin selection with enhanced error handling"""
    try:
        query = update.callback_query
        message = query.message
        group_id = message.chat.id

        # Find the active deal for this group
        active_deals = get_all_active_deals()
        deal_id = None
        deal_data = None
        
        for d_id, deal in active_deals.items():
            if deal['group_id'] == group_id:
                deal_id = d_id
                deal_data = deal
                break

        # Clear all user states and payout requests
        context.user_data.clear()
        context.user_data['state'] = None

        if not deal_id or not deal_data:
            await query.edit_message_text("❌ No active deal found to rollback.")
            return

        # Get seller info
        seller = await context.bot.get_chat(deal_data['seller'])
        seller_link = f'<a href="tg://user?id={seller.id}">{seller.first_name}</a>'
        
        # Show coin selection again
        reply_markup = InlineKeyboardMarkup(COIN_KEYBOARD)
        
        await query.edit_message_text(
            f"<b>Dear {seller_link}, please select your preferred withdrawal currency:</b>\n\n"
            "Available networks for USDT:\n"
            "• TON Network\n"
            "• BEP20 (BSC)\n\n"
            "⚠️ Please select carefully as this affects network fees and processing time.",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        
        await query.answer("🔄 Returned to coin selection")
        
    except Exception as e:
        error_msg = log_error("handle_rollback", e)
        try:
            await query.edit_message_text(f"❌ Error during rollback: {str(e)}")
        except:
            await query.answer(f"❌ Error occurred: {str(e)}", show_alert=True)

# Keep the existing edit and change functions with rollback buttons added...
async def handle_edit_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal editing with enhanced error handling"""
    try:
        query = update.callback_query
        message = query.message
        group_id = message.chat.id
        
        active_deals = get_all_active_deals()
        deal_id = None
        deal_data = None
        
        for d_id, deal in active_deals.items():
            if deal['group_id'] == group_id:
                deal_id = d_id
                deal_data = deal
                break

        if not deal_data:
            await query.edit_message_text("❌ No active deal found for this group.")
            return

        if query.from_user.id != deal_data['seller']:
            await query.answer("❌ Only the seller can edit the withdrawal", show_alert=True)
            return

        keyboard = [
            [InlineKeyboardButton("🪙 Change Coin", callback_data="change_coin"),
             InlineKeyboardButton("📍 Change Address", callback_data="change_address")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "What would you like to change?",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        error_msg = log_error("handle_edit_withdrawal", e)
        try:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await query.edit_message_text(
                f"❌ Error: {str(e)}",
                reply_markup=rollback_markup
            )
        except:
            await query.answer(f"❌ Error occurred: {str(e)}", show_alert=True)

async def handle_change_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle coin change with enhanced error handling"""
    try:
        query = update.callback_query
        message = query.message
        group_id = message.chat.id
        
        active_deals = get_all_active_deals()
        deal_id = None
        deal_data = None
        
        for d_id, deal in active_deals.items():
            if deal['group_id'] == group_id:
                deal_id = d_id
                deal_data = deal
                break

        if not deal_data:
            await query.edit_message_text("❌ No active deal found for this group.")
            return

        if query.from_user.id != deal_data['seller']:
            await query.answer("❌ Only the seller can edit the withdrawal", show_alert=True)
            return

        reply_markup = InlineKeyboardMarkup(COIN_KEYBOARD)
        await query.edit_message_text(
            "★━━━━━━━━━━★\n"
            "┃ 𝗘𝗦𝗖𝗥𝗢𝗪 𝗦𝗘𝗥𝗩𝗜𝗖𝗘  \n"
            "★━━━━━━━━━━★\n\n"
            "Please select a new coin for withdrawal:",
            reply_markup=reply_markup
        )
        await query.answer()
        
    except Exception as e:
        error_msg = log_error("handle_change_coin", e)
        try:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await query.edit_message_text(
                f"❌ Error: {str(e)}",
                reply_markup=rollback_markup
            )
        except:
            await query.answer(f"❌ Error occurred: {str(e)}", show_alert=True)

async def handle_change_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle address change with enhanced error handling"""
    try:
        query = update.callback_query
        message = query.message
        group_id = message.chat.id
        
        active_deals = get_all_active_deals()
        deal_id = None
        deal_data = None
        
        for d_id, deal in active_deals.items():
            if deal['group_id'] == group_id:
                deal_id = d_id
                deal_data = deal
                break

        if not deal_data:
            await query.edit_message_text("❌ No active deal found for this group.")
            return
            
        if query.from_user.id != deal_data['seller']:
            await query.answer("❌ Only the seller can edit the withdrawal", show_alert=True)
            return

        await query.answer()
        context.user_data['state'] = "AWAITING_WALLET"
        
        rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
        rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
        
        msg = await query.edit_message_text(
            "Please reply to this message with the new wallet address for withdrawal:\n\n"
            "⚠️ You must REPLY to this message with your address.",
            reply_markup=rollback_markup
        )
        context.user_data["prompt_message_id"] = msg.message_id
        
    except Exception as e:
        error_msg = log_error("handle_change_address", e)
        try:
            rollback_keyboard = [[InlineKeyboardButton("🔙 Back to Coin Selection", callback_data="rollback")]]
            rollback_markup = InlineKeyboardMarkup(rollback_keyboard)
            await query.edit_message_text(
                f"❌ Error: {str(e)}",
                reply_markup=rollback_markup
            )
        except:
            await query.answer(f"❌ Error occurred: {str(e)}", show_alert=True)
