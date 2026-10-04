from .base import BaseMiner
from .registry import REGISTRY, register_miner, get_miner_class, list_miners, auto_detect_miner, get_miner_info

# Import built-in miners to register them
from . import registry as _registry  # noqa: F401
from . import mrg as _mrg  # noqa: F401 - MRG Token miner

__all__ = [
    "BaseMiner",
    "REGISTRY",
    "register_miner",
    "get_miner_class",
    "list_miners",
    "auto_detect_miner",
    "get_miner_info",
]
