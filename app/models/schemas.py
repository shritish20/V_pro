from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date

@dataclass
class TimeMetrics:
    current_date: date; weekly_exp: date; monthly_exp: date
    next_weekly_exp: date; dte_weekly: int; dte_monthly: int
    is_gamma_week: bool; is_gamma_month: bool; days_to_next_weekly: int

@dataclass
class VolMetrics:
    spot: float; vix: float
    rv7: float; rv28: float; rv90: float
    garch7: float; garch28: float
    park7: float; park28: float
    vov: float; vov_zscore: float
    ivp_30d: float; ivp_90d: float; ivp_1yr: float
    ma20: float; atr14: float; trend_strength: float
    vol_regime: str; is_fallback: bool
    correlation_risk: float = 0.0 

@dataclass
class StructMetrics:
    net_gex: float; gex_ratio: float; total_oi_value: float
    gex_regime: str; pcr: float; max_pain: float
    skew_25d: float; oi_regime: str; lot_size: int

@dataclass
class EdgeMetrics:
    iv_weekly: float; vrp_rv_weekly: float; vrp_garch_weekly: float; vrp_park_weekly: float
    iv_monthly: float; vrp_rv_monthly: float; vrp_garch_monthly: float; vrp_park_monthly: float
    term_spread: float; term_regime: str; primary_edge: str

@dataclass
class ParticipantData:
    fut_long: float; fut_short: float; fut_net: float
    call_long: float; call_short: float; call_net: float
    put_long: float; put_short: float; put_net: float
    stock_net: float

@dataclass
class ExternalMetrics:
    fii: Optional[ParticipantData]; dii: Optional[ParticipantData]
    pro: Optional[ParticipantData]; client: Optional[ParticipantData]
    fii_net_change: float; flow_regime: str; event_count: int
    event_names: List[str]; event_risk: str; fast_vol: bool; data_date: str

@dataclass
class RegimeScore:
    vol_score: float; struct_score: float; edge_score: float; risk_score: float
    composite: float; confidence: str

@dataclass
class TradingMandate:
    expiry_type: str; expiry_date: date; dte: int
    regime_name: str; strategy_type: str
    allocation_pct: float; max_lots: int; risk_per_lot: float
    score: RegimeScore
    rationale: List[str]; warnings: List[str]
    suggested_structure: str
