"""
Extractors — robust initData parsing for ATF & AI Lab
Fixed bugs from v1:
- Proper URL fragment handling
- Double decoding safe
- HTML entity decode
- Validation
"""

import re
import urllib.parse
from typing import Optional, Tuple


def extract_init_data(raw: str) -> str:
    """
    Accepts 4 formats:
    A) Full URL: https://...#tgWebAppData=<encoded>
    B) Raw initData: query_id=...&user=...&hash=...
    C) Short form: user=...&hash=...
    D) HTML encoded (&amp;)
    Returns cleaned initData or empty string.
    """
    if not raw:
        return ""
    raw = raw.strip().strip('"').strip("'")
    raw = raw.replace("&amp;", "&")

    # Format A: URL with fragment
    if "tgWebAppData=" in raw:
        try:
            # Split by # and parse fragment
            if "#" in raw:
                frag = raw.split("#", 1)[1]
                # Fragment may be URL encoded query string
                # Try parse_qs first
                params = urllib.parse.parse_qs(frag, keep_blank_values=True)
                tgd = params.get("tgWebAppData", [""])[0]
                if tgd:
                    # tgd is encoded initData
                    decoded = urllib.parse.unquote(tgd)
                    # It may still be double encoded
                    for _ in range(2):
                        if "%" in decoded:
                            nd = urllib.parse.unquote(decoded)
                            if nd == decoded:
                                break
                            decoded = nd
                        else:
                            break
                    return decoded
            # Fallback: extract after tgWebAppData=
            m = re.search(r"tgWebAppData=([^&]+)", raw)
            if m:
                return urllib.parse.unquote(m.group(1))
        except Exception:
            pass

    # Format B/C/D: already initData
    # Validate it has hash and user/query_id
    parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
    if parsed.get("hash") and (parsed.get("query_id") or parsed.get("user")):
        return raw

    # If it contains atfminers URL but no fragment, invalid
    if "atfminers.asloni.online" in raw and "tgWebAppData" not in raw:
        return ""

    # Last resort: if it looks like initData (has user= and hash=), return it
    if "user=" in raw and "hash=" in raw:
        return raw

    return ""


def extract_ailab_init_data(raw: str) -> str:
    """
    AI Lab initData extractor - robust version
    """
    if not raw:
        return ""
    s = raw.strip().strip('"').strip("'")
    s = s.replace("&amp;", "&")

    if "tgWebAppData=" in s:
        try:
            # Get fragment after #
            frag = s.split("#", 1)[1] if "#" in s else s
            # Find tgWebAppData value
            for part in frag.split("&"):
                if part.startswith("tgWebAppData="):
                    s = part[len("tgWebAppData="):]
                    break
            else:
                # No & separator, maybe whole frag is the value
                if "tgWebAppData=" in frag:
                    s = frag.split("tgWebAppData=", 1)[1].split("&tgWebApp")[0]
            # Double decode up to 3 times
            for _ in range(3):
                if s.startswith("user="):
                    break
                decoded = urllib.parse.unquote(s)
                if decoded == s:
                    break
                s = decoded
        except Exception:
            pass

    # Ensure we start at user=
    if not s.startswith("user=") and "user=" in s:
        s = s[s.index("user="):]

    return s if s.startswith("user=") else ""


def extract_tg_id(init_data: str) -> int:
    """Extract Telegram user ID from initData JSON"""
    try:
        decoded = urllib.parse.unquote(init_data)
        m = re.search(r'"id"\s*:\s*(\d+)', decoded)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0


def extract_username(init_data: str) -> str:
    try:
        decoded = urllib.parse.unquote(init_data)
        m = re.search(r'"username"\s*:\s*"([^"]+)"', decoded)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def extract_first_name(init_data: str) -> str:
    try:
        decoded = urllib.parse.unquote(init_data)
        m = re.search(r'"first_name"\s*:\s*"([^"]+)"', decoded)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def extract_mrg_init_data(raw: str) -> str:
    """MRG initData extractor - supports both query_id= and user= formats"""
    if not raw:
        return ""
    s = raw.strip().strip('"').strip("'")
    s = s.replace("&amp;", "&")
    if "tgWebAppData=" in s:
        try:
            frag = s.split("#", 1)[1] if "#" in s else s
            for part in frag.split("&"):
                if part.startswith("tgWebAppData="):
                    s = part[len("tgWebAppData="):]
                    break
            else:
                if "tgWebAppData=" in s:
                    s = s.split("tgWebAppData=", 1)[1].split("&tgWebApp")[0]
            # Decode up to 3 times, but keep full initData
            for _ in range(4):
                dec = urllib.parse.unquote(s)
                if dec == s:
                    break
                s = dec
        except Exception:
            pass

    # Find the real start - either query_id= or user=
    # Telegram initData can start with query_id=... or user=...
    low = s.lower()
    q_idx = low.find("query_id=")
    u_idx = low.find("user=")

    start_idx = -1
    if q_idx != -1 and u_idx != -1:
        start_idx = min(q_idx, u_idx)
    elif q_idx != -1:
        start_idx = q_idx
    elif u_idx != -1:
        start_idx = u_idx

    if start_idx > 0:
        s = s[start_idx:]
    elif start_idx == -1:
        return ""

    # Must contain hash=
    if "hash=" not in s:
        return ""

    # Valid if starts with query_id= or user=
    if s.startswith("query_id=") or s.startswith("user="):
        return s
    return ""

def detect_miner_type(text: str) -> Optional[str]:
    """
    Auto-detect miner type from pasted text
    Returns: 'atf', 'ailab', 'mrg' or None
    """
    if not text:
        return None
    low = text.lower()
    # MRG first (most specific)
    if any(k in low for k in ["mrgtoken.xyz", "mrgminerbot", "mrg.up.railway.app", "app.mrgtoken"]):
        return "mrg"
    if "ailab-agent.online" in low:
        return "ailab"
    if "atfminers.asloni.online" in low:
        return "atf"
    if "ailab" in low:
        return "ailab"
    if "atf" in low and "tgwebappdata" in low:
        return "atf"
    if "user=" in low and "hash=" in low:
        # Generic initData, ambiguous - default to ATF for backward compat
        # Caller should use auto_detect_miner from registry for better detection
        return "atf"
    return None
