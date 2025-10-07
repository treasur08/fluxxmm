import json

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

with open('coin_list.json', 'r', encoding='utf-8') as f:
    all_coins = json.load(f)

result = []

for coin_entry in coins:
    for c in all_coins:
        if c.get('coin', '').upper() == coin_entry['coin'].upper():
            for n in c.get('networkList', []):
                if n.get('network', '').lower() == coin_entry['network'].lower():
                    result.append({
                        "text": coin_entry['text'],
                        "coin": coin_entry['coin'],
                        "network": coin_entry['network'],
                        "withdrawFee": n.get('withdrawFee'),
                        "withdrawMin": n.get('withdrawMin')
                    })

with open('fees.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=4, ensure_ascii=False)

print("fees.json created!")