def __getattr__(name):
    if name == "SignalValidator":
        from .signal_validation import SignalValidator
        return SignalValidator
    if name == "PositionValidator":
        from .position_validation import PositionValidator
        return PositionValidator
    if name == "ReturnValidator":
        from .return_validation import ReturnValidator
        return ReturnValidator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
