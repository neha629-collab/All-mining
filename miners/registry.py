"""
Miner Registry — Central place to register all miners
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Add new miners here to make them available in bot.

Usage:
    from miners.registry import REGISTRY, get_miner_class

    miner_class = get_miner_class("atf")
    miner = miner_class(label, init_data, proxy=...)
"""

from typing import Dict, Type, List, Optional
from .base import BaseMiner

# Import miners here
# We'll lazy import to avoid circular deps

REGISTRY: Dict[str, Type[BaseMiner]] = {}

def register_miner(cls: Type[BaseMiner]):
    """Decorator to register miner"""
    REGISTRY[cls.miner_id] = cls
    return cls

def get_miner_class(miner_id: str) -> Optional[Type[BaseMiner]]:
    return REGISTRY.get(miner_id)

def list_miners() -> List[str]:
    return list(REGISTRY.keys())

def get_miner_info(miner_id: str) -> Dict:
    cls = REGISTRY.get(miner_id)
    if not cls:
        return {}
    return {
        "id": cls.miner_id,
        "name": cls.display_name,
        "description": cls.description,
    }

def auto_detect_miner(text: str) -> Optional[str]:
    """Try to detect miner type from text"""
    # Import here to avoid circular
    try:
        from utils.extractors import detect_miner_type
        detected = detect_miner_type(text)
        if detected and detected in REGISTRY:
            return detected
    except Exception:
        pass

    # Try each miner's detect method
    for miner_id, cls in REGISTRY.items():
        try:
            if cls.detect(text):
                return miner_id
        except Exception:
            continue
    return None

# ── Register built-in miners ───────────────────────────────────

# We register ATF and AILab via wrapper classes
# These wrappers use existing atf_api and ailab_api

from atf_api import ATFSession
from ailab_api import AILabSession, extract_ailab_init_data
from utils.extractors import extract_init_data

@register_miner
class ATFWrapper(BaseMiner):
    miner_id = "atf"
    display_name = "ATF Miner"
    description = "ATF Miners — auto claim, boost, tasks"

    def __init__(self, label: str, init_data: str, extra: Dict = None,
                 proxy: Optional[str] = None, proxy_mgr=None, account_key: str = ""):
        super().__init__(label, init_data, extra, proxy, proxy_mgr, account_key)
        self._session = ATFSession(
            name=label,
            init_data=init_data,
            tg_id=extra.get("tg_id", 0) if extra else 0,
            username=extra.get("username", "") if extra else "",
            device_id=extra.get("device_id", "") if extra else "",
            proxy=proxy,
            proxy_mgr=proxy_mgr,
            account_key=account_key,
        )

    async def login(self):
        return await self._session.login(ref_code=extra.get("ref_code", "") if (extra := self.extra) else "")

    async def get_status(self):
        ok, _ = await self._session.login()
        if not ok:
            return {"ok": False}
        await self._session.sync()
        return self._session.user_data

    async def full_cycle(self, config, step_cb=None):
        return await self._session.full_cycle(config, step_cb=step_cb)

    async def boost(self, rounds=10, step_cb=None):
        return await self._session.run_boosts(rounds, step_cb=step_cb)

    @classmethod
    def extract_init_data(cls, raw: str) -> str:
        return extract_init_data(raw)

    @classmethod
    def detect(cls, text: str) -> bool:
        return "atfminers.asloni.online" in text.lower()

@register_miner
class AILabWrapper(BaseMiner):
    miner_id = "ailab"
    display_name = "AI Lab Agent"
    description = "AI Lab — auto mining, exchange, tasks"

    def __init__(self, label: str, init_data: str, extra: Dict = None,
                 proxy: Optional[str] = None, proxy_mgr=None, account_key: str = ""):
        super().__init__(label, init_data, extra, proxy, proxy_mgr, account_key)
        def _persist(new_session: str):
            try:
                import db
                owner = extra.get("owner_id", 0) if extra else 0
                if owner:
                    db.ai_update(owner, label, session=new_session)
            except Exception:
                pass

        self._session = AILabSession(
            name=label,
            init_data=init_data,
            session_token=extra.get("session", "") if extra else "",
            proxy=proxy,
            proxy_mgr=proxy_mgr,
            account_key=account_key,
            on_session_change=_persist,
        )

    async def login(self):
        return await self._session.login()

    async def get_status(self):
        return await self._session.status()

    async def full_cycle(self, config, step_cb=None):
        return await self._session.full_cycle(config, step_cb=step_cb)

    @classmethod
    def extract_init_data(cls, raw: str) -> str:
        return extract_ailab_init_data(raw)

    @classmethod
    def detect(cls, text: str) -> bool:
        return "ailab-agent.online" in text.lower()
