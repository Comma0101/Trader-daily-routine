def __getattr__(name):
    if name == "TrendModel":
        from .trend import TrendModel
        return TrendModel
    if name == "VolatilityEstimator":
        from .volatility import VolatilityEstimator
        return VolatilityEstimator
    if name == "PortfolioConstructor":
        from .portfolio import PortfolioConstructor
        return PortfolioConstructor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
