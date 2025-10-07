import requests  
import json   
from dotenv import load_dotenv  
import os  

load_dotenv()  

PAYOUT_KEY = os.getenv('OXAPAY_PAYOUT_KEY')  
EXCHANGE_KEY = os.getenv('OXAPAY_GENERAL_KEY')    

def check_balance():  
    url = 'https://api.oxapay.com/api/balance'  
    data = {  
        'key': PAYOUT_KEY   
    }  
    
    response = requests.post(url, json=data)  
    print(f"Balance API response: {response.text}")
    # Check if the response was successful  
    if response.status_code == 200:  
        result = response.json()   
        return result  
    else:  
        return f"Error: {response.status_code}, {response.text}"  

def request_exchange(amount, from_currency, to_currency):  
    url = 'https://api.oxapay.com/exchange/request'  
    data = {  
        'key': EXCHANGE_KEY, 
        'amount': amount,  
        'fromCurrency': from_currency,  
        'toCurrency': to_currency  
    }  
  
    response = requests.post(url, json=data) 
  
    if response.status_code == 200:  
        result = response.json()  
        return result  
    else:  
        return f"Error: {response.status_code}, {response.text}"  

def exchange_rate(amount, to_currency):
    url = 'https://api.oxapay.com/exchange/calculate'
    data = {
        'amount': amount,
        'fromCurrency': 'USDT',
        'toCurrency': to_currency
    }

    response = requests.post(url, json=data)
    print(f"Exchange rate calculation response: {response.text}")

    if response.status_code == 200:
        result = response.json()
        return result
    else:
        return f"Error: {response.status_code}, {response.text}"

