from handlers import *
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    message = query.message
    data = query.data
    logger.info(f"[handle_callback] Received callback data: {data}")
    bot = context.bot
    group_id = message.chat.id
    
    active_deals = get_all_active_deals()
    deal_id = None
    for d_id, deal in active_deals.items():
        if deal['group_id'] == group_id:
            deal_id = d_id
            break
    deal_data = get_active_deal(deal_id) if deal_id else None
    
    fees_data = load_fees_json()
    if not fees_data:
        logger.error("[handle_callback] Failed to load fees.json")
        await query.answer("Error loading fee data.", show_alert=True)
        return
    if data == 'check_admin_balance':
        if update.callback_query.from_user.id != ADMIN_ID:
            await query.answer("Only admin can view this.")
            return
        settings = load_settings()
        balance = settings.get('admin_balance', 0.0)
        
        keyboard = [[InlineKeyboardButton("Withdraw Fee", callback_data="withdraw_admin_fee")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Admin Fee Balance: ${balance:.2f}",
            reply_markup=reply_markup
        )

    elif data == 'withdraw_admin_fee':
        if update.callback_query.from_user.id != ADMIN_ID:
            await query.answer("Only admin can withdraw.")
            return
        await query.answer("Use Command:\n\n/withdfee {amount} {coin} {address} [memo]\n\nto withdraw.")

    elif data.startswith('form_confirm_') or data.startswith('form_cancel_'):
        await handle_form_confirmation(update.callback_query, data, context)

    elif data.startswith('fee_'):
            fee_payer, deal_id = data.split('_')[1], data.split('_')[2]
            deal_data = get_active_deal(deal_id)
            if not deal_data:
                await query.answer("Deal not found.")
                return
            selector = 'seller' if deal_data['deal_type'] == 'p2p' else 'buyer'
            if query.from_user.id != deal_data[selector]:
                await query.answer(f"Only the {selector} can select the fee payer.", show_alert=True)
                return
            deal_data['fee_payer'] = fee_payer
            update_active_deal(deal_id, deal_data)
            context.user_data['fee_payer'] = fee_payer
            # Adjust amount based on fee_payer
            adjusted_amount = deal_data['amount']
            fee = calculate_fee(adjusted_amount, deal_data['deal_type'], fee_payer)
            if fee_payer == 'buyer':
                adjusted_amount += fee
            elif fee_payer == 'split':
                adjusted_amount += fee
            context.user_data['amount'] = adjusted_amount
            # Add fee confirmation step
            if 'fee_confirmations' not in deal_data:
                deal_data['fee_confirmations'] = []
            update_active_deal(deal_id, deal_data)
            buyer_name = deal_data.get('buyer_name', '')
            seller_name = deal_data.get('seller_name', '')
            fee_payer_display = buyer_name if fee_payer == 'buyer' else seller_name if fee_payer == 'seller' else 'Splitted'
            deal_type_display = DEAL_TYPE_DISPLAY.get(deal_data['deal_type'], deal_data['deal_type']) if 'deal_type' in deal_data and deal_data['deal_type'] else 'N/A'
            keyboard = [[InlineKeyboardButton("Buyer Confirm", callback_data=f"confirm_fee_{deal_id}_buyer"), 
                        InlineKeyboardButton("Seller Confirm", callback_data=f"confirm_fee_{deal_id}_seller")],
                        [InlineKeyboardButton("End ❌", callback_data=f"back"), 
                        InlineKeyboardButton("Back 🔙", callback_data=f"back_to_fee_{deal_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"<b>Fee Payer Selection</b>\n\n"
                f"Fee payer: <b>{fee_payer_display}</b>\n"
                f"<b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{deal_data['buyer_name']}</a>\n"
                f"<b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{deal_data['seller_name']}</a>\n"
                f"Deal Type: <b>{deal_type_display}</b>\n\n"
                f"Both buyer and seller must confirm the fee selection to proceed.\n\n"
                f"<i>Click the button below to confirm.</i>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            await query.answer(f"{fee_payer.capitalize()} will pay the fee. Waiting for confirmation.")
            return
    elif data.startswith('fee_cancel_'):
        deal_id = data.split('_')[-1]
        deal_data = get_active_deal(deal_id)
        if not deal_data:
            await query.answer("Invalid deal.")
            return
        if query.from_user.id != ADMIN_ID:
            await query.answer("Only the Admin Can Cancel", show_alert=True)
            return
        try:
            await query.message.delete()
        except:
            pass
        remove_active_deal(deal_id)
        await query.answer("Form cancelled.")
    elif data.startswith('confirm_fee_'):
            deal_id = data.split('_')[2]
            deal_data = get_active_deal(deal_id)
            if not deal_data:
                await query.answer("Deal not found.")
                return
            user_id = query.from_user.id
            if user_id not in [deal_data['buyer'], deal_data['seller']]:
                await query.answer("Only buyer and seller can confirm fee.", show_alert=True)
                return
            if 'fee_confirmations' not in deal_data:
                deal_data['fee_confirmations'] = []
            # Only allow buyer to confirm via buyer button, seller via seller button
            already_confirmed = user_id in deal_data['fee_confirmations']
            if already_confirmed:
                await query.answer("You have already confirmed.", show_alert=True)
                return
            deal_data['fee_confirmations'].append(user_id)
            update_active_deal(deal_id, {'fee_confirmations': deal_data['fee_confirmations']})
            buyer_name = deal_data.get('buyer_name', '')
            seller_name = deal_data.get('seller_name', '')
            fee_payer = deal_data['fee_payer']
            fee_payer_display = buyer_name if fee_payer == 'buyer' else seller_name if fee_payer == 'seller' else 'Splitted'
            deal_type_display = DEAL_TYPE_DISPLAY.get(deal_data['deal_type'], deal_data['deal_type']) if 'deal_type' in deal_data and deal_data['deal_type'] else 'N/A'
            # Show confirm buttons if not both confirmed
            if len(deal_data['fee_confirmations']) < 2:
                # Show Buyer Confirm and Seller Confirm buttons, both on same row, End Deal below
                fee_payer = deal_data.get('fee_payer', '')
                confirm_row = []
                if deal_data['buyer'] not in deal_data['fee_confirmations']:
                    confirm_row.append(InlineKeyboardButton("Buyer Confirm", callback_data=f"confirm_fee_{deal_id}_buyer"))
                if deal_data['seller'] not in deal_data['fee_confirmations']:
                    confirm_row.append(InlineKeyboardButton("Seller Confirm", callback_data=f"confirm_fee_{deal_id}_seller"))
                keyboard = []
                if confirm_row:
                    keyboard.append(confirm_row)

                keyboard.append([InlineKeyboardButton("❌ End", callback_data="back"), InlineKeyboardButton("Back 🔙", callback_data=f"back_to_fee_{deal_id}")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"<b>Fee Payer Selection</b>\n\n"
                    f"Fee payer: <b>{fee_payer_display}</b>\n"
                    f"<b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{deal_data['buyer_name']}</a>\n"
                    f"<b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{deal_data['seller_name']}</a>\n"
                    f"Deal Type: <b>{deal_type_display}</b>\n\n"
                    f"Confirmation received. Waiting for other party to confirm.\n\n"
                    f"<i>Both buyer and seller must confirm to proceed.</i>",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                await query.answer("Confirmation received. Waiting for other party.", show_alert=True)
                return
            # Both confirmed, show summary and prompt to select deposit coin
            from deposit import coins
            keyboard = []
            row = []
            for item in coins:
                row.append(InlineKeyboardButton(item['text'], callback_data=f"select_coin_{item['coin']}_{item['network']}_{deal_id}"))
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            keyboard.append([InlineKeyboardButton("❌ End", callback_data="back")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            selector = 'seller' if deal_data['deal_type'] == 'p2p' else 'buyer'
            selector_name = deal_data[f'{selector}_name']
            selector_id = deal_data[selector]
            fee_payer = deal_data.get('fee_payer', '')
            full_fee = calculate_fee(
                amount=deal_data['amount'],
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
            total = deal_data['amount'] + buyer_share if selector == 'buyer' else deal_data['amount'] + (full_fee - buyer_share)
            
            
          
            await query.edit_message_text(
                f"<b>Fee Payer Confirmed ✅</b>\n\n"
                f"Fee payer: <b>{fee_payer_display}</b>\n"
                f"<b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{deal_data['buyer_name']}</a>\n"
                f"<b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{deal_data['seller_name']}</a>\n"
                f"Deal Type: <b>{deal_type_display}</b>\n\n"
                f"<b>Escrow Fee:</b> ${full_fee:.2f}\n ({fee_payer.capitalize()} pays: ${buyer_share if fee_payer == 'buyer' else full_fee - buyer_share if fee_payer == 'seller' else buyer_share:.2f})\n"
                f"\n<b>Total ({selector.capitalize()}):</b> ${total:.2f}\n"
                f"<a href='tg://user?id={selector_id}'>{selector_name}</a>, please select the payment coin:\n\n"
                f"📌 <b>Note:</b> Whatever coin you deposit will be the same coin used for withdrawal. Both buyer and seller must agree on the selected coin to proceed.",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            await query.answer("Fee confirmed. Select deposit coin.")
            return
    
    elif data.startswith('select_coin_'):
        coin = data.split('_')[2]
        network = data.split('_')[3]
        deal_id = data.split('_')[4]
        deal_data = get_active_deal(deal_id)
        if not deal_data:
            await query.answer("Deal not found.")
            return
        selector = 'seller' if deal_data['deal_type'] == 'p2p' else 'buyer'
        if query.from_user.id != deal_data[selector]:
            await query.answer(f"Only the {selector} can select the coin.", show_alert=True)
            return

        amount = deal_data['amount']
        withdraw_min_usd = None
        for fee_entry in fees_data:
            if fee_entry['coin'] == coin and fee_entry['network'] == network:
                withdraw_min = float(fee_entry['withdrawMin'])
                if coin.upper() == 'USDT':
                    withdraw_min_usd = withdraw_min
                else:
                    # Convert withdrawMin to USD for non-USDT coins
                    withdraw_min_usd = await convert_coin_to_usd(coin, withdraw_min)
                break

        if withdraw_min_usd is None:
            await query.answer(f"Error: Could not determine minimum deal amount for {coin} on {network}.", show_alert=True)
            return

        if amount < withdraw_min_usd:
            await query.answer(f"{coin} {network} min deal amount is ${withdraw_min_usd:.2f}.", show_alert=True)
            return
        # Save temporary coin and network
        update_active_deal(deal_id, {
            'temp_coin': coin,
            'temp_network': network
        })
        # Show confirmation buttons for both
        buyer_name = deal_data.get('buyer_name', '')
        seller_name = deal_data.get('seller_name', '')
        deal_type_display = DEAL_TYPE_DISPLAY.get(deal_data['deal_type'], deal_data['deal_type']) if 'deal_type' in deal_data and deal_data['deal_type'] else 'N/A'
        keyboard = [
            [
                InlineKeyboardButton("B Confirm Coin", callback_data=f"confirm_coin_{deal_id}_buyer"),
                InlineKeyboardButton("S Confirm Coin", callback_data=f"confirm_coin_{deal_id}_seller")
            ],
            [InlineKeyboardButton("❌ End", callback_data="back"), InlineKeyboardButton("Back 🔙", callback_data=f"back_to_coin_{deal_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"<b>Coin Selection</b>\n\n"
            f"Selected Coin: <b>{coin}</b>\n"
            f"Network: <b>{network}</b>\n"
            f"<b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{buyer_name}</a>\n"
            f"<b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{seller_name}</a>\n"
            f"Deal Type: <b>{deal_type_display}</b>\n\n"
            f"📌 <b>Note:</b> This coin ({coin} on {network}) will be used for both deposit and withdrawal.\n\n"
            f"Both buyer and seller must confirm the coin selection to proceed.\n\n"
            f"<i>Click the button below to confirm.</i>",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        await query.answer(f"{coin} on {network} selected. Waiting for confirmation.")
        return
    
    elif data.startswith('confirm_coin_'):
        deal_id = data.split('_')[2]
        deal_data = get_active_deal(deal_id)
        if not deal_data:
            await query.answer("Deal not found.")
            return
        user_id = query.from_user.id
        if user_id not in [deal_data['buyer'], deal_data['seller']]:
            await query.answer("Only buyer and seller can confirm coin.", show_alert=True)
            return
        if 'coin_confirmations' not in deal_data:
            deal_data['coin_confirmations'] = []
            update_active_deal(deal_id, deal_data)
        already_confirmed = user_id in deal_data['coin_confirmations']
        if already_confirmed:
            await query.answer("You have already confirmed.", show_alert=True)
            return
        deal_data['coin_confirmations'].append(user_id)
        update_active_deal(deal_id, {'coin_confirmations': deal_data['coin_confirmations']})
        coin = deal_data.get('temp_coin', '')
        network = deal_data.get('temp_network', '')
        buyer_name = deal_data.get('buyer_name', '')
        seller_name = deal_data.get('seller_name', '')
        deal_type_display = DEAL_TYPE_DISPLAY.get(deal_data['deal_type'], deal_data['deal_type']) if 'deal_type' in deal_data and deal_data['deal_type'] else 'N/A'
        if len(deal_data['coin_confirmations']) < 2:
            confirm_row = []
            if deal_data['buyer'] not in deal_data['coin_confirmations']:
                confirm_row.append(InlineKeyboardButton("B Confirm Coin", callback_data=f"confirm_coin_{deal_id}_buyer"))
            if deal_data['seller'] not in deal_data['coin_confirmations']:
                confirm_row.append(InlineKeyboardButton("S Confirm Coin", callback_data=f"confirm_coin_{deal_id}_seller"))
            keyboard = []
            if confirm_row:
                keyboard.append(confirm_row)
            keyboard.append([InlineKeyboardButton("❌ End", callback_data="back"), InlineKeyboardButton("Back 🔙", callback_data=f"back_to_coin_{deal_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"<b>Coin Selection</b>\n\n"
                f"Selected Coin: <b>{coin}</b>\n"
                f"Network: <b>{network}</b>\n"
                f"<b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{buyer_name}</a>\n"
                f"<b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{seller_name}</a>\n"
                f"Deal Type: <b>{deal_type_display}</b>\n\n"
                f"📌 <b>Note:</b> This coin ({coin} on {network}) will be used for both deposit and withdrawal.\n\n"
                f"Confirmation received. Waiting for other party to confirm.\n\n"
                f"<i>Both buyer and seller must confirm to proceed.</i>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            await query.answer("Confirmation received. Waiting for other party.", show_alert=True)
            return
        # Both confirmed, save coin and network, proceed to deposit
        update_active_deal(deal_id, {
            'pay_currency': coin,
            'network': network
        })
        # Simulate the deposit callback by calling handle_deposit with modified query.data
        query.data = f"deposit_{coin}_{network}"
        await handle_deposit(update, context)
        await query.answer("Coin confirmed by both. Proceeding to deposit instructions.")
        return
    
    elif data.startswith('back_to_coin_'):
        deal_id = data.split('_')[-1]
        # Reset coin_confirmations and temp_coin/network if needed
        deal_data = get_active_deal(deal_id)
        if deal_data:
            update_active_deal(deal_id, {
                'coin_confirmations': [],
                'temp_coin': None,
                'temp_network': None
            })
        # Re-show the coin selection keyboard (copy from fee confirmed part)
        from deposit import coins
        keyboard = []
        row = []
        for item in coins:
            row.append(InlineKeyboardButton(item['text'], callback_data=f"select_coin_{item['coin']}_{item['network']}_{deal_id}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("❌ End", callback_data="back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        selector = 'seller' if deal_data['deal_type'] == 'p2p' else 'buyer'
        selector_name = deal_data[f'{selector}_name']
        selector_id = deal_data[selector]
        fee_payer = deal_data.get('fee_payer', '')
        full_fee = calculate_fee(
            amount=deal_data['amount'],
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
        total = deal_data['amount'] + buyer_share if selector == 'buyer' else deal_data['amount'] + (full_fee - buyer_share)
        await query.edit_message_text(
            f"<b>Fee Payer Confirmed ✅</b>\n\n"
            f"Fee payer: <b>{fee_payer_display}</b>\n"
            f"<b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{deal_data['buyer_name']}</a>\n"
            f"<b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{deal_data['seller_name']}</a>\n"
            f"Deal Type: <b>{deal_type_display}</b>\n\n"
            f"<b>Escrow Fee:</b> ${full_fee:.2f}\n ({fee_payer.capitalize()} pays: ${buyer_share if fee_payer == 'buyer' else full_fee - buyer_share if fee_payer == 'seller' else buyer_share:.2f})\n"
            f"\n<b>Total ({selector.capitalize()}):</b> ${total:.2f}\n"
            f"<a href='tg://user?id={selector_id}'>{selector_name}</a>, please select the payment coin:\n\n"
            f"📌 <b>Note:</b> Whatever coin you deposit will be the same coin used for withdrawal. Both buyer and seller must agree on the selected coin to proceed.",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        await query.answer("Back to coin selection.")
        return
    elif data.startswith('back_to_fee_'):
        deal_id = data.split('_')[-1]
        deal_data = get_active_deal(deal_id)
        if not deal_data:
            await query.answer("Deal not found.")
            return
        selector = 'seller' if deal_data['deal_type'] == 'p2p' else 'buyer'
        if query.from_user.id != deal_data[selector]:
            await query.answer(f"Only the {selector} can go back to fee selection.", show_alert=True)
            return
        update_active_deal(deal_id, {'status': 'fee_pending'})
        await proceed_to_fee_payer(bot, deal_id, deal_data)
        await query.answer("Returned to fee payer selection.")
        try:
            await query.message.delete()
        except Exception as e:
            print(f"[DEBUG] Error deleting message for back_to_fee {deal_id}: {e}")

    elif data.startswith('confirm_release_'):
        await handle_confirm_release(update, context)
        return
    
    elif data == 'back_release':
        await handle_back_release(update, context)
        return
    # ---- BUTTON ABORT IF BOT NOT ADMIN + DEAL DEPOSITED ----
    action_buttons = {"release_payment", "check_timer", "mod", "back"}
    if deal_data and deal_data.get("status") == "deposited" and query.data in action_buttons:
        is_admin = await ensure_bot_admin_telethon(query.message.chat.id)
        if not is_admin:
           
            deal_info = json.dumps(deal_data, indent=2, default=str)
            buyer_link = f"<a href='tg://user?id={deal_data['buyer']}'>{deal_data.get('buyer_name','UNKNOWN')}</a>"
            seller_link = f"<a href='tg://user?id={deal_data['seller']}'>{deal_data.get('seller_name','UNKNOWN')}</a>"
            admin_warn = (
                    f"🚨<b>BOT IS NO LONGER ADMIN</b>\n\n"
                    f"Deal forcibly ended.\n"
                    f"Group ID: <code>{group_id}</code>\n"
                    f"<b>Buyer:</b> {buyer_link}\n"
                    f"<b>Seller:</b> {seller_link}\n\n"
                    f"<code>/leave {group_id}</code>\n to force bot exit this group."
            )
            remove_active_deal(deal_id)
            try:
                await context.bot.send_message(ADMIN_ID, admin_warn, parse_mode='HTML')
            except Exception as e:
                print(f"Error sending admin warning: {e}")
            try:
                await query.edit_message_text(
                    "❌ Deal ended: Bot is NOT admin. Contact the admin for resolution.", parse_mode='HTML'
                )
            except Exception:
                pass
            return
    
   
   
    elif query.data == "help":
        keyboard = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="help_en"),
             InlineKeyboardButton("Hindi 🇮🇳", callback_data="help_hi")],
            [InlineKeyboardButton("Back 🔙", callback_data="mainmenu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Select your preferred language for help:",
            reply_markup=reply_markup
        )
   
    elif query.data.startswith("help_"):
        await handle_help_language(update, context)
    elif query.data == "reviews":
        await handle_reviews(update, context)
    elif data.startswith('release_payment_'):
        deal_id = data.split('_')[-1]
        deal_data = get_active_deal(deal_id)
        if not deal_data:
            await query.answer("Deal not found or expired.", show_alert=True)
            return
        if deal_data['status'] != 'deposited':
            await query.answer("Deal is not in deposited state.", show_alert=True)
            return
        try:
            await handle_release_payment(update, context)
        except Exception as e:
            await query.answer(f"Error processing release: {str(e)}", show_alert=True)
            print(f"[DEBUG] Error in release_payment callback for deal {deal_id}: {e}")

   
    elif query.data == "seller_confirm_paid":
        await handle_seller_confirm(update, context)
   
    elif query.data == "mainmenu":
        await handle_start(update, context)
    elif query.data == "mod":
        user_id = query.from_user.id
        context.user_data['awaiting_complaint'] = True
        context.user_data['complaint_message_id'] = query.message.message_id
        await query.answer()
        await query.message.reply_text("Please type your complaint message.")

    elif query.data.startswith("review_"):
        _, action, seller_id = query.data.split("_")
        active_deals = get_all_active_deals()
        deal_data = None
        for deal in active_deals.values():
            if deal['seller'] == int(seller_id):
                deal_data = deal
                break
        
        if query.from_user.id != deal_data['buyer']:
            await query.answer("Only the buyer can leave a review ❌", show_alert=True)
            return
        seller = await context.bot.get_chat(int(seller_id))
        buyer = await context.bot.get_chat(deal_data['buyer'])
        
        if action == "positive":
            review_system.add_review(int(seller_id), seller.first_name, True, deal_data['deal_type'],  buyer.id, buyer.first_name)
            await query.edit_message_text(
                f"✅ You rated {seller.first_name} positively!\n\n"
                "Thank you for your feedback."
            )
        elif action == "negative":
            review_system.add_review(int(seller_id), seller.first_name, False, deal_data['deal_type'],  buyer.id, buyer.first_name)
            await query.edit_message_text(
                f"❌ You rated {seller.first_name} negatively.\n\n"
                "Thank you for your feedback."
            )
    elif data.startswith('payment_sent_'):
        deal_id = data.split('_')[-1]
        await handle_payment_sent(update, context)
        return
    elif query.data == "back":
        query = update.callback_query
        message = query.message
        group_id = message.chat.id
        active_deals = get_all_active_deals()
        deal_id = None
        for d_id, deal in active_deals.items():
            if deal['group_id'] == group_id:
                deal_id = d_id
                break
        if deal_id:
            deal_data = get_active_deal(deal_id)
            if deal_data:
                status = deal_data.get('status')
                if status in ['waiting', 'deposited', 'initiated']:
                    # Only ADMIN_ID can cancel in these statuses
                    if str(query.from_user.id) == ADMIN_ID:
                        remove_active_deal(deal_id)
                        context.user_data.clear()
                        context.user_data["state"] = None
                        if 'buyer' in deal_data:
                            context.user_data.pop('buyer', None)
                        if 'seller' in deal_data:
                            context.user_data.pop('seller', None)
                        user_link = f'<a href="tg://user?id={query.from_user.id}">{query.from_user.first_name}</a>'
                        await query.edit_message_text(f"Deal cancelled by Admin {user_link}.", parse_mode="html")
                    else:
                        await query.answer("Only Moderator can cancel deals at this stage ❌", show_alert=True)
                else:
                    # Other statuses: allow only ADMIN_ID
                    if str(query.from_user.id) == ADMIN_ID:
                        remove_active_deal(deal_id)
                        context.user_data.clear()
                        context.user_data["state"] = None
                        if 'buyer' in deal_data:
                            context.user_data.pop('buyer', None)
                        if 'seller' in deal_data:
                            context.user_data.pop('seller', None)
                        user_link = f'<a href="tg://user?id={query.from_user.id}">{query.from_user.first_name}</a>'
                        await query.edit_message_text(f"Deal cancelled by Admin {user_link}.", parse_mode="html")
                    else:
                        await query.answer("You are not authorized to cancel this deal ❌", show_alert=True)
            else:
                await query.answer("No active deal found.", show_alert=True)


    elif query.data.startswith("refunds_"):
        await handle_refund_coin_selection(update, context)
    
    elif data.startswith('broadcast_'):
        await handle_broadcast_type(update, context) if data in ['broadcast_text', 'broadcast_image'] else await handle_broadcast_confirmation(update, context)


    elif query.data == "check_timer":
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
        
        buyer = await context.bot.get_chat(deal_data['buyer'])
        seller = await context.bot.get_chat(deal_data['seller'])
        deal_type = deal_data['deal_type']
        deal_type_display = DEAL_TYPE_DISPLAY.get(deal_type, deal_type)
        amount = deal_data['amount']
        fee_payer = deal_data['fee_payer']
        fee = calculate_fee(amount, deal_data['deal_type'])
        total = amount + fee
        buyer_share, full_fee = calculate_fee(amount, deal_type, fee_payer)
        
        keyboard = [  
            [InlineKeyboardButton("💰 Release Payment", callback_data="release_payment")],  
            [InlineKeyboardButton("⏳ Check Timer", callback_data="check_timer")],  
            [InlineKeyboardButton("👨‍💼 Involve Moderator", callback_data="mod")],  
            [InlineKeyboardButton("🚫 End Deal", callback_data="back")]  
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
       
        
        if deal_type == 'p2p':
            instructions = (
                "👤 <b>Buyer:</b> Release payment only after seller sends coin/fiat.\n"
                "👤 <b>Seller:</b> Deliver promptly; wait for buyer confirmation."
            )
        else:  # b_and_s or product
            instructions = (
                "👤 <b>Buyer:</b> Release payment only after receiving product/service.\n"
                "👤 <b>Seller:</b> Deliver promptly; wait for buyer confirmation."
            )

        text = (
            f"✅ <b>Payment Confirmed!</b>\n\n"
            f"👤 <b>Buyer:</b> <a href='tg://user?id={deal_data['buyer']}'>{buyer.first_name}</a>\n"
            f"👤 <b>Seller:</b> <a href='tg://user?id={deal_data['seller']}'>{seller.first_name}</a>\n"
            f"📋 <b>Type:</b> {deal_type_display}\n"
            f"💸 <b>Amount:</b> ${amount:.2f}\n"
            f"💵 <b>Fee:</b> ${buyer_share:.2f}\n"
            f"💰 <b>Total:</b> ${total:.2f}\n\n"
            f"{instructions}\n\n"
            f"⚠️ <i>Complete trade before timer expires.</i>"
        )

        keyboard = [
            [InlineKeyboardButton("💰 Release Payment", callback_data="release_payment")],
            [InlineKeyboardButton("⏳ Check Timer", callback_data="check_timer")],
            [InlineKeyboardButton("👨‍💼 Involve Moderator", callback_data="mod")],
            [InlineKeyboardButton("🚫 End Deal", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        await query.answer("Timer updated.")

    await query.answer()



