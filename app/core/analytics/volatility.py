import numpy as np
import logging
from arch import arch_model
from app.config import Config
from app.models.schemas import VolMetrics

logger = logging.getLogger("VOLGUARD")

class VolatilityEngine:
    def get_correlation_risk(self, nifty, vix):
        if nifty.empty or vix.empty: return 0.0
        return nifty['close'].pct_change().tail(10).corr(vix['close'].pct_change().tail(10))

    def get_vol_metrics(self, nifty_hist, vix_hist, spot_live, vix_live) -> VolMetrics:
        spot = spot_live if spot_live > 0 else (nifty_hist.iloc[-1]['close'] if not nifty_hist.empty else 0)
        vix = vix_live if vix_live > 0 else (vix_hist.iloc[-1]['close'] if not vix_hist.empty else 0)

        returns = np.log(nifty_hist['close'] / nifty_hist['close'].shift(1)).dropna()
        rv7 = returns.rolling(7).std().iloc[-1] * np.sqrt(252) * 100
        rv28 = returns.rolling(28).std().iloc[-1] * np.sqrt(252) * 100
        rv90 = returns.rolling(90).std().iloc[-1] * np.sqrt(252) * 100

        # REAL GARCH IMPLEMENTATION (70% Weight Core)
        is_fallback = False
        try:
            scaled_returns = returns * 100
            model = arch_model(scaled_returns, vol='Garch', p=1, q=1, dist='Normal')
            res = model.fit(disp='off', show_warning=False)
            forecast = res.forecast(horizon=1)
            var_forecast = forecast.variance.iloc[-1, 0]
            garch7 = np.sqrt(var_forecast) * np.sqrt(252)
            garch28 = garch7 
        except Exception as e:
            logger.warning(f"⚠️ GARCH Failed: {e}. Fallback to RV.")
            garch7 = rv7
            garch28 = rv28
            is_fallback = True
        
        const = 1.0 / (4.0 * np.log(2.0))
        park7 = np.sqrt((np.log(nifty_hist['high'] / nifty_hist['low']) ** 2).tail(7).mean() * const) * np.sqrt(252) * 100
        park28 = np.sqrt((np.log(nifty_hist['high'] / nifty_hist['low']) ** 2).tail(28).mean() * const) * np.sqrt(252) * 100

        vix_returns = np.log(vix_hist['close'] / vix_hist['close'].shift(1)).dropna()
        vov = vix_returns.rolling(30).std().iloc[-1] * np.sqrt(252) * 100
        vov_rolling = vix_returns.rolling(30).std() * np.sqrt(252) * 100
        vov_mean = vov_rolling.rolling(60).mean().iloc[-1]
        vov_std = vov_rolling.rolling(60).std().iloc[-1]
        vov_zscore = (vov - vov_mean) / vov_std if vov_std > 0 else 0

        ivp_1yr = (vix_hist['close'].tail(252) < vix).mean() * 100
        ma20 = nifty_hist['close'].rolling(20).mean().iloc[-1]
        
        corr_risk = self.get_correlation_risk(nifty_hist, vix_hist)

        vol_regime = "EXPLODING" if vov_zscore > Config.VOV_CRASH_ZSCORE else \
                     "RICH" if ivp_1yr > Config.HIGH_VOL_IVP else \
                     "CHEAP" if ivp_1yr < Config.LOW_VOL_IVP else "FAIR"

        return VolMetrics(spot, vix, rv7, rv28, rv90, garch7, garch28, park7, park28,
                         vov, vov_zscore, 30, 90, ivp_1yr, ma20, 100, 1.0, vol_regime, is_fallback, corr_risk)
