"""
Formatters — human readable outputs
"""

import time
from typing import Dict

def hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

def hms_short(sec: float) -> str:
    sec = max(0, int(sec))
    h, r = divmod(sec, 3600)
    return f"{h:02d}:{r//60:02d}:{r%60:02d}"

def fmt_atf_balance(val: float) -> str:
    return f"{val:.4f} ATF"

def fmt_usd(val: float) -> str:
    return f"${val:.6f}"

def fmt_mining_status(u: Dict) -> str:
    now = int(time.time())
    start = int(u.get("last_mining_start") or 0)
    freezes = int(u.get("mining_freezes_at") or 0)
    frozen = bool(u.get("mining_frozen"))

    if frozen:
        return "❄️ Frozen (claim needed)"
    if freezes and now >= freezes:
        return "✅ READY TO CLAIM!"
    if start and freezes:
        left = max(0, freezes - now)
        return f"⛏ Mining ({hms(left)} left)"
    if start:
        return "⛏ Mining active"
    return "💤 Idle"

def fmt_proxy_short(proxy: str) -> str:
    if not proxy:
        return "DIRECT"
    # Hide credentials if present
    try:
        if "@" in proxy:
            # scheme://user:pass@host:port -> scheme://***@host:port
            scheme, rest = proxy.split("://", 1)
            if "@" in rest:
                _, hostport = rest.rsplit("@", 1)
                return f"{scheme}://***@{hostport}"
    except Exception:
        pass
    return proxy

def truncate(text: str, max_len: int = 100) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len-3] + "..."
