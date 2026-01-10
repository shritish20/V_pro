from app.models.schemas import EdgeMetrics, VolMetrics

class EdgeEngine:
    def get_edge_metrics(self, weekly_chain, monthly_chain, spot, vol: VolMetrics) -> EdgeMetrics:
        if weekly_chain.empty or spot == 0: return EdgeMetrics(0,0,0,0,0,0,0,0,0,"FLAT","NONE")
        atm_idx = (weekly_chain['strike'] - spot).abs().argsort()[:1]
        iv_weekly = weekly_chain.iloc[atm_idx]['ce_iv'].values[0]
        
        # GARCH is now real, so VRP is high quality
        vrp_rv_weekly = iv_weekly - vol.rv7
        vrp_garch_weekly = iv_weekly - vol.garch7 
        vrp_park_weekly = iv_weekly - vol.park7
        
        return EdgeMetrics(iv_weekly, vrp_rv_weekly, vrp_garch_weekly, vrp_park_weekly,
                          0, 0, 0, 0, 0, "FLAT", "SHORT_VEGA")
