# Analytical-only interfaces. These classes cannot submit or modify broker orders.
class MarketAnalyst:
    def analyze(self,state): return {"role":"market_analyst","observations":[],"authority":"none"}
class TradeAnalyst:
    def analyze(self,trade): return {"role":"trade_analyst","observations":[],"authority":"none"}
class FailureAnalyst:
    def analyze(self,trades): return {"role":"failure_analyst","patterns":[],"authority":"none"}
class HypothesisGenerator:
    def generate(self,analysis): return {"role":"hypothesis_generator","hypotheses":[],"requires_backtest":True,"authority":"none"}
