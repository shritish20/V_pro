import asyncio
import logging
from typing import List, Dict, Optional
from datetime import date, datetime
from app.config import Config
from app.core.data.rest_client import UpstoxRESTClient
from app.database import DatabaseManager

logger = logging.getLogger("VOLGUARD")

class SentinelRiskManager:
    """
    The Brain. Manages Pre-Trade Safety AND Post-Trade Strategy Exits.
    """
    def __init__(self, rest_client: UpstoxRESTClient, db: DatabaseManager):
        self.api = rest_client
        self.db = db
        self.active = False
        self.kill_switch = False
        
        # Real-time metrics
        self.metrics = {"pnl": 0.0, "positions": 0, "available_cash": 0.0}
        
        # Track the active strategy for exit rules
        self.active_trade: Optional[Dict] = None

    async def initialize(self):
        """Syncs Funds, Positions, and loads active trade from DB on startup."""
        # 1. Get Money
        self.metrics["available_cash"] = await self.api.get_funds_and_margin()
        
        # 2. Get Positions
        pos = await self.api.get_net_positions()
        self.metrics["positions"] = len(pos)
        self.metrics["pnl"] = sum(p.get('pnl', 0.0) for p in pos)
        
        # 3. Resume Trade State if crash occurred
        if not self.active_trade and self.metrics["positions"] > 0:
            self.active_trade = self.db.get_active_trade()
            if self.active_trade:
                logger.info(f"📋 Resumed Active Trade: {self.active_trade['strategy']} | Expiry: {self.active_trade['expiry_date']}")

    async def validate_trade(self, legs: List[Dict]) -> bool:
        """
        PRE-TRADE GUARD:
        1. Check Kill Switch
        2. Check Daily Loss Limit
        3. Check REAL Exchange Margin
        """
        if self.kill_switch:
            logger.warning("🚫 Trade Blocked: Kill Switch Active")
            return False

        # Refresh funds before checking
        await self.initialize()

        # Check 1: Existing positions? (Don't stack trades yet)
        if self.metrics["positions"] > 0:
            logger.warning("🚫 Trade Blocked: Existing positions active.")
            return False

        # Check 2: Daily Loss
        if self.metrics["pnl"] < -abs(Config.MAX_DAILY_LOSS):
            logger.error(f"🚫 Trade Blocked: Daily Loss Hit ({self.metrics['pnl']:,.2f})")
            return False

        # Check 3: Real Margin
        required_margin = await self.api.get_margin_required(legs)
        logger.info(f"🛡️ Margin Check: Need ₹{required_margin:,.2f} | Have ₹{self.metrics['available_cash']:,.2f}")

        if required_margin > self.metrics["available_cash"]:
            logger.error("🚫 Trade Blocked: Insufficient Margin")
            return False

        return True

    def register_trade(self, expiry_date: date, entry_premium: float, strategy: str):
        """Called by ExecutionEngine AFTER trade is placed."""
        self.active_trade = {
            'expiry_date': expiry_date,
            'entry_premium': entry_premium,
            'strategy': strategy
        }
        logger.info(f"📝 Strategy Registered: {strategy} | Premium: ₹{entry_premium:,.2f} | Expiry: {expiry_date}")

    async def check_exits(self):
        """
        STRATEGY EXIT RULES:
        1. T-1 Auto-Exit (Thursday -> Wednesday exit)
        2. 50% Profit Target
        3. 50% Stop Loss
        """
        if not self.active_trade or self.metrics["positions"] == 0:
            return
        
        expiry = self.active_trade['expiry_date']
        entry_prem = self.active_trade['entry_premium']
        current_pnl = self.metrics['pnl']
        
        # Calculate Days to Expiry
        today = date.today()
        dte = (expiry - today).days
        
        # --- RULE 1: T-1 EXIT ---
        if dte <= 1:
            logger.warning(f"📅 T-1 AUTO-EXIT TRIGGERED (DTE={dte})")
            await self._exit_positions("T-1_AUTO_EXIT")
            return
        
        # --- RULE 2: 50% PROFIT ---
        target = entry_prem * 0.50
        if current_pnl >= target:
            logger.info(f"💰 PROFIT TARGET HIT: ₹{current_pnl:,.2f} (Target: ₹{target:,.2f})")
            await self._exit_positions("PROFIT_TARGET_50%")
            return
        
        # --- RULE 3: 50% STOP LOSS ---
        stop_loss = -abs(entry_prem * 0.50)
        if current_pnl <= stop_loss:
            logger.error(f"🛑 STOP LOSS HIT: ₹{current_pnl:,.2f} (Limit: ₹{stop_loss:,.2f})")
            await self._exit_positions("STOP_LOSS_50%")
            return

    async def _exit_positions(self, reason: str):
        """Executes the Square Off"""
        logger.warning(f"🚨 EXECUTING EXIT: {reason}")
        
        # 1. API Call to Close All
        success = await self.api.cancel_all_positions()
        
        # 2. DB Update
        final_pnl = self.metrics['pnl']
        self.db.close_trade(reason, final_pnl)
        
        # 3. Reset State
        self.active_trade = None
        self.metrics['positions'] = 0
        logger.info(f"✅ Positions Closed. Final P&L: ₹{final_pnl:,.2f}")

    async def patrol(self):
        """The Heartbeat Loop"""
        self.active = True
        while self.active and not self.kill_switch:
            try:
                # 1. Sync P&L
                pos = await self.api.get_net_positions()
                self.metrics["pnl"] = sum(p.get('pnl', 0.0) for p in pos)
                self.metrics["positions"] = len(pos)

                # 2. Check Strategy Exits
                await self.check_exits()

                # 3. EMERGENCY KILL SWITCH (Daily Loss)
                if self.metrics["pnl"] < -abs(Config.MAX_DAILY_LOSS):
                    logger.critical(f"🚨 DAILY LOSS BREACH: {self.metrics['pnl']:,.2f}")
                    await self._exit_positions("DAILY_LOSS_KILL_SWITCH")
                    self.kill_switch = True
                    break
                
                await asyncio.sleep(5) # Check every 5 seconds
            except Exception as e:
                logger.error(f"Sentinel Patrol Error: {e}")
                await asyncio.sleep(5)
