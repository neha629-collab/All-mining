"""
Template for adding NEW mining bots — Copy this file!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Example: Let's say you want to add "Hamster Kombat" miner

Steps:
1. Copy this file to miners/hamster.py
2. Rename class to HamsterMiner
3. Change miner_id = "hamster"
4. Implement login(), get_status(), full_cycle()
5. In miners/registry.py, add: from .hamster import HamsterMiner (or use decorator)
6. Done! Bot will auto-detect and support it.

The bot's /add command can be extended to /hamster_add or generic /miner_add
"""

from typing import Dict, Any, Tuple, Optional
from .base import BaseMiner, StepCB

# Example using aiohttp
import aiohttp

# Use this decorator to auto-register
from .registry import register_miner

@register_miner
class TemplateMiner(BaseMiner):
    """
    Template miner — replace with your own logic
    """
    miner_id = "template"  # CHANGE THIS: must be unique, e.g., "hamster", "blum", "notcoin"
    display_name = "Template Miner"  # Display name in bot
    description = "Template for new miners — copy this file to create your own"

    def __init__(self, label: str, init_data: str, extra: Dict[str, Any] = None,
                 proxy: Optional[str] = None, proxy_mgr=None, account_key: str = ""):
        super().__init__(label, init_data, extra, proxy, proxy_mgr, account_key)
        self.api_base = "https://api.example.com"  # CHANGE: your miner API
        self.session_token = extra.get("session", "") if extra else ""

    # ── Required methods ───────────────────────────────────────

    async def login(self) -> Tuple[bool, str]:
        """
        Login to miner API
        Return (success, message)
        """
        try:
            # Example:
            # async with aiohttp.ClientSession() as s:
            #     async with s.post(f"{self.api_base}/auth", json={"initData": self.init_data}) as r:
            #         data = await r.json()
            #         if data.get("token"):
            #             self.session_token = data["token"]
            #             return True, "Logged in"
            #         return False, data.get("message", "Login failed")

            # For template, just simulate
            if len(self.init_data) < 20:
                return False, "Invalid initData"
            self.session_token = "fake_token_" + self.label
            return True, f"Logged in as {self.label}"

        except Exception as e:
            return False, f"Login error: {e}"

    async def get_status(self) -> Dict[str, Any]:
        """
        Get current mining status, balance, etc.
        Return dict with at least {"ok": True/False, ...}
        """
        try:
            # Example API call:
            # headers = {"Authorization": f"Bearer {self.session_token}"}
            # async with aiohttp.ClientSession(headers=headers) as s:
            #     async with s.get(f"{self.api_base}/status") as r:
            #         return await r.json()

            return {
                "ok": True,
                "balance": 123.45,
                "mining": True,
                "rate": "1.5/hr",
                "label": self.label,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def full_cycle(self, config: Dict[str, Any], step_cb: StepCB = None) -> Dict[str, Any]:
        """
        Full mining cycle: claim, start mining, tasks, etc.
        This is what /run and scheduler call.
        Return report dict
        """

        async def step(emoji: str, msg: str):
            if step_cb:
                try:
                    await step_cb(emoji, msg)
                except Exception:
                    pass

        report = {"name": self.label, "steps": [], "error": None}

        # 1. Login
        ok, msg = await self.login()
        if not ok:
            report["error"] = msg
            await step("❌", msg)
            return report
        await step("🔐", msg)

        # 2. Get status
        status = await self.get_status()
        await step("📊", f"Balance: {status.get('balance', 0)}")

        # 3. Your mining logic here
        # e.g., claim rewards, start mining, do tasks
        await step("⛏", "Mining cycle logic here...")
        # await self.claim()
        # await self.start_mining()

        # 4. Done
        await step("✅", "Cycle complete!")
        return report

    # ── Optional overrides ─────────────────────────────────────

    async def claim(self) -> Tuple[bool, str]:
        """Claim rewards"""
        return True, "Claimed 10 tokens"

    async def boost(self, rounds: int = 10, step_cb: StepCB = None) -> Tuple[int, int]:
        """Boost mining"""
        return rounds, 0

    @classmethod
    def extract_init_data(cls, raw: str) -> str:
        """
        Extract initData from raw user input.
        Override this if your miner has special format.
        """
        # Simple: return raw if it contains user= and hash=
        raw = raw.strip()
        if "user=" in raw and "hash=" in raw:
            return raw
        # If URL with tgWebAppData
        if "tgWebAppData=" in raw:
            import urllib.parse
            try:
                frag = raw.split("#", 1)[1] if "#" in raw else raw
                for part in frag.split("&"):
                    if part.startswith("tgWebAppData="):
                        return urllib.parse.unquote(part[len("tgWebAppData="):])
            except Exception:
                pass
        return raw

    @classmethod
    def detect(cls, text: str) -> bool:
        """
        Auto-detect if pasted text belongs to this miner.
        Return True if text looks like it belongs to this miner.
        """
        # Example: check domain
        # return "hamsterkombat.io" in text.lower()
        return "template" in text.lower()

# ── How to add tasks, boost, etc. ──────────────────────────────
# You can add any custom methods your miner needs.
# The bot.py will call full_cycle() for /run and scheduler.
# For custom commands, add handlers in bot.py like:
#
# async def cmd_template_add(...): ...
# async def cmd_template_status(...): ...
#
# And register them in main().
#
# For scheduler, create a new scheduler class in scheduler.py similar to
# MiningScheduler, or reuse GenericMinerScheduler (see below).
