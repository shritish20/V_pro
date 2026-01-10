from app.core.data.market_client import SyncFetcher
from app.models.schemas import TradingMandate

class TradeConstructor:
    def build(self, mandate: TradingMandate, api: SyncFetcher):
        if mandate.regime_name == "CASH": return None
        
        spot = api.get_live_spot()
        chain = api.chain(mandate.expiry_date)
        if chain.empty: return None
        
        legs = []
        qty = 50 
        
        if mandate.strategy_type == "STRANGLE":
            short_ce = chain.iloc[(chain['strike'] - spot*1.03).abs().argsort()[:1]].iloc[0] 
            short_pe = chain.iloc[(chain['strike'] - spot*0.97).abs().argsort()[:1]].iloc[0] 
            long_ce = chain.iloc[(chain['strike'] - spot*1.08).abs().argsort()[:1]].iloc[0]
            long_pe = chain.iloc[(chain['strike'] - spot*0.92).abs().argsort()[:1]].iloc[0]
            
        elif mandate.strategy_type == "IRON_CONDOR":
            short_ce = chain.iloc[(chain['strike'] - spot*1.02).abs().argsort()[:1]].iloc[0]
            short_pe = chain.iloc[(chain['strike'] - spot*0.98).abs().argsort()[:1]].iloc[0]
            long_ce = chain.iloc[(chain['strike'] - spot*1.04).abs().argsort()[:1]].iloc[0]
            long_pe = chain.iloc[(chain['strike'] - spot*0.96).abs().argsort()[:1]].iloc[0]
            
        else: # Defensive
            short_pe = chain.iloc[(chain['strike'] - spot*0.98).abs().argsort()[:1]].iloc[0]
            long_pe = chain.iloc[(chain['strike'] - spot*0.96).abs().argsort()[:1]].iloc[0]
            legs.append({'key': long_pe['pe_key'], 'side': 'BUY', 'qty': qty, 'ltp': long_pe['pe_ltp']})
            legs.append({'key': short_pe['pe_key'], 'side': 'SELL', 'qty': qty, 'ltp': short_pe['pe_ltp']})
            return legs

        # Add Legs (Longs, then Shorts)
        legs.append({'key': long_ce['ce_key'], 'side': 'BUY', 'qty': qty, 'ltp': long_ce['ce_ltp']})
        legs.append({'key': long_pe['pe_key'], 'side': 'BUY', 'qty': qty, 'ltp': long_pe['pe_ltp']})
        legs.append({'key': short_ce['ce_key'], 'side': 'SELL', 'qty': qty, 'ltp': short_ce['ce_ltp']})
        legs.append({'key': short_pe['pe_key'], 'side': 'SELL', 'qty': qty, 'ltp': short_pe['pe_ltp']})
        
        return legs
