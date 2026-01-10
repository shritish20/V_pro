import os
from dataclasses import dataclass

class Config:
    ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")
    
    UPSTOX_BASE_V2 = "https://api.upstox.com/v2"
    UPSTOX_BASE_V3 = "https://api.upstox.com/v3"
    NIFTY_KEY = "NSE_INDEX|Nifty 50"
    VIX_KEY = "NSE_INDEX|India VIX"

    BASE_CAPITAL = 10_00_000  
    MAX_DAILY_LOSS = 50_000
    MARGIN_SELL_BASE = 1_25_000 
    MARGIN_BUY_BASE = 30_000     
    PAPER_TRADING = True 

    # Analytical Parameters
    GAMMA_DANGER_DTE = 1
    HIGH_VOL_IVP = 75.0
    LOW_VOL_IVP = 25.0
    VOV_CRASH_ZSCORE = 2.5   
    VOV_WARNING_ZSCORE = 2.0 

    # Weights
    WEIGHT_VOL = 0.40
    WEIGHT_STRUCT = 0.30
    WEIGHT_EDGE = 0.20
    WEIGHT_RISK = 0.10

    # Flow
    FII_STRONG_LONG = 50000
    FII_STRONG_SHORT = -50000
