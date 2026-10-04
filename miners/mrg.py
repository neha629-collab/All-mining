"""
MRG Miner — Wrapper for mrg_api.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Registers as miner_id = "mrg"
"""

from typing import Dict, Any, Tuple, Optional
from .base import BaseMiner, StepCB
from .registry import register_miner

@register_miner
class MRGWrapper(BaseMiner):
    miner_id = "mrg"
    display_name = "MRG Token"
    description = "MRG (app.mrgtoken.xyz) — mine, tasks, squad, boost, auto-refresh"

    def __init__(self, label: str, init_data: str, extra: Dict[str, Any] = None,
                 proxy: Optional[str] = None, proxy_mgr=None, account_key: str = ""):
        super().__init__(label, init_data, extra, proxy, proxy_mgr, account_key)
        # Lazy import to avoid circular
        from mrg_api import MRGSession, extract_mrg_init_data
        # Clean init_data via extractor
        clean = extra.get("init_data_clean") if extra else None
        init = clean or extract_mrg_init_data(init_data) or init_data

        self._session = MRGSession(
            name=label,
            init_data=init,
            proxy=proxy,
            proxy_mgr=proxy_mgr,
            account_key=account_key,
            start_param=extra.get("start_param", "") if extra else "",
        )
        # Restore task state if provided
        if extra and extra.get("task_state"):
            self._session.task_state = extra["task_state"]

    async def login(self) -> Tuple[bool, str]:
        snap = await self._session.snapshot()
        if snap.get("ok"):
            return True, f"Verified | Bal {snap['user'].get('inAppBalance',0)}"
        return False, snap.get("detail") or snap.get("reason") or "Login failed"

    async def get_status(self) -> Dict[str, Any]:
        return await self._session.get_status()

    async def full_cycle(self, config: Dict[str, Any], step_cb: StepCB = None) -> Dict[str, Any]:
        # Merge MRG specific config
        mrg_cfg = {
            "mineThreshold": config.get("mrg_mine_threshold", 0.0001),
            "commissionThreshold": config.get("mrg_commission_threshold", 0),
            "autoClaimBonus": config.get("mrg_auto_claim_bonus", True),
            "taskFirstVisitDelaySec": config.get("mrg_task_first_delay", 15),
            "taskRevisitDelaySec": config.get("mrg_task_revisit_delay", 5),
            "taskClaimDelayMs": config.get("mrg_task_claim_delay", 2500),
            "joinRetryAfterH": config.get("mrg_join_retry_h", 24),
            "attemptAdsgram": config.get("mrg_attempt_adsgram", False),
            "autoUnlockLevels": config.get("mrg_auto_unlock", True),
            "maxAutoUnlockLevel": config.get("mrg_max_unlock_level", 1000),
            "skipTaskIds": config.get("mrg_skip_task_ids", []),
            "skipVerifyTypes": config.get("mrg_skip_verify_types", []),
        }
        # Merge with passed cfg
        merged = {**config, **mrg_cfg}
        return await self._session.full_cycle(merged, step_cb=step_cb)

    async def boost(self, rounds: int = 10, step_cb: StepCB = None) -> Tuple[int, int]:
        res = await self._session.flow_boost({}, step_cb=step_cb)
        unlocked = res.get("unlocked", [])
        return len(unlocked), 0

    @classmethod
    def extract_init_data(cls, raw: str) -> str:
        from mrg_api import extract_mrg_init_data
        return extract_mrg_init_data(raw) or raw.strip()

    @classmethod
    def detect(cls, text: str) -> bool:
        low = text.lower()
        return any(k in low for k in ["mrgtoken.xyz", "mrgminerbot", "mrg.up.railway.app", "app.mrgtoken"])
