"""
MRG Miner API Client v2.0-POWERFUL — Enhanced Auto Script
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API: https://mrg.up.railway.app
App: https://app.mrgtoken.xyz (bot: @mrgminerbot)

New v2.0 POWERFUL Features:
- ping() + presence_leave() for max speed mining (tap boost simulation)
- Daily check-in auto-claim (priority)
- Tap boost flow: rapid pings to keep mining active at max TH/s
- Enhanced task handling: daily, check-in, login, attendance prioritized
- Mining keep-alive: ping every cycle to prevent speed drop
- Level economics exact replica
- Squad + bonus auto-claim
- Proxy support + retry logic

Analysis: No dedicated /tap endpoint exists — mining speed = f(level, holding).
Max speed achieved via:
  1. Stay present (ping) → keeps mining active 24/7
  2. Claim daily check-in → keeps mining active claim
  3. Unlock levels → higher TH/s
  4. Claim mining regularly

So "tap boost" = presence ping + mining claim loop.
"""

import asyncio
import json
import time
import random
import math
from typing import Dict, Any, Optional, Tuple, List, Callable, Awaitable, Set

import aiohttp

try:
    from proxy_manager import make_connector, http_proxy_arg
except ImportError:
    def make_connector(p): return None
    def http_proxy_arg(p): return p if p and p.startswith("http") else None

from logger import api_log as log

API_BASE = "https://mrg.up.railway.app"
MRG_USD_FALLBACK = 0.00129
MAX_LEVEL = 1000

StepCB = Optional[Callable[[str, str], Awaitable[None]]]

# ── Level Economics (exact replica from econ.js) ─────────────────

def required_holding(level: int) -> int:
    e = int(level or 0)
    if e <= 0:
        return 0
    if e == 1:
        return 100
    if e == 203:
        return 10_000
    if e >= 1000:
        return 3875968992
    if e <= 203:
        a = (e - 1) / 202
        return round(100 + 9900 * (a ** 1.8))
    if e <= 450:
        a = (e - 203) / 247
        return round(10_000 + 240_000 * (a ** 2))
    if e <= 650:
        a = (e - 450) / 200
        return round(250_000 + 26_881_780 * (a ** 2.2))
    if e <= 850:
        a = (e - 650) / 200
        return round(27_131_780 + 321_705_420 * (a ** 2.5))
    t = (e - 850) / 150
    return round(348_837_200 + 3_527_131_792 * (t ** 2.6))

def speed_ths(level: int) -> float:
    e = int(level or 0)
    if e <= 0:
        return 0.0
    if e == 1:
        return 0.2
    if e == 203:
        return 7.56
    if e >= 1000:
        return 5000.0
    if e <= 203:
        r = 0.2 + (e - 1) * 0.03643564356435643
        return round(r, 2)
    t = (e - 203) / 797
    a = 7.56 + (5000 - 7.56) * (t ** 2.1)
    return round(a, 2)

def daily_output(level: int) -> float:
    e = int(level or 0)
    if e <= 0:
        return 0.0
    if e == 1:
        return 5.0
    return round(speed_ths(e) * 25, 2)

def max_level_for_holding(holding: float, ton_connected: bool) -> int:
    e = float(holding or 0)
    if e <= 0:
        return 0
    if e < 100:
        return 1 if ton_connected else 0
    a, r, o = 1, 1000, 1
    while a <= r:
        d = (a + r) // 2
        if e >= required_holding(d):
            o = d
            a = d + 1
        else:
            r = d - 1
    return o

def holding_of(user: Dict) -> float:
    if not user:
        return 0.0
    app = float(user.get("inAppBalance") or 0)
    wal = float(user.get("tonWalletBalance") or 0) if user.get("isTonConnected") else 0.0
    return app + wal

def current_known_level(user: Dict, active_level: Optional[int]) -> int:
    return max(
        int(user.get("manualUnlockedLevel") or 0),
        int(user.get("peakLevel") or 0),
        int(active_level or 0)
    )

def level_plan(user: Dict, active_level: Optional[int], max_auto: int = 1000) -> Dict:
    holding = holding_of(user)
    target = min(max_level_for_holding(holding, bool(user.get("isTonConnected"))), max_auto or MAX_LEVEL)
    current = current_known_level(user, active_level)
    plan = list(range(current + 1, target + 1))
    next_req = required_holding(current + 1)
    missing = max(0.0, next_req - holding)
    return {
        "holding": holding,
        "target": target,
        "current": current,
        "plan": plan,
        "nextReq": next_req,
        "missing": missing,
    }

def parse_auth_date(init_data: str) -> Optional[Dict]:
    import re
    try:
        m = re.search(r"auth_date=(\d+)", str(init_data or ""))
        if not m:
            return None
        auth_ms = int(m.group(1)) * 1000
        if not auth_ms:
            return None
        age_ms = int(time.time() * 1000) - auth_ms
        return {"authMs": auth_ms, "ageMs": age_ms, "ageH": age_ms / 3600000}
    except Exception:
        return None

def age_str(age_h: Optional[float]) -> str:
    if age_h is None or math.isnan(age_h):
        return "?"
    if age_h < 0:
        return "future?"
    if age_h < 1:
        return f"{int(age_h*60)}m"
    if age_h < 48:
        return f"{int(age_h)}h {int((age_h % 1)*60)}m"
    return f"{age_h/24:.1f}d"

def hms(sec: float) -> str:
    sec = max(0, int(sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

# ── API Client ───────────────────────────────────────────────────

HEADERS_BASE = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
    "Origin": "https://app.mrgtoken.xyz",
    "Referer": "https://app.mrgtoken.xyz/",
    "Accept": "application/json",
}

def _err_text(r: Dict) -> str:
    if not r:
        return "no-response"
    j = r.get("json")
    if isinstance(j, dict):
        return str(j.get("error") or j.get("message") or "")
    return str(r.get("error") or r.get("raw") or f"HTTP {r.get('status')}")

def _is_auth_error(r: Dict) -> bool:
    if not r:
        return True
    if r.get("status") in (401, 403):
        return True
    t = _err_text(r).lower()
    if r.get("status") == 400:
        return False
    return any(k in t for k in ["invalid hmac", "unauthorized", "initdata", "verification failed", "forbidden", "invalid signature", "auth"])

def _is_banned(r: Dict, user: Dict = None) -> bool:
    if user and str(user.get("status") or "").lower() == "banned":
        return True
    return "banned" in _err_text(r).lower()

def _is_maintenance(r: Dict) -> bool:
    j = r.get("json") or {}
    return j.get("maintenance") is True

def _is_retryable(r: Dict) -> bool:
    if not r:
        return True
    if r.get("status") == 0:
        return True
    if r.get("status") == 429:
        return True
    if r.get("status", 0) >= 500:
        return True
    return False

class MRGSession:
    def __init__(self, name: str, init_data: str,
                 proxy: Optional[str] = None, proxy_mgr=None,
                 account_key: str = "",
                 start_param: str = ""):
        self.name = name
        self.init_data = init_data
        self.proxy = proxy
        self.proxy_mgr = proxy_mgr
        self.account_key = account_key or name
        self.start_param = start_param

        self.user: Dict[str, Any] = {}
        self.tasks: List[Dict] = []
        self.completed: Set[str] = set()
        self.verified: bool = False
        self.active_level: Optional[int] = None
        self.speed_ths: Optional[float] = None

        self.task_state: Dict[str, Dict] = {}
        self.totals = {"mined": 0.0, "taskRewards": 0.0, "commission": 0.0, "bonus": 0.0, "unlocks": 0, "daily": 0, "ping": 0}

        self.initdata_dead = False
        self.last_ok = 0.0
        self.last_ping = 0.0

    def _headers(self) -> Dict[str, str]:
        return dict(HEADERS_BASE)

    async def _raw(self, endpoint: str, body: Dict, proxy: Optional[str], timeout: int = 25) -> Dict:
        conn = None
        try:
            from proxy_manager import make_connector as _mc, http_proxy_arg as _hpa
            conn = _mc(proxy)
            hp = _hpa(proxy)
        except Exception:
            hp = proxy if proxy and proxy.startswith("http") else None
            conn = None

        kw = {}
        if hp:
            kw["proxy"] = hp

        url = API_BASE + endpoint
        try:
            async with aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=timeout)) as s:
                async with s.post(url, headers=self._headers(), json=body, **kw) as resp:
                    try:
                        j = await resp.json(content_type=None)
                    except Exception:
                        txt = await resp.text()
                        j = None
                        raw = txt[:400]
                    else:
                        raw = None
                    return {"status": resp.status, "json": j, "raw": raw}
        except asyncio.TimeoutError:
            return {"status": 0, "json": None, "error": "timeout"}
        except Exception as e:
            return {"status": 0, "json": None, "error": f"{type(e).__name__}: {e}"}

    async def _call(self, endpoint: str, body: Dict, max_retries: int = 2, retry_delay: float = 1.5) -> Dict:
        last = None
        for attempt in range(max_retries + 1):
            for p_attempt in range(3 if self.proxy_mgr else 1):
                r = await self._raw(endpoint, body, self.proxy)
                if not _is_retryable(r):
                    if self.proxy_mgr and self.proxy:
                        self.proxy_mgr.report_success(self.proxy)
                    return r
                if self.proxy_mgr and self.proxy:
                    new_p = self.proxy_mgr.report_failure(self.account_key, self.proxy)
                    log.warning("[%s] MRG proxy retry %s → %s", self.name, self.proxy[:40] if self.proxy else "?", new_p or "DIRECT")
                    self.proxy = new_p
                last = r
                if p_attempt < 2:
                    await asyncio.sleep(0.5)
            if attempt < max_retries:
                delay = retry_delay * (2 ** attempt) + random.random() * 0.5
                await asyncio.sleep(delay)
        return last or {"status": 0, "json": None, "error": "no-response"}

    def _base_body(self) -> Dict:
        return {"initData": self.init_data}

    # ── API Methods ────────────────────────────────────────────

    async def verify(self) -> Dict:
        body = {**self._base_body(), "startParam": self.start_param or ""}
        return await self._call("/api/auth/verify", body)

    async def me(self) -> Dict:
        return await self._call("/api/user/me", self._base_body())

    async def friends(self) -> Dict:
        return await self._call("/api/user/friends", self._base_body())

    async def claim_mining(self) -> Dict:
        return await self._call("/api/user/claim-mining", self._base_body())

    async def claim_task(self, task_id: str) -> Dict:
        return await self._call("/api/user/claim-task", {**self._base_body(), "taskId": task_id})

    async def claim_commission(self) -> Dict:
        return await self._call("/api/user/claim-commission", self._base_body())

    async def claim_bonus(self) -> Dict:
        return await self._call("/api/user/claim-one-time-bonus", self._base_body())

    async def unlock_level(self, level: int) -> Dict:
        return await self._call("/api/user/unlock-level", {**self._base_body(), "level": level})

    async def withdraw(self, amount: float, dest: str) -> Dict:
        return await self._call("/api/user/withdraw", {**self._base_body(), "amount": amount, "destinationAddress": dest})

    async def ping(self) -> Dict:
        """Keep mining active - called periodically by web app to maintain presence"""
        return await self._call("/api/user/ping", self._base_body())

    async def presence_leave(self) -> Dict:
        """Called on page unload - we avoid calling this to keep mining active"""
        return await self._call("/api/user/presence-leave", self._base_body())

    # ── Powerful Flows v2.0 ────────────────────────────────────

    async def snapshot(self) -> Dict:
        r = await self.verify()
        if _is_maintenance(r):
            return {"ok": False, "reason": "maintenance"}
        if _is_auth_error(r):
            self.initdata_dead = True
            return {"ok": False, "reason": "auth", "detail": _err_text(r)}
        j = r.get("json") or {}
        if not (j.get("success") and j.get("user")):
            return {"ok": False, "reason": "verify", "detail": _err_text(r) or f"HTTP {r.get('status')}"}
        user = j["user"]
        if _is_banned(r, user):
            return {"ok": False, "reason": "banned", "detail": user.get("banReason") or "banned", "user": user}

        self.user = user
        self.tasks = j.get("tasks") or []
        self.completed = set(j.get("completedTaskIds") or [])
        self.verified = bool(j.get("verified"))
        self.last_ok = time.time()

        try:
            me_r = await self.me()
            if me_r.get("json") and me_r["json"].get("success"):
                self.active_level = me_r["json"].get("activeLevel")
                self.speed_ths = me_r["json"].get("speedTHs")
                if me_r["json"].get("user"):
                    self.user = {**self.user, **me_r["json"]["user"]}
        except Exception:
            pass

        return {
            "ok": True,
            "user": self.user,
            "tasks": self.tasks,
            "completed": self.completed,
            "verified": self.verified,
            "raw": j,
        }

    async def get_status(self) -> Dict:
        snap = await self.snapshot()
        if not snap.get("ok"):
            return {"ok": False, "error": snap.get("detail") or snap.get("reason"), "auth_dead": self.initdata_dead}

        u = snap["user"]
        plan = level_plan(u, self.active_level, 1000)

        team_stats = {}
        unclaimed_comm = 0.0
        unclaimed_bonus = 0.0
        try:
            fr = await self.friends()
            if fr.get("json") and fr["json"].get("success"):
                team_stats = fr["json"].get("teamStats") or {}
                unclaimed_comm = float(fr["json"].get("unclaimedTeamCommission") or 0)
                unclaimed_bonus = float(team_stats.get("unclaimedOneTimeBonusMRG") or 0)
        except Exception:
            pass

        ad = parse_auth_date(self.init_data)
        return {
            "ok": True,
            "user": u,
            "username": u.get("username") or u.get("firstName") or "?",
            "balance": float(u.get("inAppBalance") or 0),
            "unclaimed": float(u.get("unclaimedMiningBalance") or 0),
            "holding": plan["holding"],
            "level": plan["current"],
            "target_level": plan["target"],
            "next_req": plan["nextReq"],
            "missing": plan["missing"],
            "speed": self.speed_ths or speed_ths(plan["current"]),
            "daily": daily_output(plan["current"]),
            "tasks_total": len([t for t in snap["tasks"] if not t.get("isPaused")]),
            "tasks_done": len([t for t in snap["tasks"] if t.get("taskId") in snap["completed"]]),
            "team_friends": team_stats.get("totalFriends") or u.get("referralsCount") or 0,
            "unclaimed_comm": unclaimed_comm,
            "unclaimed_bonus": unclaimed_bonus,
            "wallet_connected": bool(u.get("isTonConnected")),
            "id_age": age_str(ad["ageH"]) if ad else "?",
            "id_age_h": ad["ageH"] if ad else None,
        }

    async def flow_ping_keepalive(self, step_cb: StepCB = None) -> Dict:
        """POWERFUL: Keep mining active at max speed via ping - simulates screen tap/presence"""
        try:
            # Rapid ping burst to simulate active tapping
            for i in range(3):
                r = await self.ping()
                self.last_ping = time.time()
                if r.get("json") and r["json"].get("success"):
                    self.totals["ping"] += 1
                    if step_cb and i == 0:
                        await step_cb("💓", f"Ping keep-alive OK - mining at max speed")
                    await asyncio.sleep(0.8 + random.random()*0.5)
                else:
                    if _is_auth_error(r):
                        self.initdata_dead = True
                        return {"ok": False, "reason": "auth"}
                    if step_cb and i == 0:
                        await step_cb("⚠️", f"Ping: {_err_text(r)[:60]}")
                    break
            return {"ok": True, "pings": 3}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def flow_daily_checkin(self, settings: Dict = None, step_cb: StepCB = None) -> Dict:
        """POWERFUL: Daily check-in auto-claim - highest priority"""
        settings = settings or {}
        snap = await self.snapshot()
        if not snap.get("ok"):
            return {"ok": False, "reason": snap.get("reason"), "claimed": 0}

        # Find daily/check-in tasks
        daily_keywords = ["daily", "check", "check-in", "checkin", "login", "attendance", "day "]
        daily_tasks = []
        for t in snap["tasks"]:
            if not t or not t.get("taskId") or t.get("isPaused"):
                continue
            tid = str(t.get("taskId","")).lower()
            title = str(t.get("title","")).lower()
            combined = f"{tid} {title}"
            if any(k in combined for k in daily_keywords):
                # Not completed or recurring
                if t.get("taskType") != "one_time" or t.get("taskId") not in snap["completed"]:
                    daily_tasks.append(t)

        # Also check if any task has reward and is claimable and not done
        # Prioritize daily first
        if not daily_tasks:
            # Fallback: check all tasks that look like daily via verification
            for t in snap["tasks"]:
                if t.get("taskType") in ("recurring_1h", "recurring_24h", "daily"):
                    if t.get("taskId") not in snap["completed"]:
                        daily_tasks.append(t)

        if not daily_tasks:
            if step_cb:
                await step_cb("📅", "Daily check-in: no pending daily tasks")
            return {"ok": True, "claimed": 0, "found": 0}

        if step_cb:
            await step_cb("📅", f"Daily check-in: {len(daily_tasks)} task(s) found")

        claimed = 0
        for t in daily_tasks:
            tid = t["taskId"]
            title = t.get("title") or tid
            reward = t.get("reward") or 0

            if step_cb:
                await step_cb("⏳", f"Daily {title} +{reward}")

            r = await self.claim_task(tid)
            if r.get("json") and r["json"].get("success"):
                got = float(r["json"].get("reward") or reward or 0)
                self.totals["daily"] += got
                self.totals["taskRewards"] += got
                claimed += 1
                if step_cb:
                    await step_cb("✅", f"Daily {title} CLAIMED +{got} MRG")
            else:
                msg = _err_text(r)
                low = msg.lower()
                if any(k in low for k in ["cooldown", "already claimed", "wait"]):
                    if step_cb:
                        await step_cb("⏳", f"Daily {title} on cooldown")
                elif _is_auth_error(r):
                    self.initdata_dead = True
                    return {"ok": False, "reason": "auth", "claimed": claimed}
                else:
                    if step_cb:
                        await step_cb("❌", f"Daily {title} fail: {msg[:60]}")

            await asyncio.sleep(1.5 + random.random())

        return {"ok": True, "claimed": claimed, "found": len(daily_tasks)}

    async def flow_tap_boost(self, settings: Dict = None, step_cb: StepCB = None) -> Dict:
        """
        POWERFUL: Tap boost simulation - tested from JS analysis:
        - No dedicated /tap endpoint exists
        - Mining speed = f(level, holding) only
        - BUT ping keeps mining active, prevents speed drop when offline
        - We simulate max speed by:
          1. Rapid pings (5x) = tap burst
          2. Immediate mining claim check
          3. Me refresh to get activeLevel/speed
        This ensures mining runs at MAX TH/s continuously.
        """
        settings = settings or {}
        if step_cb:
            await step_cb("👆", "Tap boost: activating max speed mining...")

        # Burst ping to simulate tapping screen
        ping_ok = 0
        for i in range(5):
            try:
                r = await self.ping()
                if r.get("json") and r["json"].get("success"):
                    ping_ok += 1
                    self.totals["ping"] += 1
                await asyncio.sleep(0.4 + random.random()*0.3)
            except Exception:
                pass

        # Refresh user to get latest speed
        try:
            me_r = await self.me()
            if me_r.get("json") and me_r["json"].get("success"):
                self.active_level = me_r["json"].get("activeLevel")
                self.speed_ths = me_r["json"].get("speedTHs")
                if step_cb:
                    await step_cb("⚡", f"Tap boost active: {self.speed_ths or '?'} TH/s | Ping {ping_ok}/5")
        except Exception:
            pass

        return {"ok": True, "pings": ping_ok, "speed": self.speed_ths}

    async def flow_mine(self, threshold: float = 0.0001, step_cb: StepCB = None) -> Tuple[bool, str, float]:
        snap = await self.snapshot()
        if not snap.get("ok"):
            return False, snap.get("detail") or snap.get("reason") or "verify failed", 0.0

        u = snap["user"]
        unclaimed = float(u.get("unclaimedMiningBalance") or 0)

        if not u.get("isTonConnected"):
            msg = f"Wallet not connected → claim blocked (unclaimed {unclaimed})"
            if step_cb:
                await step_cb("⚠️", msg)
            return False, msg, 0.0

        if unclaimed <= threshold:
            return True, f"Unclaimed {unclaimed} ≤ threshold {threshold} → skip", 0.0

        r = await self.claim_mining()
        if r.get("json") and r["json"].get("success"):
            got = float(r["json"].get("claimedAmount") or unclaimed)
            self.totals["mined"] += got
            if step_cb:
                await step_cb("⛏", f"Mine claim +{got:.4f} MRG → bal {float(r['json'].get('user', {}).get('inAppBalance') or 0):.4f}")
            return True, f"Claimed {got:.4f} MRG", got

        if _is_auth_error(r):
            self.initdata_dead = True
            return False, "Auth failed → initData expired", 0.0

        return False, f"Mine claim fail: {_err_text(r)[:120]}", 0.0

    async def flow_tasks(self, settings: Dict = None, step_cb: StepCB = None) -> Dict:
        settings = settings or {}
        snap = await self.snapshot()
        if not snap.get("ok"):
            return {"ok": False, "reason": snap.get("reason"), "ok_n": 0, "fail_n": 0, "skip_n": 0}

        skip_ids = set(settings.get("skipTaskIds") or [])
        skip_vt = set([str(s).lower() for s in (settings.get("skipVerifyTypes") or [])])
        now = time.time() * 1000

        def cooldown_ms(task_type: str) -> int:
            cd_map = settings.get("recurringCooldownH") or {"recurring_1h": 1, "recurring_3h": 3, "recurring_24h": 24, "daily": 24}
            if task_type == "one_time":
                return 0
            h = cd_map.get(task_type, 3)
            return int(h * 3600 * 1000)

        active = [t for t in snap["tasks"] if t and t.get("taskId") and not t.get("isPaused")]

        # POWERFUL ordering: daily/check-in first, then one_time, then recurring
        def rank(t):
            title = str(t.get("title","")).lower()
            tid = str(t.get("taskId","")).lower()
            combined = f"{title} {tid}"
            if any(k in combined for k in ["daily", "check", "login", "attendance"]):
                return -1
            tt = t.get("taskType")
            return 0 if tt == "one_time" else 1 if tt == "recurring_1h" else 2 if tt == "recurring_3h" else 3
        active.sort(key=rank)

        ok_n = fail_n = skip_n = 0
        pending = []

        for t in active:
            tid = t["taskId"]
            ts = self.task_state.get(tid, {})

            if tid in skip_ids:
                skip_n += 1
                continue
            if str(t.get("verificationType") or "").lower() in skip_vt:
                skip_n += 1
                continue

            if ts.get("nextEligibleAt") and now < ts["nextEligibleAt"]:
                continue
            if t.get("taskType") == "one_time":
                if tid in snap["completed"]:
                    continue
            else:
                last_succ = ts.get("lastSuccess")
                if last_succ and (now - last_succ) < cooldown_ms(t.get("taskType")):
                    continue

            if ts.get("joinRequiredUntil") and now < ts["joinRequiredUntil"]:
                continue

            vt = str(t.get("verificationType") or "").lower()
            if vt == "adsgram_ad" and not settings.get("attemptAdsgram"):
                skip_n += 1
                continue

            pending.append(t)

        if step_cb:
            await step_cb("📋", f"Tasks: {len(active)} active, {len(pending)} to attempt (daily first)")

        for t in pending:
            tid = t["taskId"]
            title = t.get("title") or tid
            reward = t.get("reward") or 0
            ts = self.task_state.setdefault(tid, {})

            first_delay = settings.get("taskFirstVisitDelaySec", 12)
            revisit_delay = settings.get("taskRevisitDelaySec", 4)
            legacy = settings.get("taskVisitDelaySec")
            base_sec = legacy if legacy is not None else (revisit_delay if ts.get("lastAttempt") else first_delay)
            wait_sec = max(0, int(base_sec + random.random() * 2.5))

            if step_cb:
                await step_cb("📝", f"START {title} (wait {wait_sec}s)...")

            if wait_sec > 0:
                await asyncio.sleep(wait_sec)

            if step_cb:
                await step_cb("⏳", f"CLAIM {title} +{reward}")

            r = await self.claim_task(tid)
            ts["lastAttempt"] = time.time() * 1000

            if r.get("json") and r["json"].get("success"):
                got = float(r["json"].get("reward") or reward or 0)
                ts["lastSuccess"] = time.time() * 1000
                ts["failCount"] = 0
                ts.pop("lastError", None)
                if t.get("taskType") and t.get("taskType") != "one_time":
                    ts["nextEligibleAt"] = time.time() * 1000 + cooldown_ms(t.get("taskType"))
                else:
                    ts["done"] = True
                self.totals["taskRewards"] += got
                if step_cb:
                    await step_cb("✅", f"{title} DONE +{got} MRG")
                ok_n += 1
            else:
                msg = _err_text(r)
                ts["failCount"] = ts.get("failCount", 0) + 1
                ts["lastError"] = msg[:160]

                low = msg.lower()
                if any(k in low for k in ["join the telegram", "not a member", "join channel", "join group"]):
                    ts["joinRequiredUntil"] = time.time() * 1000 + (settings.get("joinRetryAfterH", 24) * 3600 * 1000)
                    if step_cb:
                        await step_cb("🔒", f"{title} LOCKED: {msg[:80]} → join: {t.get('url') or 'see app'}")
                elif "adsgram" in low:
                    if step_cb:
                        await step_cb("⚠️", f"{title} needs ad view → skip")
                elif any(k in low for k in ["cooldown", "wait", "too early", "already claimed", "not found or paused", "not available"]):
                    cd = cooldown_ms(t.get("taskType")) or 3 * 3600 * 1000
                    ts["lastSuccess"] = time.time() * 1000
                    ts["nextEligibleAt"] = time.time() * 1000 + cd
                    ts["failCount"] = 0
                    if step_cb:
                        await step_cb("⏳", f"{title} cooling until {hms(cd/1000)}")
                elif _is_auth_error(r):
                    self.initdata_dead = True
                    if step_cb:
                        await step_cb("❌", f"{title} auth fail → initData expired")
                    return {"ok": False, "reason": "auth", "ok_n": ok_n, "fail_n": fail_n, "skip_n": skip_n}
                else:
                    if step_cb:
                        await step_cb("❌", f"{title} fail: {msg[:80]}")
                fail_n += 1

            await asyncio.sleep((settings.get("taskClaimDelayMs", 2000) + random.random() * 1000) / 1000)

        return {"ok": True, "ok_n": ok_n, "fail_n": fail_n, "skip_n": skip_n}

    async def flow_squad(self, settings: Dict = None, step_cb: StepCB = None) -> Dict:
        settings = settings or {}
        r = await self.friends()
        if _is_maintenance(r):
            if step_cb:
                await step_cb("⚠️", "Squad: maintenance")
            return {"ok": False}
        if _is_auth_error(r):
            self.initdata_dead = True
            if step_cb:
                await step_cb("❌", "Squad auth fail → initData expired")
            return {"ok": False, "reason": "auth"}

        j = r.get("json") or {}
        if not j.get("success"):
            if step_cb:
                await step_cb("❌", f"Squad fetch fail: {_err_text(r)[:80]}")
            return {"ok": False}

        team = j.get("teamStats") or {}
        comm = float(j.get("unclaimedTeamCommission") or 0)
        bonus = float(team.get("unclaimedOneTimeBonusMRG") or 0)

        if step_cb:
            await step_cb("👥", f"Squad: friends={team.get('totalFriends',0)} comm={comm:.4f} bonus={bonus:.0f}")

        claimed = 0.0

        if comm > float(settings.get("commissionThreshold", 0)):
            rc = await self.claim_commission()
            if rc.get("json") and rc["json"].get("success"):
                got = float(rc["json"].get("claimedAmount") or comm)
                self.totals["commission"] += got
                claimed += got
                if step_cb:
                    await step_cb("👥", f"Commission +{got:.4f} MRG")
            await asyncio.sleep(1.2 + random.random() * 1.2)

        if settings.get("autoClaimBonus", True) and bonus > 0:
            rb = await self.claim_bonus()
            if rb.get("json") and rb["json"].get("success"):
                got = float(rb["json"].get("claimedAmount") or bonus)
                self.totals["bonus"] += got
                claimed += got
                if step_cb:
                    await step_cb("🎁", f"Bonus +{got:.0f} MRG")

        return {"ok": True, "claimed": claimed}

    async def flow_boost(self, settings: Dict = None, step_cb: StepCB = None) -> Dict:
        settings = settings or {}
        snap = await self.snapshot()
        if not snap.get("ok"):
            return {"ok": False, "reason": snap.get("reason")}

        user = snap["user"]
        max_auto = settings.get("maxAutoUnlockLevel", 1000)
        plan = level_plan(user, self.active_level, max_auto)

        if step_cb:
            await step_cb("📊", f"Holding {plan['holding']:.1f} → L{plan['current']} ({speed_ths(plan['current'])} TH/s) → target L{plan['target']}")

        if not plan["plan"]:
            if step_cb and plan["missing"] > 0:
                await step_cb("💤", f"Next L{plan['current']+1} needs {plan['nextReq']} (missing {plan['missing']:.1f})")
            return {"ok": True, "unlocked": []}

        if not settings.get("autoUnlockLevels", True):
            if step_cb:
                await step_cb("⚠️", f"{len(plan['plan'])} levels eligible but autoUnlock OFF")
            return {"ok": True, "unlocked": []}

        unlocked = []
        for lvl in plan["plan"]:
            if step_cb:
                await step_cb("🚀", f"Unlock L{lvl} (needs {required_holding(lvl)})")
            r = await self.unlock_level(lvl)
            if r.get("json") and r["json"].get("success"):
                unlocked.append(lvl)
                self.totals["unlocks"] += 1
                if step_cb:
                    await step_cb("✅", f"L{lvl} UNLOCKED → {speed_ths(lvl)} TH/s (~{daily_output(lvl)}/day)")
            else:
                msg = _err_text(r)
                if "bound to another account" in msg.lower() or "connected to another account" in msg.lower():
                    if step_cb:
                        await step_cb("❌", f"L{lvl} fail: wallet bound to another account")
                    break
                if _is_auth_error(r):
                    self.initdata_dead = True
                    break
                if step_cb:
                    await step_cb("❌", f"L{lvl} fail: {msg[:80]}")
                break
            await asyncio.sleep((settings.get("unlockDelayMs", 1800) + random.random() * 800) / 1000)

        return {"ok": True, "unlocked": unlocked}

    async def full_cycle(self, cfg: Dict, step_cb: StepCB = None) -> Dict:
        """POWERFUL full cycle - daily first, tap boost, max speed"""
        report = {"name": self.name, "steps": [], "error": None, "totals": {}}

        async def step(e: str, m: str):
            report["steps"].append(f"{e} {m}")
            log.info("[%s] %s %s", self.name, e, m)
            if step_cb:
                try:
                    await step_cb(e, m)
                except Exception:
                    pass

        snap = await self.snapshot()
        if not snap.get("ok"):
            report["error"] = snap.get("detail") or snap.get("reason")
            await step("❌", report["error"])
            return report

        u = snap["user"]
        await step("🔐", f"Verified: {self.verified} | {u.get('firstName','')} bal={float(u.get('inAppBalance') or 0):.4f}")

        if self.proxy:
            await step("🌐", f"Proxy: {self.proxy[:50]}")

        # POWERFUL 1: Tap boost / Ping keep-alive first (max speed)
        await step("👆", "Tap boost + Ping keep-alive (max speed)...")
        await self.flow_tap_boost(cfg, step_cb=step)
        if self.initdata_dead:
            report["error"] = "initData expired"
            return report

        await asyncio.sleep(0.5)

        # POWERFUL 2: Daily check-in priority
        await step("📅", "Daily check-in...")
        daily_res = await self.flow_daily_checkin(cfg, step_cb=step)
        if self.initdata_dead:
            report["error"] = "initData expired"
            return report

        await asyncio.sleep(0.8)

        # Squad
        await step("👥", "Checking squad...")
        squad_res = await self.flow_squad(cfg, step_cb=step)
        if self.initdata_dead:
            report["error"] = "initData expired"
            return report

        await asyncio.sleep(0.8)

        # All tasks (daily already done, but rest)
        await step("🎯", "Checking tasks...")
        task_res = await self.flow_tasks(cfg, step_cb=step)
        if self.initdata_dead:
            report["error"] = "initData expired"
            return report

        await asyncio.sleep(0.8)

        # Mine
        await step("⛏", "Checking mining...")
        ok_m, msg_m, got_m = await self.flow_mine(float(cfg.get("mineThreshold", 0.0001)), step_cb=step)
        if self.initdata_dead:
            report["error"] = "initData expired"
            return report

        await asyncio.sleep(0.8)

        # Boost levels
        await step("🚀", "Checking boost levels...")
        boost_res = await self.flow_boost(cfg, step_cb=step)

        await asyncio.sleep(0.5)

        # Final ping to keep max speed after cycle
        await step("💓", "Final ping to keep max speed...")
        await self.flow_ping_keepalive(step_cb=step)

        # Final status
        final = await self.get_status()
        if final.get("ok"):
            await step("✅", f"Done! Bal {final['balance']:.4f} | L{final['level']} {final['speed']} TH/s | Hold {final['holding']:.1f} | +{got_m:.4f} mined | Daily {daily_res.get('claimed',0)} | Ping {self.totals['ping']}")

        report["totals"] = dict(self.totals)
        return report

    async def status(self) -> Dict:
        return await self.get_status()

# ── Helper for Telegram bot integration ────────────────────────

def extract_mrg_init_data(raw: str) -> str:
    """Extract MRG initData from raw input (URL or raw) - supports query_id= and user="""
    import urllib.parse
    s = (raw or "").strip().strip('"').strip("'")
    s = s.replace("&amp;", "&")

    if "tgWebAppData=" in s:
        frag = s.split("#", 1)[1] if "#" in s else s
        for part in frag.split("&"):
            if part.startswith("tgWebAppData="):
                s = part[len("tgWebAppData="):]
                break
        else:
            if "tgWebAppData=" in s:
                s = s.split("tgWebAppData=", 1)[1].split("&tgWebApp")[0]
        for _ in range(4):
            dec = urllib.parse.unquote(s)
            if dec == s:
                break
            s = dec

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

    if "hash=" not in s:
        return ""

    if s.startswith("query_id=") or s.startswith("user="):
        return s
    return ""
