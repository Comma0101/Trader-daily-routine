def __getattr__(name):
    if name == "FuturesData":
        from .futures import FuturesData
        return FuturesData
    if name == "COTData":
        from .cot import COTData
        return COTData
    if name == "BenchmarkData":
        from .benchmarks import BenchmarkData
        return BenchmarkData
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
