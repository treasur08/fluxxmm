import os
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5991907369"))
OXAPAY_API_KEY = os.getenv("OXAPAY_API_KEY")
OXAPAY_PAYOUT_KEY = os.getenv("OXAPAY_PAYOUT_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "echofluxx") 
P2P_FEE = 0.025  
BS_FEE = 0.03   

DEAL_TYPE_DISPLAY = {
    'b_and_s': 'Buy and Sell',
    'p2p': 'P2P Transfer'
    
}
