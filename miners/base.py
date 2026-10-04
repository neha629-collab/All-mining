"""
Base Miner — Abstract class for all mining bots
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This makes adding new miners super easy:

1. Create new file in miners/ e.g., my_miner.py
2. Inherit from BaseMiner
3. Implement required methods
4. Register in miners/registry.py

Example in miners/template.py
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, Awaitable, Tuple

StepCB = Optional[Callable[[str, str], Awaitable[None]]]

class BaseMiner(ABC):
    """
    Abstract base for all miners.
    Each miner must implement these methods.
    """

    # Unique ID, e.g., "atf", "ailab", "hamster", etc.
    miner_id: str = "base"
    display_name: str = "Base Miner"
    description: str = "Base miner template"

    def __init__(self, label: str, init_data: str, extra: Dict[str, Any] = None,
                 proxy: Optional[str] = None, proxy_mgr=None, account_key: str = ""):
        self.label = label
        self.init_data = init_data
        self.extra = extra or {}
        self.proxy = proxy
        self.proxy_mgr = proxy_mgr
        self.account_key = account_key

    @abstractmethod
    async def login(self) -> Tuple[bool, str]:
        """Login and return (success, message)"""
        pass

    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """Get current status/balance"""
        pass

    @abstractmethod
    async def full_cycle(self, config: Dict[str, Any], step_cb: StepCB = None) -> Dict[str, Any]:
        """Run full mining cycle"""
        pass

    async def boost(self, rounds: int = 10, step_cb: StepCB = None) -> Tuple[int, int]:
        """Optional: boost mining speed, returns (success, fail)"""
        return 0, 0

    async def claim(self) -> Tuple[bool, str]:
        """Optional: claim rewards"""
        return False, "Not implemented"

    def get_proxy(self) -> Optional[str]:
        return self.proxy

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "miner_id": self.miner_id,
            "proxy": self.proxy,
        }

    @classmethod
    def extract_init_data(cls, raw: str) -> str:
        """Extract initData from raw input - override per miner"""
        return raw.strip()

    @classmethod
    def detect(cls, text: str) -> bool:
        """Auto-detect if text belongs to this miner"""
        return False
