import mexc_spot_v3
import json

wallet = mexc_spot_v3.mexc_wallet()

coin = input("Enter the coin symbol (optional): ").strip().upper()
range_limit = input("Enter the range limit (optional): ").strip()

CoinList = wallet.get_coinlist()
# print(CoinList)  # Debug: See the structure

# Filter by coin symbol if provided
if coin:
    # CoinList is a list of dicts, filter by 'coin' key
    CoinList = [c for c in CoinList if c.get('coin', '').upper() == coin]

if range_limit.isdigit():
    limit = int(range_limit)
    CoinList = CoinList[:limit]

with open('coin_list.json', 'w', encoding='utf-8') as f:
    json.dump(CoinList, f, indent=4, ensure_ascii=False)