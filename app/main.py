import sys
import os
import asyncio
import logging
import traceback
from datetime import date, datetime, timedelta

from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.logging import RichHandler

# Imports
from app.config import Config
from app.database import DatabaseManager
from app.core.data.rest_client import UpstoxRESTClient
from app.core.data.stream_client import UpstoxStreamManager
from app.lifecycle.sentinel import SentinelRiskManager

# Analytics Engines
from app.core.analytics.volatility import VolatilityEngine
from app.core.analytics.structure import StructureEngine
from app.core.analytics.edge import EdgeEngine
from app.core.analytics.regime import RegimeEngine
from app.core.trading.strategies import TradeConstructor
from app.core.trading.executor import ExecutionEngine
from app.models.schemas import TimeMetrics

# Setup Logging
logging.basicConfig(
    level="INFO", format="%(message)s", datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("VOLGUARD")

def render_ui(mandate, sentinel, prices):
    layout = Layout()
    layout.split_column(Layout(name="header", size=3), Layout(name="body"))
    
    status = "KILL SWITCH ACTIVE" if sentinel.kill_switch else "SYSTEM ACTIVE"
    style = "bold white on red" if sentinel.kill_switch else "bold white on blue"
    
    layout["header"].update(Panel(f"VOLGUARD PRO | {status} | {datetime.now().strftime('%H:%M:%S')}", style=style))
    
    t = Table(expand=True)
    t.add_column("Metric"); t.add_column("Value")
    t.add_row("Nifty Spot", f"{prices.get(Config.NIFTY_KEY, 0):,.2f}")
    t.add_row("India VIX", f"{prices.get(Config.VIX_KEY, 0):.2f}")
    t.add_row("---", "---")
    
    pnl_color = "green" if sentinel.metrics['pnl'] >= 0 else "red"
    t.add_row("Net P&L", f"[bold {pnl_color}]{sentinel.metrics['pnl']:,.2f}[/]")
    t.add_row("Cash Available", f"₹{sentinel.metrics['available_cash']:,.2f}")
    t.add_row("Active Pos", str(sentinel.metrics['positions']))
    
    if sentinel.active_trade:
        t.add_row("---", "---")
        t.add_row("Active Strategy", sentinel.active_trade['strategy'])
        t.add_row("Entry Premium", f"₹{sentinel.active_trade['entry_premium']:,.2f}")
        t.add_row("Expiry", str(sentinel.active_trade['expiry_date']))

    layout["body"].update(Panel(t, title="COCKPIT"))
    return layout

async def main():
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "")
    if not token and not Config.PAPER_TRADING:
        print("[red]Missing Token[/]"); return

    # 1. Initialize Infrastructure
    db = DatabaseManager()
    rest_api = UpstoxRESTClient(token)
    stream_manager = UpstoxStreamManager(token)
    
    # 2. Risk Manager (Sentinel)
    sentinel = SentinelRiskManager(rest_api, db)
    await sentinel.initialize()
    asyncio.create_task(sentinel.patrol())

    # 3. Execution Engine (Pass Sentinel Here!)
    executor = ExecutionEngine(rest_api, db, sentinel) 
    
    # 4. Analytics Engines
    vol_engine = VolatilityEngine()
    struct_engine = StructureEngine()
    edge_engine = EdgeEngine()
    regime_engine = RegimeEngine()
    constructor = TradeConstructor()

    # 5. Start Streams
    loop = asyncio.get_running_loop()
    stream_manager.start(loop, [Config.NIFTY_KEY, Config.VIX_KEY])
    
    # 6. Fetch History
    today = date.today().strftime("%Y-%m-%d")
    past = (date.today() - timedelta(days=400)).strftime("%Y-%m-%d")
    nifty_h, vix_h = await asyncio.gather(
        rest_api.get_historical_candles(Config.NIFTY_KEY, "day", today, past),
        rest_api.get_historical_candles(Config.VIX_KEY, "day", today, past)
    )

    # 7. Expiry Setup (Simple calculation)
    today_dt = date.today()
    weekly_exp = today_dt + timedelta((3-today_dt.weekday()) % 7)
    
    prices = {Config.NIFTY_KEY: 0.0, Config.VIX_KEY: 0.0}
    console = Console()
    
    with Live(render_ui(None, sentinel, prices), refresh_per_second=2, console=console) as live:
        while True:
            try:
                # A. Consume Streams
                while not stream_manager.market_queue.empty():
                    msg = await stream_manager.market_queue.get()
                    if 'feeds' in msg:
                        for k, v in msg['feeds'].items():
                            if 'ltpc' in v: prices[k] = v['ltpc']['lp']
                            elif 'ff' in v: prices[k] = v['ff']['marketFF']['ltpc']['ltp']

                # B. Strategy Logic (Only if no positions active)
                spot = prices.get(Config.NIFTY_KEY, 0)
                
                if spot > 0 and sentinel.metrics['positions'] == 0:
                    # 1. Fetch Chain
                    w_chain = await rest_api.get_option_chain(Config.NIFTY_KEY, str(weekly_exp))
                    
                    # 2. Analytics (Placeholder for data conversion)
                    # For demo purposes, we assume engines handle raw data or we add conversion here
                    
                    # 3. Generate Mandate (Placeholder)
                    mandate = None 
                    
                    # 4. Execute?
                    if mandate and mandate.allocation_pct > 0:
                        legs = constructor.build(mandate, rest_api)
                        
                        # Validate & Execute
                        if await sentinel.validate_trade(legs):
                            await executor.execute(legs, mandate)

                live.update(render_ui(None, sentinel, prices))
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Loop Error: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
