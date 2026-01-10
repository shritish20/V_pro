from app.config import Config
from app.models.schemas import RegimeScore, TradingMandate, VolMetrics, StructMetrics, EdgeMetrics, ExternalMetrics, TimeMetrics
from datetime import date

class RegimeEngine:
    def calculate_scores(self, vol: VolMetrics, struct: StructMetrics, edge: EdgeMetrics,
                        external: ExternalMetrics, time: TimeMetrics, expiry_type: str) -> RegimeScore:

        garch_val = edge.vrp_garch_weekly
        park_val = edge.vrp_park_weekly
        rv_val = edge.vrp_rv_weekly
        # 70% Weight on the now-Real GARCH
        weighted_vrp = (garch_val * 0.70) + (park_val * 0.15) + (rv_val * 0.15)

        edge_score = 5.0
        if weighted_vrp > 4.0: edge_score += 3.0
        elif weighted_vrp > 2.0: edge_score += 2.0
        elif weighted_vrp > 1.0: edge_score += 1.0
        elif weighted_vrp < 0: edge_score -= 3.0
        edge_score = max(0, min(10, edge_score))

        vol_score = 5.0
        if vol.vov_zscore > Config.VOV_CRASH_ZSCORE: vol_score = 0.0 
        elif vol.vov_zscore > Config.VOV_WARNING_ZSCORE: vol_score -= 3.0
        elif vol.vov_zscore < 1.5: vol_score += 1.5

        if vol.ivp_1yr > Config.HIGH_VOL_IVP: vol_score += 0.5
        elif vol.ivp_1yr < Config.LOW_VOL_IVP: vol_score -= 2.5
        else: vol_score += 1.0
        
        if vol.correlation_risk > 0.3: vol_score -= 2.0

        vol_score = max(0, min(10, vol_score))

        struct_score = 5.0
        if struct.gex_regime == "STICKY": struct_score += 1.0
        if 0.9 < struct.pcr < 1.1: struct_score += 1.0
        struct_score = max(0, min(10, struct_score))

        risk_score = 10.0
        if external.flow_regime == "STRONG_SHORT": risk_score -= 3.0
        if time.is_gamma_week and expiry_type == "WEEKLY": risk_score -= 2.0
        
        risk_score = max(0, min(10, risk_score))

        composite = (vol_score * Config.WEIGHT_VOL + struct_score * Config.WEIGHT_STRUCT +
                     edge_score * Config.WEIGHT_EDGE + risk_score * Config.WEIGHT_RISK)

        confidence = "HIGH" if composite >= 6.5 else "LOW"
        return RegimeScore(vol_score, struct_score, edge_score, risk_score, composite, confidence)

    def generate_mandate(self, score: RegimeScore, vol: VolMetrics, dte: int, expiry: date) -> TradingMandate:
        if score.composite >= 7.5:
            regime = "AGGRESSIVE_SHORT"; strategy = "STRANGLE"; alloc = 60.0
        elif score.composite >= 6.0:
            regime = "MODERATE_SHORT"; strategy = "IRON_CONDOR"; alloc = 40.0
        elif score.composite >= 4.0:
            regime = "DEFENSIVE"; strategy = "CREDIT_SPREAD"; alloc = 20.0
        else:
            regime = "CASH"; strategy = "NONE"; alloc = 0.0
            
        return TradingMandate("WEEKLY", expiry, dte, regime, strategy, alloc, 0, 0, score, [], [], strategy)
