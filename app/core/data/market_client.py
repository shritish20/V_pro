import requests
import pandas as pd
import numpy as np
import aiohttp
from urllib.parse import quote
from datetime import date, timedelta, datetime
from app.config import Config

class SyncFetcher:
    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "accept": "application/json", "Api-Version": "2.0"})

    def get_expiries(self):
        # Mock logic to match original script behavior or fetch real
        # For simplicity based on original script usage:
        today = date.today()
        # Find next Thursday
        thursday = today + timedelta((3 - today.weekday()) % 7)
        if thursday == today: thursday += timedelta(days=7)
        monthly = thursday + timedelta(days=21) # Approximation for structure
        return thursday, monthly, thursday + timedelta(days=7), 50 # lot size

    def get_live_spot(self, key=Config.NIFTY_KEY):
        if Config.PAPER_TRADING: return 24500.0
        try:
            response = self.session.get(f"{Config.UPSTOX_BASE_V3}/market-quote/ltp", params={"instrument_key": key})
            if response.status_code == 200:
                data = response.json().get('data', {})
                api_key = key if key in data else key.replace('|',':')
                return data[api_key]['last_price']
        except: pass
        return 0.0

    def live(self, keys):
        if Config.PAPER_TRADING:
            return {k: 24500.0 if "Nifty" in k else 14.5 for k in keys}
        data = {}
        for k in keys:
            data[k] = self.get_live_spot(k)
        return data

    def history(self, key, days=400):
        if Config.PAPER_TRADING:
             dates = pd.date_range(end=datetime.today(), periods=400)
             data = np.random.normal(15, 2, 400) if "VIX" in key else np.linspace(22000, 24000, 400) + np.random.normal(0, 50, 400)
             return pd.DataFrame({'close': data, 'high': data+10, 'low': data-10}, index=dates)

        try:
            encoded_key = quote(key, safe='')
            to_date = date.today().strftime("%Y-%m-%d")
            from_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
            url = f"{Config.UPSTOX_BASE_V2}/historical-candle/{encoded_key}/day/{to_date}/{from_date}"
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json().get("data", {}).get("candles", [])
                if data:
                    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    return df.set_index('timestamp').astype(float).sort_index()
        except: pass
        return pd.DataFrame()

    def chain(self, expiry_date):
        if Config.PAPER_TRADING:
            strikes = np.arange(23000, 25000, 50)
            rows = []
            for k in strikes:
                rows.append({'strike': k, 'ce_iv': 15, 'pe_iv': 15, 'ce_delta': 0.5, 'pe_delta': -0.5,
                             'ce_gamma': 0.002, 'pe_gamma': 0.002, 'ce_oi': 100000, 'pe_oi': 100000,
                             'ce_ltp': 100, 'pe_ltp': 100, 'ce_key': f"CE_{k}", 'pe_key': f"PE_{k}"})
            return pd.DataFrame(rows)

        try:
            expiry_str = expiry_date.strftime("%Y-%m-%d")
            response = self.session.get(f"{Config.UPSTOX_BASE_V2}/option/chain", params={"instrument_key": Config.NIFTY_KEY, "expiry_date": expiry_str})
            if response.status_code == 200:
                data = response.json().get('data', [])
                return pd.DataFrame([{
                    'strike': x['strike_price'],
                    'ce_iv': x['call_options']['option_greeks'].get('iv', 0),
                    'pe_iv': x['put_options']['option_greeks'].get('iv', 0),
                    'ce_delta': x['call_options']['option_greeks'].get('delta', 0),
                    'pe_delta': x['put_options']['option_greeks'].get('delta', 0),
                    'ce_gamma': x['call_options']['option_greeks'].get('gamma', 0),
                    'pe_gamma': x['put_options']['option_greeks'].get('gamma', 0),
                    'ce_oi': x['call_options']['market_data']['oi'],
                    'pe_oi': x['put_options']['market_data']['oi'],
                    'ce_ltp': x['call_options']['market_data']['ltp'],
                    'pe_ltp': x['put_options']['market_data']['ltp'],
                    'ce_key': x['call_options']['instrument_key'],
                    'pe_key': x['put_options']['instrument_key']
                } for x in data])
        except: pass
        return pd.DataFrame()
    
    def place_order(self, leg):
        if Config.PAPER_TRADING: return "PAPER_ID"
        url = f"{Config.UPSTOX_BASE_V3}/order/place"
        order_type = leg.get('order_type', 'LIMIT')
        price = leg.get('limit_price', 0.0) if order_type == 'LIMIT' else 0.0
        
        payload = {
            "instrument_token": leg['key'], "quantity": leg['qty'], "product": "M", 
            "transaction_type": leg['side'], "order_type": order_type, "price": price
        }
        headers = self.session.headers.copy(); headers["Api-Version"] = "2.0"
        resp = self.session.post(url, headers=headers, json=payload)
        return resp.json().get('data', {}).get('order_id')

    def get_order_status(self, order_id):
        if Config.PAPER_TRADING: 
            return {"status": "complete", "average_price": 100.0, "filled_quantity": 50}
        url = f"{Config.UPSTOX_BASE_V2}/order/details"
        params = {"order_id": order_id}
        resp = self.session.get(url, headers=self.session.headers, params=params)
        if resp.status_code == 200:
            data = resp.json()['data']
            return {
                "status": data['order_status'], 
                "average_price": float(data['average_price'] or 0),
                "filled_quantity": int(data['filled_quantity'] or 0)
            }
        return {"status": "unknown"}

    def cancel_order(self, order_id):
        if Config.PAPER_TRADING: return True
        url = f"{Config.UPSTOX_BASE_V3}/order/cancel"
        params = {"order_id": order_id}
        resp = self.session.delete(url, headers=self.session.headers, params=params)
        return resp.status_code == 200

class AsyncFetcher:
    def __init__(self, token):
        self.headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}

    async def get_positions(self):
        if Config.PAPER_TRADING: return [] 
        url = f"{Config.UPSTOX_BASE_V2}/portfolio/short-term-positions"
        headers = self.headers.copy(); headers["Api-Version"] = "2.0"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('data', [])
        return []

    async def get_option_greeks(self, instrument_keys):
        if not instrument_keys: return []
        url = f"{Config.UPSTOX_BASE_V3}/market-quote/option-greek"
        params = {"instrument_key": ",".join(instrument_keys)}
        headers = self.headers.copy(); headers["Api-Version"] = "2.0"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('data', {})
        return {}
