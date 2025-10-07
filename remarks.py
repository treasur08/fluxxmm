import json
from datetime import datetime

class ReviewSystem:
    def __init__(self):
        self.filename = "remarks.txt"
        self.load_reviews()

    def load_reviews(self):
        try:
            with open(self.filename, 'r') as f:
                self.reviews = json.load(f)
        except:
            self.reviews = {}

    def save_reviews(self):
        with open(self.filename, 'w') as f:
            json.dump(self.reviews, f, indent=4)

    def add_review(self, seller_id, seller_name, is_positive, deal_type,  buyer_id, buyer_name):
        if seller_id not in self.reviews:
            self.reviews[seller_id] = {
                'name': seller_name,
                'trades': 1,
                'positive': 0,
                'negative': 0,
                'p2p_trades': 0,
                'bs_trades': 0,
                'link': f'tg://user?id={seller_id}',
                'reviewers': {}
            }
        else:
            self.reviews[seller_id]['trades'] += 1

        if str(buyer_id) not in self.reviews[seller_id]['reviewers']:
            self.reviews[seller_id]['reviewers'][str(buyer_id)] = {
                'name': buyer_name,
                'positive': 0,
                'negative': 0
            }

        if is_positive:
            self.reviews[seller_id]['positive'] += 1
            self.reviews[seller_id]['reviewers'][str(buyer_id)]['positive'] += 1
        else:
            self.reviews[seller_id]['negative'] += 1
            self.reviews[seller_id]['reviewers'][str(buyer_id)]['negative'] += 1
        if deal_type == "p2p":
            self.reviews[seller_id]['p2p_trades'] += 1
        elif deal_type == "b_and_s":
            self.reviews[seller_id]['bs_trades'] += 1
            
        self.save_reviews()

    def get_formatted_reviews(self):
        formatted_reviews = {}
        for seller_id, data in self.reviews.items():
            formatted_reviews[seller_id] = {
                'name': data['name'],
                'total_trades': data['trades'],
                'positive_trades': data['positive'],
                'negative_trades': data['negative'],
                'p2p_trades': data.get('p2p_trades', 0),
                'bs_trades': data.get('bs_trades', 0),
                'reviewers': data.get('reviewers', {})
            }
        return formatted_reviews

