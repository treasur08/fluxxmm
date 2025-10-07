import requests
import json

url = 'https://api.oxapay.com/v1/payment/accepted-currencies'

headers = {
    'merchant_api_key': 'G26EHN-P8HAVP-16GYSH-HKXXVC',
    'Content-Type': 'application/json'
}

response = requests.get(url, headers=headers)
result = response.json()
with open('result.json', 'w') as f:
    json.dump(result, f, indent=4)


