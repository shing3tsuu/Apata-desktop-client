import time
import logging
import inspect
from typing import TypeVar, ParamSpec, Callable, Optional
from functools import wraps

P = ParamSpec("P")
T = TypeVar("T")

def timer(
    logger: Optional[logging.Logger] = None,
    log_level: int = logging.INFO,  # по умолчанию INFO
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    elapsed = time.perf_counter() - start
                    _log(logger, func.__name__, elapsed, log_level)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                start = time.perf_counter()
                try:
                    return func(*args, **kwargs)
                finally:
                    elapsed = time.perf_counter() - start
                    _log(logger, func.__name__, elapsed, log_level)
            return sync_wrapper
    return decorator

def _log(logger: Optional[logging.Logger], func_name: str, elapsed: float, log_level: int) -> None:
    msg = f"{func_name} finished in {elapsed:.6f} sec"
    if logger is None:
        logger = logging.getLogger(__name__)
    logger.log(log_level, msg)