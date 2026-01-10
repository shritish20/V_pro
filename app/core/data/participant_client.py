import requests
import io
import pandas as pd
import pytz
from datetime import datetime, timedelta
from app.models.schemas import ParticipantData
from app.config import Config

class ParticipantDataFetcher:
    @staticmethod
    def get_trading_dates():
        tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(tz)
        dates = []
        candidate = now
        if candidate.hour < 18 or candidate.hour >= 24:
            candidate -= timedelta(days=1)
        while len(dates) < 2:
            if candidate.weekday() < 5:
                dates.append(candidate)
            candidate -= timedelta(days=1)
        return dates

    @staticmethod
    def fetch_oi_csv(date_obj):
        date_str = date_obj.strftime('%d%m%Y')
        url = f"https://archives.nseindia.com/content/nsccl/fao_participant_oi_{date_str}.csv"
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                content = r.content.decode('utf-8')
                lines = content.splitlines()
                for idx, line in enumerate(lines[:20]):
                    if "Future Index Long" in line:
                        df = pd.read_csv(io.StringIO(content), skiprows=idx)
                        df.columns = df.columns.str.strip()
                        return df
        except: pass
        return None

    @classmethod
    def fetch_participant_metrics(cls):
        dates = cls.get_trading_dates()
        df_today = cls.fetch_oi_csv(dates[0])
        if df_today is None: return None, None, 0.0, dates[0].strftime('%d-%b-%Y')
        return cls.process_participant_data(df_today), {}, 0, dates[0].strftime('%d-%b-%Y')

    @staticmethod
    def process_participant_data(df):
        data = {}
        for p in ["FII", "DII", "Client", "Pro"]:
            try:
                row = df[df['Client Type'].astype(str).str.contains(p, case=False, na=False)].iloc[0]
                data[p] = ParticipantData(
                    float(row['Future Index Long']), float(row['Future Index Short']),
                    float(row['Future Index Long']) - float(row['Future Index Short']),
                    0,0,0,0,0,0,0
                )
            except: data[p] = None
        return data
