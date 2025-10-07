import aiohttp
from config import OXAPAY_API_KEY, WEBHOOK_URL, DEFAULT_PAY_CURRENCY, DEFAULT_NETWORK, DEFAULT_CURRENCY, DEFAULT_LIFETIME, DEFAULT_FEE_PAID_BY_PAYER
from utils import *
from datetime import datetime, timedelta
import mexc_spot_v3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import DEAL_TYPE_DISPLAY
import asyncio

def load_fees():
    with open('config.json', 'r') as f:
        config = json.load(f)
    return config['p2p_fee'], config['bs_fee'], config['allfee']


coins = [
    {"text": "USDT (TRC20)", "coin": "USDT", "network": "Tron(TRC20)"},
    {"text": "BTC", "coin": "BTC", "network": "Bitcoin(BTC)"},
    {"text": "ETH", "coin": "ETH", "network": "Ethereum(ERC20)"},
    {"text": "USDT (BEP20)", "coin": "USDT", "network": "BNB Smart Chain(BEP20)"},
    {"text": "USDT (ERC20)", "coin": "USDT", "network": "Ethereum(ERC20)"},
    {"text": "USDT (SOL)", "coin": "USDT", "network": "Solana(SOL)"},
    {"text": "USDT (MATIC)", "coin": "USDT", "network": "Polygon(MATIC)"},
    {"text": "USDT (TON)", "coin": "USDT", "network": "Toncoin(TON)"},
    {"text": "USDT (OP)", "coin": "USDT", "network": "Optimism(OP)"},
    {"text": "USDT (ARB)", "coin": "USDT", "network": "Arbitrum One(ARB)"},
    {"text": "XRP", "coin": "XRP", "network": "Ripple(XRP)"},
    {"text": "SOLANA", "coin": "SOL", "network": "Solana(SOL)"},
    {"text": "LTC", "coin": "LTC", "network": "Litecoin(LTC)"},
    {"text": "TONCOIN", "coin": "TON", "network": "Toncoin(TON)"},
    {"text": "BNB", "coin": "BNB", "network": "BNB Smart Chain(BEP20)"},
    {"text": "Tron", "coin": "TRX", "network": "Tron(TRC20)"}
]

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

async def get_deposit_address(coin: str, network: str = None):
    wallet = mexc_spot_v3.mexc_wallet()
    params = {
        "coin": coin
    }
    if network:
        params["network"] = network
    try:
        deposit_address = wallet.get_deposit_address(params)
        print(f"Raw deposit address response: {deposit_address}")
        return deposit_address
    except Exception as e:
        print(f"Error getting deposit address from MEXC: {e}")
        print(f"Exception type: {type(e)}")
        return None


async def generate_deposit_address(coin: str, network: str = None):
    wallet = mexc_spot_v3.mexc_wallet()
    params = {
        "coin": coin
    }
    if network:
        params["network"] = network
    try:
        print(f"Generating deposit address for {coin} on network {network} with params: {params}")
        result = wallet.post_deposit_address(params)
        print(f"Generate deposit address result: {result}")
        print(f"Result type: {type(result)}")
        return result
    except Exception as e:
        print(f"Error generating deposit address from MEXC: {e}")
        print(f"Exception type: {type(e)}")
        if hasattr(e, 'response'):
            print(f"Response status: {getattr(e.response, 'status_code', 'N/A')}")
            print(f"Response text: {getattr(e.response, 'text', 'N/A')}")
        return None
    
async def handle_deposit_address_generation(deal_id, coin, network=None):
    try:
        print(f"Generating deposit address for coin: {coin}, network: {network}")
        
        generation_time = datetime.now().isoformat()

        address_data = await get_deposit_address(coin, network)
        print(f"Get deposit address response: {address_data}")
        
        # Fix: Check if address_data is a list and has items
        if address_data and isinstance(address_data, list) and len(address_data) > 0:
            address_info = address_data[0]
            if 'address' in address_info:
                deposit_info = {
                    'deposit_address': address_info['address'],
                    'selected_coin': coin,
                    'network': network,
                    'generation_time': generation_time
                }
                
                if 'memo' in address_info and address_info['memo']:
                    deposit_info['tag'] = address_info['memo']
                elif 'tag' in address_info and address_info['tag']:
                    deposit_info['tag'] = address_info['tag']
                    
                update_active_deal(deal_id, deposit_info)
                return address_info
        
        if not address_data or not isinstance(address_data, list) or len(address_data) == 0:
            print(f"No existing address found, generating new one for {coin} on {network}")
            address_data = await generate_deposit_address(coin, network)
            print(f"Generate deposit address result: {address_data}")
            
            if address_data and isinstance(address_data, dict) and 'address' in address_data:
                deposit_info = {
                    'deposit_address': address_data['address'],
                    'selected_coin': coin,
                    'network': network,
                    'generation_time': generation_time
                }
                
                if 'memo' in address_data and address_data['memo']:
                    deposit_info['tag'] = address_data['memo']
                elif 'tag' in address_data and address_data['tag']:
                    deposit_info['tag'] = address_data['tag']
                    
                update_active_deal(deal_id, deposit_info)
                return address_data
            else:
                error_msg = address_data.get('msg', 'Unknown error') if isinstance(address_data, dict) else "Unknown error"
                print(f"Failed to generate deposit address for {coin} on {network}: {error_msg}")
                return None
        
        return None
        
    except Exception as e:
        print(f"Error in handle_deposit_address_generation: {e}")
        return None

async def verify_payment_deposit(coin: str, deposit_address: str, expected_amount: float, deal_data: dict):
    try:
        wallet = mexc_spot_v3.mexc_wallet()
        
        params = {
            "coin": coin,
            "limit": "50",
        }
        
        start_time = None
        if 'generation_time' in deal_data:
            start_time = datetime.fromisoformat(deal_data['generation_time'])
            print(f"Using address generation time: {start_time}")
        elif 'timestamp' in deal_data:
            start_time = datetime.fromisoformat(deal_data['timestamp'])
            print(f"Using deal timestamp: {start_time}")
        
        if start_time:
            start_time_ms = int(start_time.timestamp() * 1000)
            params["startTime"] = str(start_time_ms)
        
        deposit_history = wallet.get_deposit_list(params)
        
        if not deposit_history or not isinstance(deposit_history, list):
            print("No deposit history found or invalid response format")
            return False
        
        for deposit in deposit_history:
            deposit_addr = deposit.get('address', '').lower()
            target_addr = deposit_address.lower()
            
            if deposit_addr == target_addr:
                deposit_amount = float(deposit.get('amount', 0))
                deposit_status = deposit.get('status', 0)
                deposit_time = deposit.get('insertTime', 0)
                tx_id = deposit.get('txId', '')
                memo = deposit.get('memo', '')
                
                print(f"Found deposit: Amount={deposit_amount} {coin}, Expected=${expected_amount} USD, Status={deposit_status}, TxId={tx_id}")
                
                usd_equivalent = await convert_coin_to_usd(coin, deposit_amount)
                if usd_equivalent is None:
                    print(f"Could not get USD conversion for {deposit_amount} {coin}")
                    continue
                
                print(f"USD equivalent of {deposit_amount} {coin} = ${usd_equivalent:.4f}")
                
                amount_tolerance = expected_amount * 0.05
                amount_matches = abs(usd_equivalent - expected_amount) <= amount_tolerance
                
                is_success = deposit_status == 5
                is_pending = deposit_status == 4
                is_auditing = deposit_status == 6
                
                deal_start_time = datetime.fromisoformat(deal_data['timestamp'])
                deposit_datetime = datetime.fromtimestamp(deposit_time / 1000)
                is_after_deal_start = deposit_datetime >= deal_start_time
                
                if amount_matches and is_success and is_after_deal_start:
                    print(f"Payment verified! Amount: {deposit_amount} {coin} (${usd_equivalent:.4f} USD), Status: {deposit_status} (SUCCESS), TxId: {tx_id}")
                    return True
                elif amount_matches and (is_pending or is_auditing) and is_after_deal_start:
                    print(f"Payment found but still pending/auditing. Amount: {deposit_amount} {coin} (${usd_equivalent:.4f} USD), Status: {deposit_status}, TxId: {tx_id}")
                    return True
                elif amount_matches and is_after_deal_start:
                    status_names = {1: "SMALL", 2: "TIME_DELAY", 3: "LARGE_DELAY", 4: "PENDING", 5: "SUCCESS", 6: "AUDITING", 7: "REJECTED"}
                    status_name = status_names.get(deposit_status, f"UNKNOWN({deposit_status})")
                    print(f"Payment found but status is {deposit_status} ({status_name}). Amount: {deposit_amount} {coin} (${usd_equivalent:.4f} USD), TxId: {tx_id}")
                    
                    if deposit_status == 7:
                        continue
                    return True
                else:
                    print(f"Deposit found but doesn't match criteria: Amount match={amount_matches}, After deal start={is_after_deal_start}")
        
        print("No matching payment found")
        return False
        
    except Exception as e:
        print(f"Error verifying payment deposit: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False


async def convert_coin_to_usd(coin: str, amount: float):
    """
    Convert coin amount to USD equivalent using CryptoCompare API
    """
    try:
        # Handle USDT directly
        if coin.upper() == 'USDT':
            return amount
        
        # Get current price from CryptoCompare
        url = f"https://min-api.cryptocompare.com/data/price?fsym={coin.upper()}&tsyms=USD"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"CryptoCompare price data for {coin}: {data}")
                    
                    if 'USD' in data:
                        price = float(data['USD'])
                        usd_equivalent = amount * price
                        print(f"Converted {amount} {coin} to ${usd_equivalent:.4f} USD at rate ${price}")
                        return usd_equivalent
                    else:
                        print(f"USD price not found for {coin}")
                        return None
                else:
                    print(f"CryptoCompare API error: {response.status}")
                    return None
                    
    except Exception as e:
        print(f"Error converting {coin} to USD using CryptoCompare: {e}")
        return None


async def get_deposit_history_for_verification(coin: str, start_time: datetime = None):
    """
    Get deposit history for verification purposes
    """
    try:
        wallet = mexc_spot_v3.mexc_wallet()
        
        params = {
            "coin": coin,
            "limit": "100",
        }
        
        if start_time:
            start_time_ms = int(start_time.timestamp() * 1000)
            params["startTime"] = str(start_time_ms)
        
        deposit_history = wallet.get_deposit_list(params)
        return deposit_history
        
    except Exception as e:
        print(f"Error getting deposit history: {e}")
        return None


async def handle_deposit(update, context):
    query = update.callback_query
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
    selected_coin = deal_data.get('pay_currency')
    network = deal_data.get('network')
    
    if not selected_coin or not network:
        await query.answer("Coin or network not selected.", show_alert=True)
        return
    
    address_data = await handle_deposit_address_generation(deal_id, selected_coin, network)
    
    if not address_data:
        await query.edit_message_text(
            "Error generating deposit address. Please try again or select a different coin."
        )
        return
    
    update_active_deal(deal_id, {
        'status': 'waiting',
        'deposited_coin': selected_coin,  # Renamed for clarity
        'deposited_network': network,     # Store network
        'deposit_address': address_data['address'],
        'tag': address_data.get('memo', '')
    })
    
    deal_data = get_active_deal(deal_id)
    amount = deal_data['amount']
    fee_payer = deal_data.get('fee_payer', '')
    full_fee = calculate_fee(
        amount=amount,
        deal_type=deal_data['deal_type'],
        fee_payer=fee_payer,
        discount_percentage=deal_data.get('discount_percentage', 0.0)
    )
    if fee_payer == 'buyer':
        buyer_share = full_fee
    elif fee_payer == 'seller':
        buyer_share = 0
    elif fee_payer == 'split':
        buyer_share = full_fee / 2
    else:
        buyer_share = 0
    total = amount + buyer_share if deal_data['deal_type'] != 'p2p' else amount + (full_fee - buyer_share)
    
    address = address_data['address']
    tag = address_data.get('memo', '')
    deposit_instructions = (
        "🔐 *FLUXX ESCROW DEPOSIT INSTRUCTIONS* 🔐\n"
        "━━━━━━━━━━━━━━━━━\n\n"
        f"💰 *Deposit Amount:* ${total:.2f}\n"
        f"🪙 *Coin:* {selected_coin}\n"
        f"🌐 *Network:* {network}\n\n"
        f"📝 *Deposit Address:*\n`{address}`\n"
    )
    
    if tag:
        deposit_instructions += f"🏷️ *Tag/Memo:*\n`{tag}`\n\n"
    
    deposit_instructions += (
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 *Note:* The coin you deposit ({selected_coin} on {network}) will be the same coin used for withdrawal to the seller.\n\n"
        "⚠️ *IMPORTANT :* ⚠️\n"
        f"• Send ${total:.2f} worth of {selected_coin}\n"
        "• Double-check the network before sending\n"
        "• Ensure the address and memo (if any) are copied correctly\n\n"
        "*Click ✅ Sent After Payment*"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Sent", callback_data=f"payment_sent_{deal_id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        deposit_instructions,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_payment_sent(update, context):
    query = update.callback_query
    deal_id = query.data.split('_')[-1]
    deal_data = get_active_deal(deal_id)
    
    if not deal_data or deal_data.get('status') != 'waiting':
        await query.answer("No active deposit waiting for confirmation.", show_alert=True)
        return
    
    selector = 'seller' if deal_data['deal_type'] == 'p2p' else 'buyer'
    if query.from_user.id != deal_data[selector]:
        await query.answer(f"Only the {selector} can confirm the payment has been sent.", show_alert=True)
        return
    
    selected_coin = deal_data.get('deposited_coin')
    deposit_address = deal_data.get('deposit_address')
    amount = deal_data['amount']
    fee_payer = deal_data.get('fee_payer', 'buyer')
    full_fee = calculate_fee(amount, deal_data['deal_type'], fee_payer, deal_data.get('discount_percentage', 0.0))
    if fee_payer == 'buyer':
        depositor_share = full_fee
    elif fee_payer == 'seller':
        depositor_share = 0
    elif fee_payer == 'split':
        depositor_share = full_fee / 2
    else:
        depositor_share = 0
    expected_amount = amount + depositor_share if deal_data['deal_type'] != 'p2p' else amount + (full_fee - depositor_share)
    
    await query.answer("Verifying your payment...")
    
    try:
        # Phase 1/3 - Initial check
        await query.edit_message_text("🔍 Checking Payment 1/3...")
        payment_found = await verify_payment_deposit(selected_coin, deposit_address, expected_amount, deal_data)
        
        if payment_found:
            await query.edit_message_text("✅ Payment confirmed!")
            await asyncio.sleep(2)
            await handle_payment_confirmed(query, context, deal_id, deal_data)
            return
        
        await asyncio.sleep(60)
        
        current_deal = get_active_deal(deal_id)
        if not current_deal or current_deal.get('status') != 'waiting':
            return
        
        await query.edit_message_text("🔍 Checking Payment 2/3...")
        
        # Phase 2/3 - Second check
        payment_found = await verify_payment_deposit(selected_coin, deposit_address, expected_amount, deal_data)
        
        if payment_found:
            await query.edit_message_text("✅ Payment confirmed!")
            await asyncio.sleep(2)
            await handle_payment_confirmed(query, context, deal_id, deal_data)
            return
        
        await asyncio.sleep(120)
        
        # Check if deal still exists again
        current_deal = get_active_deal(deal_id)
        if not current_deal or current_deal.get('status') != 'waiting':
            return
            
        await query.edit_message_text("🔍 Checking Payment 3/3...")
        
        # Phase 3/3 - Final check
        payment_found = await verify_payment_deposit(selected_coin, deposit_address, expected_amount, deal_data)
        
        if payment_found:
            await query.edit_message_text("✅ Payment confirmed!")
            await asyncio.sleep(2)
            await handle_payment_confirmed(query, context, deal_id, deal_data)
            return
        
        # Payment not found after all attempts
        await query.edit_message_text("❌ Sorry we could not confirm your payment")
        await asyncio.sleep(4)
        
        # Fallback to deposit address display
        await show_deposit_address_again(query, context, deal_data)
        
    except Exception as e:
        print(f"Error in payment verification process: {e}")
        await query.edit_message_text("❌ Error occurred during payment verification. Please try again.")
        await asyncio.sleep(3)
        await show_deposit_address_again(query, context, deal_data)

async def handle_payment_confirmed(query, context, deal_id, deal_data):
    """Handle confirmed payment - similar to oxapay callback"""
    bot = context.bot
    group_id = deal_data['group_id']
    
    # Update deal status
    update_active_deal(deal_id, {
        'status': 'deposited',
        'payment_time': datetime.now().isoformat()
    })
    
    buyer = await bot.get_chat(deal_data['buyer'])
    seller = await bot.get_chat(deal_data['seller'])
    buyer_name = deal_data.get('buyer_name', buyer.first_name)
    seller_name = deal_data.get('seller_name', seller.first_name)
    
    selector = 'seller' if deal_data['deal_type'] == 'p2p' else 'buyer'
    depositor_name = seller_name if selector == 'seller' else buyer_name
    depositor_id = deal_data['seller'] if selector == 'seller' else deal_data['buyer']
    receiver_name = buyer_name if selector == 'seller' else seller_name
    receiver_id = deal_data['buyer'] if selector == 'seller' else deal_data['seller']
    
    amount = deal_data['amount']
    fee_payer = deal_data.get('fee_payer', 'buyer')
    full_fee = calculate_fee(amount, deal_data['deal_type'], fee_payer, deal_data.get('discount_percentage', 0.0))
    total = amount + full_fee  # Note: This is the gross total; depositor paid their share + amount
    
    details_section = f"<b>Details:</b> {deal_data.get('details', '')}\n" if deal_data.get('deal_type') != 'p2p' else ""
    remaining_time = f"{deal_data.get('timer_hours', 1)} hours"
    
    instructions = (
        f"1. Ensure the transaction is fully completed before proceeding.\n"
        f"2. <a href='tg://user?id={receiver_id}'>{receiver_name}</a> Verify that all items/services meet your expectations.\n"
        f"3. <a href='tg://user?id={receiver_id}'>{receiver_name}</a> Only click 'Release Payment' if fully satisfied with the transaction.\n"
       
    )
    
    text = (
        f"<b>{DEAL_TYPE_DISPLAY.get(deal_data['deal_type'], 'Deal')} - Payment Confirmed ✅</b>\n\n"
        f"<b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{buyer_name}</a>\n"
        f"<b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{seller_name}</a>\n"
        f"{details_section}"
        f"<b>Amount:</b> <code>${amount:.2f}</code>\n"
        f"<b>Fee (Paid by {fee_payer.capitalize()}):</b> <code>${full_fee:.2f}</code>\n"
        f"<b>Total:</b> <code>${total:.2f}</code>\n\n"
        f"<b>⚠️ Instructions:</b>\n{instructions}\n\n"
        f"<b>⏱ Time Remaining:</b> <code>{remaining_time}</code>"
    )

    keyboard = [
        [InlineKeyboardButton("💰 Release Payment", callback_data=f"release_payment_{deal_id}")],
        [InlineKeyboardButton("⏳ Check Timer", callback_data=f"check_timer_{deal_id}")],
        [InlineKeyboardButton("👨‍💼 Involve Moderator", callback_data=f"mod_{deal_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    sent_message = await bot.send_message(
        chat_id=group_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    # Start background admin monitoring after payment confirmed
    from main import monitor_admin_main, PIN_TRACKER, ADMIN_MONITORS, check_payment_timeout
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
    except Exception as e:
        print(f"[DEBUG] Error pinning message for deal {deal_id}: {e}")
    asyncio.create_task(check_payment_timeout(bot, group_id, deal_id, sent_message.message_id))

async def show_deposit_address_again(query, context, deal_data):
    # Re-display the deposit instructions
    selected_coin = deal_data.get('deposited_coin')
    network = deal_data.get('deposited_network')
    address = deal_data.get('deposit_address')
    tag = deal_data.get('tag', '')
    amount = deal_data['amount']  # Or recalculate total
    
    deposit_instructions = (
        "🔐 *FLUXX ESCROW DEPOSIT INSTRUCTIONS* 🔐\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 *Deposit Amount:* ${amount:.2f}\n"  # Use recalculated if needed
        f"🪙 *Coin:* {selected_coin}\n"
        f"🌐 *Network:* {network}\n\n"
        f"📝 *Deposit Address:*\n`{address}`\n"
    )
    
    if tag:
        deposit_instructions += f"🏷️ *Tag/Memo:*\n`{tag}`\n\n"
    
    deposit_instructions += (
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ *IMPORTANT WARNINGS:* ⚠️\n"
        f"• Send *EXACTLY* ${amount:.2f} worth of {selected_coin}\n"
        f"• Double-check the network before sending\n"
        f"• Ensure the address is copied correctly\n\n"
        "After completing your deposit, click 'I've Sent Payment' below."
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Sent", callback_data=f"payment_sent_{deal_data['deal_id']}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        deposit_instructions,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )