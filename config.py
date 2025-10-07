import os
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5991907369"))
OXAPAY_API_KEY = os.getenv("OXAPAY_API_KEY")
OXAPAY_PAYOUT_KEY = os.getenv("OXAPAY_PAYOUT_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "echofluxx") 
BOT_USERNAME = os.getenv("BOT_USERNAME", "mmbotsold_bot")
mexc_host = "https://api.mexc.com"
api_key = "mx0vglBVfP9oHXqHxL"
secret_key = "5d2738c28e7b4b32962b407df2034802"
P2P_FEE = 0.025  
BS_FEE = 0.03   
DEFAULT_PAY_CURRENCY = "USDT"
DEFAULT_NETWORK = "TRC20"
DEFAULT_CURRENCY = "USD"  # Fiat base
DEFAULT_LIFETIME = 60  # minutes
DEFAULT_FEE_PAID_BY_PAYER = 0  # Default to merchant (escrow) pays, but we'll override based on fee_payer
DEFAULT_REFER_PERCENT = 10.0

DEFAULT_MAX_DEAL = 10000 
DEFAULT_FREE_LIMIT = 100  
DEFAULT_LOG_CHANNEL = None  
DEAL_TYPE_DISPLAY = {
    'b_and_s': 'Product Deal',
    'p2p': 'P2P Transfer'
    
}

AVAILABLE_COINS = ["BNB", "BTC", "ETH", "LTC", "SOL", "TON", "TRX", "USDT"]


USDT_NETWORKS = ["TRC20", "ERC20", "BEP20", "TON", "POL"]

ALLOWED_GROUPS = []