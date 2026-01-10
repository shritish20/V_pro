import sys
import os
import asyncio
import logging
from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.logging import RichHandler
from logging.handlers import RotatingFileHandler
from datetime import date

# Import from our new modules
from app.config import Config
from app.database import DatabaseManager
from app.core.data.market_client import SyncFetcher, AsyncFetcher
from app.core.data.participant_client import ParticipantDataFetcher
from app.core.analytics.volatility import VolatilityEngine
from app.core.analytics.structure import StructureEngine
from app.core.analytics.edge import EdgeEngine
from app.core.analytics.regime import RegimeEngine
from app.core.trading.strategies import TradeConstructor
from app.core.trading.executor import ExecutionEngine
from app.lifecycle.sentinel import SentinelWatchdog
from app.models.schemas import TimeMetrics, ExternalMetrics

# Setup Logging
logging.basicConfig(
    level="INFO", format="%(message)s", datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True), RotatingFileHandler("volguard.log", maxBytes=5*1024*1024)]
)
logger = logging.getLogger("VOLGUARD")

def render_ui(mandate, sentinel):
    layout = Layout()
    layout.split_column(Layout(name="header", size=3), Layout(name="body"))
    mode = "PAPER" if Config.PAPER_TRADING else "LIVE"
    layout["header"].update(Panel(f"VOLGUARD v33.0 PRO | {mode}", style="bold white on blue"))
    
    table = Table(expand=True)
    table.add_column("Metric"); table.add_column("Value")
    if mandate:
        table.add_row("Regime", mandate.regime_name)
        table.add_row("Strategy", mandate.strategy_type)
        table.add_row("Alloc", f"{mandate.allocation_pct}%")
    else:
        table.add_row("Status", "Analyzing...")
        
    table.add_row("Net Delta", f"{sentinel.metrics['delta']:.2f}")
    table.add_row("Open P&L", f"₹{sentinel.metrics['pnl']:,.2f}")
    layout["body"].update(Panel(table, title="COCKPIT"))
    return layout

async def main():
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "")
    if not token and not Config.PAPER_TRADING:
        print("❌ Token Missing"); return

    db = DatabaseManager()
    sync_api = SyncFetcher(token)
    async_api = AsyncFetcher(token)
    
    # Initialize Engines
    vol_engine = VolatilityEngine()
    struct_engine = StructureEngine()
    edge_engine = EdgeEngine()
    regime_engine = RegimeEngine()
    constructor = TradeConstructor()
    executor = ExecutionEngine(sync_api, db)
    sentinel = SentinelWatchdog(async_api, db)
    part_fetcher = ParticipantDataFetcher()

    asyncio.create_task(sentinel.patrol())
    console = Console()
    
    with Live(console=console, refresh_per_second=2) as live:
        while True:
            # 1. Fetch Data (Thread-Safe Wrapper)
            # CRITICAL: Run blocking sync calls in a thread so Sentinel keeps running
            p_data, p_yest, fii_net, d_date = await asyncio.to_thread(part_fetcher.fetch_participant_metrics)
            live_data = await asyncio.to_thread(sync_api.live, [Config.NIFTY_KEY, Config.VIX_KEY])
            nifty_h = await asyncio.to_thread(sync_api.history, Config.NIFTY_KEY)
            vix_h = await asyncio.to_thread(sync_api.history, Config.VIX_KEY)
            weekly, monthly, next_w, lot = await asyncio.to_thread(sync_api.get_expiries)
            
            if weekly:
                # 2. Analytics
                # Helper to calculate TimeMetrics locally
                today = date.today()
                dte_w = (weekly - today).days
                dte_m = (monthly - today).days
                dte_nw = (next_w - today).days
                t_metrics = TimeMetrics(today, weekly, monthly, next_w, dte_w, dte_m,
                          dte_w <= Config.GAMMA_DANGER_DTE, dte_m <= Config.GAMMA_DANGER_DTE, dte_nw)
                
                w_chain = await asyncio.to_thread(sync_api.chain, weekly)
                m_chain = await asyncio.to_thread(sync_api.chain, monthly)
                
                v_metrics = vol_engine.get_vol_metrics(nifty_h, vix_h, live_data.get(Config.NIFTY_KEY,0), live_data.get(Config.VIX_KEY,0))
                s_metrics = struct_engine.get_struct_metrics(w_chain, v_metrics.spot, lot)
                e_metrics = edge_engine.get_edge_metrics(w_chain, m_chain, v_metrics.spot, v_metrics)
                
                # Helper for External Metrics
                flow = "NEUTRAL"
                if p_data and p_data.get('FII'):
                    if p_data['FII'].fut_net > Config.FII_STRONG_LONG: flow = "STRONG_LONG"
                    elif p_data['FII'].fut_net < Config.FII_STRONG_SHORT: flow = "STRONG_SHORT"
                ex_metrics = ExternalMetrics(p_data.get('FII'), None, None, None, fii_net, flow, 0, [], "LOW", False, d_date)
                
                # 3. Regime & Mandate
                score = regime_engine.calculate_scores(v_metrics, s_metrics, e_metrics, ex_metrics, t_metrics, "WEEKLY")
                mandate = regime_engine.generate_mandate(score, v_metrics, t_metrics.dte_weekly, weekly)
                
                # 4. Execution
                if mandate.allocation_pct > 0 and sentinel.metrics['positions'] == 0 and not sentinel.pending_execution:
                    sentinel.pending_execution = True
                    legs = await asyncio.to_thread(constructor.build, mandate, sync_api)
                    if legs:
                        # Execution is blocking, run in thread
                        await asyncio.to_thread(executor.execute, legs, mandate)
                        sentinel.metrics['positions'] = 4
                        await asyncio.sleep(5)
                    sentinel.pending_execution = False

                live.update(render_ui(mandate, sentinel))
            
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down.")
