import time
import threading
from collections import defaultdict

RATE_WINDOW:  int = 60   # rolling window in seconds
RATE_MAX_REQ: int = 10   # max requests per user per window

_lock = threading.Lock()
_user_log: dict[int, list[float]] = defaultdict(list)


def is_rate_limited(user_id: int) -> bool:
    now = time.monotonic()
    cutoff = now - RATE_WINDOW

    with _lock:
        log = _user_log[user_id]
        log[:] = [t for t in log if t > cutoff]

        if len(log) >= RATE_MAX_REQ:
            return True          # limit exceeded, do NOT record

        log.append(now)          # record valid request
        return False