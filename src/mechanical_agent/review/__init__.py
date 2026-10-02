"""Public reviewer API, loaded lazily so the module CLI runs cleanly."""

__all__ = ["ReviewResult", "review_engineering_result"]


def __getattr__(name: str):
    if name in __all__:
        from . import engineering_result
        return getattr(engineering_result, name)
    raise AttributeError(name)
