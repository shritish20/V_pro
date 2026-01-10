from app.models.schemas import StructMetrics

class StructureEngine:
    def get_struct_metrics(self, chain, spot, lot_size) -> StructMetrics:
        if chain.empty or spot == 0: return StructMetrics(0, 0, 0, "NEUTRAL", 0, 0, 0, "NEUTRAL", lot_size)
        subset = chain[(chain['strike'] > spot * 0.90) & (chain['strike'] < spot * 1.10)]
        net_gex = ((subset['ce_gamma'] * subset['ce_oi']).sum() - (subset['pe_gamma'] * subset['pe_oi']).sum()) * spot * lot_size
        total_oi = (chain['ce_oi'].sum() + chain['pe_oi'].sum()) * spot * lot_size
        gex_ratio = abs(net_gex) / total_oi if total_oi > 0 else 0
        pcr = chain['pe_oi'].sum() / chain['ce_oi'].sum() if chain['ce_oi'].sum() > 0 else 1.0
        return StructMetrics(net_gex, gex_ratio, total_oi, "NEUTRAL", pcr, 0, 0, "NEUTRAL", lot_size)
