import asyncio
import logging
import numpy as np
from app.core.data.market_client import AsyncFetcher
from app.database import DatabaseManager
from app.config import Config

logger = logging.getLogger("VOLGUARD")

class SentinelWatchdog:
    def __init__(self, api: AsyncFetcher, db: DatabaseManager):
        self.api = api; self.db = db
        self.active = False
        self.metrics = {"delta": 0.0, "pnl": 0.0, "positions": 0}
        self.pending_execution = False 

    def check_exit_rules(self, pnl, entry_premium, dte):
        if entry_premium == 0: return False, ""
        pct = pnl / entry_premium
        if dte > 3 and pct >= 0.50: return True, "EARLY_WIN_50%"
        if dte <= 1 and pct >= 0.80: return True, "EXPIRY_GRIND_80%"
        if pct <= -0.50: return True, "STOP_LOSS_50%"
        return False, ""

    async def patrol(self):
        self.active = True
        logger.info("🛡️ Sentinel Active (Async)")
        
        while self.active:
            try:
                # Race Condition Fix: Don't check positions if we are mid-execution
                if self.pending_execution:
                    await asyncio.sleep(1)
                    continue

                if Config.PAPER_TRADING:
                    self.metrics['delta'] = np.random.normal(5, 2)
                    self.metrics['pnl'] += np.random.normal(50, 20)
                    if self.metrics['positions'] == 0: 
                         pass 
                    await asyncio.sleep(2)
                    continue

                positions = await self.api.get_positions()
                if not positions:
                    self.metrics = {"delta": 0, "pnl": 0, "positions": 0}
                    await asyncio.sleep(2); continue

                keys = [p['instrument_token'] for p in positions]
                # greeks = await self.api.get_option_greeks(keys) # Future implementation
                
                total_pnl = sum(float(p['pnl']) for p in positions)
                self.metrics['pnl'] = total_pnl
                self.metrics['positions'] = len(positions)
                
                should, reason = self.check_exit_rules(total_pnl, 20000, 3)
                if should: logger.info(f"⚡ EXIT SIGNAL: {reason}")
                
                if total_pnl < -Config.MAX_DAILY_LOSS:
                    logger.critical("🚨 DAILY LOSS HIT"); self.active = False

                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Sentinel Error: {e}"); await asyncio.sleep(5)
