"""
Mining Bot — Professional Config v4.0 — MongoDB + Force Refer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- MongoDB support (motor/pymongo)
- ATF force refer + MRG force refer
- Auto-detect platform from pasted token/URL
- Per-user per-platform slot limit (default 1)
- Powerful proxy with 25+ sources
- Force-join with enhanced checks
"""

import os
from pathlib import Path
from typing import List, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ── Telegram Bot ─────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE").strip()
_admin_env = os.getenv("ADMIN_IDS", "")
if _admin_env:
    try:
        ADMIN_IDS: List[int] = [int(x.strip()) for x in _admin_env.split(",") if x.strip()]
    except ValueError:
        ADMIN_IDS = []
else:
    ADMIN_IDS: List[int] = []

ADMIN_CONTACT: str = os.getenv("ADMIN_CONTACT", "@abdur081").strip()

# ── MongoDB v4.0 NEW ─────────────────────────────────────────────
MONGO_URL: str = os.getenv("MONGO_URL", "").strip()  # e.g. mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "mining_bot").strip()
MONGO_ENABLED: bool = bool(MONGO_URL)

# ── ATF Force Refer v4.0 ─────────────────────────────────────────
# Your ATF bot: https://t.me/ATF_AIRDROP_bot?start=1692540458
ATF_REF_CODE: str = os.getenv("ATF_REF_CODE", "1692540458").strip()
ATF_REF_LINK: str = os.getenv("ATF_REF_LINK", f"https://t.me/ATF_AIRDROP_bot?start={ATF_REF_CODE}").strip()
# Legacy alias
REF_CODE: str = ATF_REF_CODE

# ── MRG Force Refer v4.0 ─────────────────────────────────────────
# Your MRG bot: https://t.me/mrgminerbot/app?startapp=ref_XYDUB621
MRG_REF_CODE: str = os.getenv("MRG_REF_CODE", "ref_XYDUB621").strip()
MRG_REF_LINK: str = os.getenv("MRG_REF_LINK", f"https://t.me/mrgminerbot/app?startapp={MRG_REF_CODE}").strip()
MRG_START_PARAM: str = os.getenv("MRG_START_PARAM", MRG_REF_CODE).strip()  # used for API verify

# ── Logging ──────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_TO_FILE: bool = True
LOG_MAX_BYTES: int = 5 * 1024 * 1024
LOG_BACKUP_COUNT: int = 5

# ── Slot System (NEW v3.0) ───────────────────────────────────────
DEFAULT_SLOT_ATF: int = int(os.getenv("DEFAULT_SLOT_ATF", "1"))
DEFAULT_SLOT_AILAB: int = int(os.getenv("DEFAULT_SLOT_AILAB", "1"))
DEFAULT_SLOT_MRG: int = int(os.getenv("DEFAULT_SLOT_MRG", "1"))
DEFAULT_MAX_TOTAL: int = int(os.getenv("DEFAULT_MAX_TOTAL", "3"))

ABSOLUTE_MAX_SLOT_PER_PLATFORM: int = int(os.getenv("ABSOLUTE_MAX_SLOT", "10"))

# ── Auto-Claim (ATF) ─────────────────────────────────────────────
AUTO_CLAIM_THRESHOLD: float = float(os.getenv("AUTO_CLAIM_THRESHOLD", "1.0"))
CLAIM_CHECK_MINUTES: int = int(os.getenv("CLAIM_CHECK_MINUTES", "5"))
BOOST_ROUNDS: int = int(os.getenv("BOOST_ROUNDS", "10"))
BOOST_INTERVAL_MINUTES: int = int(os.getenv("BOOST_INTERVAL_MINUTES", "20"))
TASK_DELAY_SEC: int = int(os.getenv("TASK_DELAY_SEC", "6"))
SKIP_MANUAL_TASKS: bool = os.getenv("SKIP_MANUAL_TASKS", "True").lower() in ("1", "true", "yes")
CHECK_INTERVAL_MINUTES: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))

# ── Proxy v3.0 — Powerful ────────────────────────────────────────
USE_PROXY: bool = os.getenv("USE_PROXY", "True").lower() in ("1", "true", "yes")
PROXY_REFRESH_HOURS: int = int(os.getenv("PROXY_REFRESH_HOURS", "12"))
PROXY_MIN_HEALTHY: int = int(os.getenv("PROXY_MIN_HEALTHY", "100"))
PROXY_VALIDATE_MAX: int = int(os.getenv("PROXY_VALIDATE_MAX", "1500"))
PROXY_CONCURRENCY: int = int(os.getenv("PROXY_CONCURRENCY", "200"))
PROXY_TIMEOUT_SEC: int = int(os.getenv("PROXY_TIMEOUT_SEC", "10"))
PROXY_SOURCES_EXTRA: str = os.getenv("PROXY_SOURCES_EXTRA", "")

# ── Force Join v3.0 — Powerful ───────────────────────────────────
FORCE_JOIN_ENABLED: bool = os.getenv("FORCE_JOIN_ENABLED", "True").lower() in ("1", "true", "yes")
FORCE_JOIN_CHANNELS: List[Tuple[str, str]] = [
    ("@auto_miningX", "Auto Mining X"),
    ("@ExtremePrimeX", "Extreme Prime X"),
]
_fj_env = os.getenv("FORCE_JOIN_CHANNELS", "")
if _fj_env:
    try:
        FORCE_JOIN_CHANNELS = []
        for item in _fj_env.split(","):
            if ":" in item:
                cid, name = item.split(":", 1)
                FORCE_JOIN_CHANNELS.append((cid.strip(), name.strip()))
            else:
                FORCE_JOIN_CHANNELS.append((item.strip(), item.strip()))
    except Exception:
        pass

FORCE_JOIN_CACHE_TTL: int = int(os.getenv("FORCE_JOIN_CACHE_TTL", "300"))
FORCE_JOIN_STRICT: bool = os.getenv("FORCE_JOIN_STRICT", "True").lower() in ("1", "true", "yes")

# ── AI Lab ───────────────────────────────────────────────────────
AILAB_ENABLED: bool = os.getenv("AILAB_ENABLED", "True").lower() in ("1", "true", "yes")
AILAB_AUTO_START: bool = os.getenv("AILAB_AUTO_START", "True").lower() in ("1", "true", "yes")
AILAB_AUTO_EXCHANGE: bool = os.getenv("AILAB_AUTO_EXCHANGE", "True").lower() in ("1", "true", "yes")
AILAB_AUTO_TASKS: bool = os.getenv("AILAB_AUTO_TASKS", "True").lower() in ("1", "true", "yes")
AILAB_EXCHANGE_MIN: float = float(os.getenv("AILAB_EXCHANGE_MIN", "0.5"))
AILAB_RESTART_GRACE_SEC: int = int(os.getenv("AILAB_RESTART_GRACE_SEC", "30"))
AILAB_KEEPALIVE_MIN: int = int(os.getenv("AILAB_KEEPALIVE_MIN", "25"))
AILAB_TASK_MIN: int = int(os.getenv("AILAB_TASK_MIN", "30"))
AILAB_CHECK_MIN: int = int(os.getenv("AILAB_CHECK_MIN", "10"))

# ── MRG ──────────────────────────────────────────────────────────
MRG_ENABLED: bool = os.getenv("MRG_ENABLED", "True").lower() in ("1", "true", "yes")
MRG_API_BASE: str = os.getenv("MRG_API_BASE", "https://mrg.up.railway.app")
MRG_MINE_THRESHOLD: float = float(os.getenv("MRG_MINE_THRESHOLD", "0.0001"))
MRG_COMMISSION_THRESHOLD: float = float(os.getenv("MRG_COMMISSION_THRESHOLD", "0"))
MRG_AUTO_CLAIM_BONUS: bool = os.getenv("MRG_AUTO_CLAIM_BONUS", "True").lower() in ("1", "true", "yes")
MRG_TASK_FIRST_DELAY: int = int(os.getenv("MRG_TASK_FIRST_DELAY", "15"))
MRG_TASK_REVISIT_DELAY: int = int(os.getenv("MRG_TASK_REVISIT_DELAY", "5"))
MRG_TASK_CLAIM_DELAY: int = int(os.getenv("MRG_TASK_CLAIM_DELAY", "2500"))
MRG_JOIN_RETRY_H: int = int(os.getenv("MRG_JOIN_RETRY_H", "24"))
MRG_ATTEMPT_ADSGRAM: bool = os.getenv("MRG_ATTEMPT_ADSGRAM", "False").lower() in ("1", "true", "yes")
MRG_AUTO_UNLOCK: bool = os.getenv("MRG_AUTO_UNLOCK", "True").lower() in ("1", "true", "yes")
MRG_MAX_UNLOCK_LEVEL: int = int(os.getenv("MRG_MAX_UNLOCK_LEVEL", "1000"))
MRG_CHECK_MINUTES: int = int(os.getenv("MRG_CHECK_MINUTES", "30"))
MRG_TASK_CHECK_MINUTES: int = int(os.getenv("MRG_TASK_CHECK_MINUTES", "30"))
MRG_INITDATA_WARN_H: int = int(os.getenv("MRG_INITDATA_WARN_H", "20"))

# ── Bot UX v4.0 ──────────────────────────────────────────────────
BOT_VERSION: str = "5.2-POWERFUL"
DEFAULT_LANG: str = os.getenv("BOT_LANG", "en")
MAX_ACCOUNTS_PER_USER: int = int(os.getenv("MAX_ACCOUNTS_PER_USER", "10"))
RUN_DELAY_BETWEEN_ACCOUNTS: float = 1.5
ENABLE_LEVELUP_NOTIFY: bool = True
AUTO_RUN_ON_ADD: bool = True

# ── Validation ───────────────────────────────────────────────────
def validate() -> List[str]:
    errors = []
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        errors.append("BOT_TOKEN not set! Set in .env")
    if AUTO_CLAIM_THRESHOLD < 0.1:
        errors.append("AUTO_CLAIM_THRESHOLD too low")
    if PROXY_CONCURRENCY > 400:
        errors.append("PROXY_CONCURRENCY too high")
    if MONGO_URL and not MONGO_URL.startswith(("mongodb://", "mongodb+srv://")):
        errors.append("MONGO_URL invalid — must start with mongodb:// or mongodb+srv://")
    return errors

def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return False
    return user_id in ADMIN_IDS

def is_open_mode() -> bool:
    return len(ADMIN_IDS) == 0

def mongo_info() -> str:
    if not MONGO_URL:
        return "JSON fallback (no MONGO_URL)"
    # mask password
    try:
        from urllib.parse import urlparse
        parsed = urlparse(MONGO_URL)
        host = parsed.hostname or "?"
        return f"MongoDB @ {host} / {MONGO_DB_NAME}"
    except Exception:
        return f"MongoDB / {MONGO_DB_NAME}"
