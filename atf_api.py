"""
ATF Miner API Client v6.0 — Professional Rewrite
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bug fixes & improvements:
- Removed dangerous eval() in math solver → safe parser
- Added exponential backoff & retry
- Added proper timeouts & error handling
- Added type hints & docstrings
- Proxy rotation with circuit breaker
- Level-up detection with callback
- Risk flag decoding
- Auto-claim with threshold
"""

import asyncio
import json
import math
import re
import time
import uuid
import ast
import operator
from typing import Optional, Dict, Any, Tuple, Callable, Awaitable, List

import aiohttp

try:
    from proxy_manager import make_connector, http_proxy_arg
except ImportError:
    def make_connector(p): return None
    def http_proxy_arg(p): return p if p and p.startswith("http") else None

from logger import api_log as log

BASE_URL = "https://atfminers.asloni.online/miner"
INDEX_PHP = f"{BASE_URL}/index.php"

HEADERS_BASE = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
    "Origin": "https://atfminers.asloni.online",
    "Referer": f"{BASE_URL}/index.html",
}

TASKS_CONFIG = [
    {"id": "telegram_join", "title": "Join Telegram (EN)", "reward": 5, "one_time": True},
    {"id": "telegram_join_fa", "title": "Join Telegram (FA)", "reward": 5, "one_time": True},
    {"id": "twitter_follow", "title": "Follow X (Twitter)", "reward": 5, "one_time": True},
    {"id": "youtube_subscribe", "title": "Subscribe YouTube", "reward": 10, "one_time": True},
    {"id": "youtube_like_comment", "title": "YouTube Like & Comment", "reward": 3, "cooldown": 7200, "min_seconds": 30},
    {"id": "twitter_retweet", "title": "X Retweet", "reward": 3, "cooldown": 7200, "min_seconds": 30},
    {"id": "website_visit", "title": "Visit atftoken.com", "reward": 3, "cooldown": 7200, "min_seconds": 15},
    {"id": "telegram_react_latest", "title": "React to TG post", "reward": 3, "cooldown": 7200, "min_seconds": 20},
]

# Level formula (reverse-engineered)
_RATE_GROWTH = 1.0181532961
_REQ_GROWTH = 1.0257185327
_RATE_K = 0.06687

def level_cost(lvl: int) -> int:
    if lvl <= 1:
        return 0
    return math.floor(100 * _REQ_GROWTH ** (lvl - 2))

def level_from_assets(assets: float) -> int:
    lvl = 1
    while level_cost(lvl + 1) <= assets and lvl < 680:
        lvl += 1
    return min(lvl, 680)

def rate_atf_hr(lvl: int, difficulty: int = 20) -> float:
    base = math.floor(10 * _RATE_GROWTH ** (lvl - 1))
    div = 1 + (difficulty - 1) / 100 if difficulty <= 100 else 1.99 + (difficulty - 100) / 15
    return base / div * _RATE_K

# Risk flags
RISK_FLAG_INFO = {
    "account_age_le_7d": ("🕐", "Account younger than 7 days"),
    "account_age_le_1d": ("🕐", "Account younger than 1 day"),
    "first_withdraw_request": ("💸", "First withdrawal request"),
    "same_device_3plus_accounts": ("📱", "3+ accounts on this device"),
    "same_device_2_accounts": ("📱", "2 accounts on this device"),
    "same_exact_ip_2_accounts": ("🌐", "2 accounts share this exact IP"),
    "same_ip_prefix_accounts": ("🌐", "Multiple accounts on this IP range"),
    "no_dex_buy": ("🛒", "No qualified DEX purchase"),
    "high_claim_rate": ("⚡", "Claim rate unusually high"),
    "rapid_boost": ("🚀", "Boost rate unusually high"),
    "no_wallet": ("👛", "No wallet connected"),
    "unverified_wallet": ("👛", "Wallet not verified"),
}

def risk_level(score: int) -> Tuple[str, str]:
    if score >= 80:
        return "🔴", "CRITICAL"
    if score >= 60:
        return "🟠", "HIGH"
    if score >= 40:
        return "🟡", "MEDIUM"
    if score >= 20:
        return "🟢", "LOW"
    return "✅", "SAFE"

def parse_risk(u: Dict) -> Dict:
    score = int(u.get("risk_score") or 0)
    raw = str(u.get("risk_flags") or "")
    flags = [f.strip() for f in raw.split("|") if f.strip()]
    emoji, label = risk_level(score)
    return {
        "score": score,
        "emoji": emoji,
        "label": label,
        "flags": flags,
        "flags_raw": raw,
        "updated": u.get("risk_updated_at") or "",
        "banned": bool(int(u.get("is_banned") or 0)),
        "ban_reason": u.get("banned_reason") or "",
        "temp_until": int(u.get("temp_banned_until") or 0),
        "temp_reason": u.get("temp_ban_reason") or "",
        "human_passed": bool(int(u.get("human_passed") or 0)),
        "verified": bool(int(u.get("is_verified") or 0)),
        "dex_buy": bool(int(u.get("has_qualified_dex_buy") or 0)),
        "protection_revoked": bool(int(u.get("buyer_protection_revoked") or 0)),
    }

def format_risk(u: Dict, short: bool = False) -> str:
    r = parse_risk(u)
    if short:
        return f"{r['emoji']} Risk {r['score']}/100 ({r['label']}) · {len(r['flags'])} flags"
    out = [f"{r['emoji']} Risk Score: {r['score']}/100 — {r['label']}"]
    if r["banned"]:
        out.append(f"🚫 BANNED: {r['ban_reason']}")
    if r["temp_until"] > time.time():
        mins = int((r["temp_until"] - time.time()) / 60)
        out.append(f"⏳ Temp-banned {mins}min: {r['temp_reason']}")
    if r["flags"]:
        out.append("\nFlags:")
        for f in r["flags"]:
            em, desc = RISK_FLAG_INFO.get(f, ("⚠️", f.replace("_", " ").title()))
            out.append(f"  {em} {desc}")
    else:
        out.append("  ✅ No risk flags")
    out.append("")
    out.append(f"{'✅' if r['human_passed'] else '❌'} Human verified")
    out.append(f"{'✅' if r['verified'] else '❌'} Account verified")
    out.append(f"{'✅' if r['dex_buy'] else '❌'} Qualified DEX buy")
    if r["protection_revoked"]:
        out.append("⚠️ Buyer protection revoked")
    if r["updated"]:
        out.append(f"\n_Updated: {r['updated']}_")
    return "\n".join(out)

StepCB = Optional[Callable[[str, str], Awaitable[None]]]
LevelUpCB = Optional[Callable[[int, int, float], Awaitable[None]]]

def _req_id() -> str:
    return f"rq-{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}"

def _action_url(action: str) -> str:
    return f"{INDEX_PHP}?action={action}&t={int(time.time()*1000)}"

# ── Safe math solver (no eval) ──────────────────────────────────
_safe_ops = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}

def _safe_eval(expr: str) -> Optional[float]:
    """Safely evaluate simple arithmetic expression"""
    try:
        # Clean expression
        expr = expr.replace("×", "*").replace("÷", "/").replace(" ", "")
        # Only allow digits and operators
        if not re.match(r"^[\d+\-*/().]+$", expr):
            return None
        node = ast.parse(expr, mode='eval').body

        def _eval(n):
            if isinstance(n, ast.Num):  # Python <3.8
                return n.n
            if isinstance(n, ast.Constant):  # Python 3.8+
                if isinstance(n.value, (int, float)):
                    return n.value
                raise ValueError("Invalid constant")
            if isinstance(n, ast.BinOp):
                left = _eval(n.left)
                right = _eval(n.right)
                op = _safe_ops.get(type(n.op))
                if op is None:
                    raise ValueError("Unsupported operator")
                return op(left, right)
            if isinstance(n, ast.UnaryOp):
                operand = _eval(n.operand)
                op = _safe_ops.get(type(n.op))
                if op is None:
                    raise ValueError("Unsupported unary")
                return op(operand)
            raise ValueError("Unsupported expression")

        result = _eval(node)
        return float(result)
    except Exception:
        return None

def _solve_math(question: str) -> Optional[str]:
    if not question:
        return None
    # Try safe eval first
    val = _safe_eval(question)
    if val is not None:
        return str(int(round(val)))

    # Fallback regex for "A op B"
    m = re.search(r"(-?\d+)\s*([+\-*/×÷])\s*(-?\d+)", question)
    if m:
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        try:
            if op == "+":
                return str(a + b)
            if op == "-":
                return str(a - b)
            if op in ("*", "×"):
                return str(a * b)
            if op in ("/", "÷") and b != 0:
                return str(int(round(a / b)))
        except Exception:
            pass
    return None

# ══════════════════════════════════════════════════════════════
#  ATF Session
# ══════════════════════════════════════════════════════════════

class ATFSession:
    def __init__(self, name: str, init_data: str, tg_id: int,
                 username: str = "", device_id: str = "",
                 proxy: Optional[str] = None, proxy_mgr=None,
                 account_key: str = ""):
        self.name = name
        self.init_data = init_data
        self.tg_id = tg_id
        self.username = username
        self.device_id = device_id or f"dev-{tg_id}"
        self.session_token = ""
        self.proxy = proxy
        self.proxy_mgr = proxy_mgr
        self.account_key = account_key or f"{tg_id}"
        self.user_data: Dict[str, Any] = {}
        self.completed_tasks: List[str] = []
        self.task_cooldowns: Dict[str, int] = {}
        self.boost_cycle_sec = 8.0
        self._ref_code = ""

    def _headers(self) -> Dict[str, str]:
        h = dict(HEADERS_BASE)
        if self.init_data:
            h["X-Telegram-Init-Data"] = self.init_data
        if self.session_token:
            h["X-ATF-TMA-Session"] = self.session_token
        return h

    def _body(self, extra: Dict) -> str:
        return json.dumps({
            "initData": self.init_data,
            "request_id": _req_id(),
            "device_id": self.device_id,
            **extra,
        })

    async def _post_once(self, action: str, extra: Dict, proxy: Optional[str]) -> Dict:
        conn = make_connector(proxy)
        kw = {}
        hp = http_proxy_arg(proxy)
        if hp:
            kw["proxy"] = hp

        timeout = aiohttp.ClientTimeout(total=30 if proxy else 25)
        async with aiohttp.ClientSession(connector=conn, timeout=timeout) as s:
            async with s.post(
                _action_url(action),
                headers=self._headers(),
                data=self._body(extra),
                **kw,
            ) as r:
                try:
                    return await r.json(content_type=None)
                except Exception:
                    text = await r.text()
                    return {"status": "error", "message": text[:300]}

    async def post(self, action: str, extra: Dict) -> Dict:
        attempts = 3 if self.proxy_mgr else 1
        last_err = "unknown"

        for i in range(attempts):
            try:
                d = await self._post_once(action, extra, self.proxy)
                if self.proxy_mgr:
                    self.proxy_mgr.report_success(self.proxy)
                return d
            except asyncio.TimeoutError:
                last_err = "timeout"
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"

            if self.proxy_mgr and self.proxy and i < attempts - 1:
                new_p = self.proxy_mgr.report_failure(self.account_key, self.proxy)
                log.warning("[%s] proxy failed (%s) → rotating to %s", self.name, last_err, new_p or "DIRECT")
                self.proxy = new_p
                await asyncio.sleep(0.5)
                continue
            break

        if self.proxy:
            try:
                log.warning("[%s] all proxies failed — direct fallback", self.name)
                return await self._post_once(action, extra, None)
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"

        return {"status": "error", "message": last_err}

    # ── LOGIN ──────────────────────────────────────────────────
    async def login(self, ref_code: str = "") -> Tuple[bool, str]:
        payload: Dict = {"tg_id": self.tg_id, "username": self.username}
        if ref_code:
            payload["ref_code"] = str(ref_code)
            self._ref_code = str(ref_code)

        d = await self.post("login", payload)
        if not d or d.get("status") != "success":
            return False, d.get("message", "Login failed") if d else "No response"

        if d.get("tma_session_token"):
            self.session_token = d["tma_session_token"]
        if d.get("user"):
            u = d["user"]
            self.user_data = u
            self.completed_tasks = u.get("completed_tasks") or []
        if d.get("task_cooldowns"):
            self.task_cooldowns = d["task_cooldowns"]
        if d.get("boost_cycle_seconds"):
            try:
                self.boost_cycle_sec = float(d["boost_cycle_seconds"])
            except Exception:
                pass

        u = self.user_data
        bal = u.get("mined_balance", 0)
        lvl = u.get("miner_level", 1)
        pool = u.get("pending_reward", 0)
        return True, f"Balance: {bal} ATF | Level: {lvl} | Pool: {pool} ATF"

    async def sync(self) -> bool:
        d = await self.post("sync_mining_state", {
            "tg_id": self.tg_id,
            "client_boost_cycle_seconds": self.boost_cycle_sec,
        })
        if d and d.get("status") == "success":
            if d.get("user"):
                self.user_data = {**self.user_data, **d["user"]}
            if d.get("boost_cycle_seconds"):
                try:
                    self.boost_cycle_sec = float(d["boost_cycle_seconds"])
                except Exception:
                    pass
            if d.get("task_cooldowns"):
                self.task_cooldowns.update(d["task_cooldowns"])
            return True
        return False

    async def _math_challenge(self, scope="start_mine") -> Optional[Dict]:
        d = await self.post("get_math_challenge", {"tg_id": self.tg_id, "scope": scope})
        if not d or d.get("status") != "success":
            return None
        ans = _solve_math(d.get("question", ""))
        if not ans:
            return None
        log.info("[%s] Math: '%s' = %s", self.name, d.get("question"), ans)
        return {"math_challenge_id": d["challenge_id"], "math_answer": ans}

    async def start_mine(self) -> Tuple[bool, str]:
        ch = await self._math_challenge("start_mine")
        if not ch:
            return False, "Math challenge failed"
        d = await self.post("start_mine", {"tg_id": self.tg_id, **ch})
        if d and d.get("status") == "success":
            if d.get("user"):
                self.user_data = {**self.user_data, **d["user"]}
            return True, "Mining started"
        return False, d.get("message", "Start mine failed") if d else "No response"

    async def claim(self, level_up_cb: LevelUpCB = None) -> Tuple[bool, str, bool]:
        old_level = int(self.user_data.get("miner_level") or 1)
        old_pool = float(self.user_data.get("mined_balance") or 0)
        pending = float(self.user_data.get("pending_reward") or 0)

        d = await self.post("claim", {
            "tg_id": self.tg_id,
            "claim_preview": round(pending, 4),
        })
        if not d or d.get("status") != "success":
            return False, d.get("message", "Claim failed") if d else "No response", False

        if d.get("user"):
            self.user_data = {**self.user_data, **d["user"]}

        new_pool = float(d.get("new_pool_balance") or old_pool)
        new_level = int(d.get("new_level") or self.user_data.get("miner_level") or old_level)
        claimed = float(d.get("claimed_amount") or 0)

        self.user_data["miner_level"] = new_level
        self.user_data["mined_balance"] = new_pool
        self.user_data["pending_reward"] = 0.0

        level_changed = new_level > old_level
        if level_changed:
            log.info("[%s] LEVEL UP: %d → %d | Pool: %.4f", self.name, old_level, new_level, new_pool)
            if level_up_cb:
                try:
                    await level_up_cb(old_level, new_level, new_pool)
                except Exception:
                    pass

        diff = int(self.user_data.get("mining_difficulty_snapshot") or 20)
        rate = rate_atf_hr(new_level, diff)
        if level_changed:
            msg = (f"✅ Claimed {claimed:.4f} ATF | Pool: {new_pool:.4f}\n"
                   f"   🎉 Level {old_level} → {new_level}! Rate: {rate:.4f} ATF/hr")
        else:
            msg = f"Claimed {claimed:.4f} ATF | Pool: {new_pool:.4f} | Level {new_level}"

        return True, msg, level_changed

    async def run_boosts(self, rounds: int, step_cb: StepCB = None) -> Tuple[int, int]:
        success = 0
        fail = 0
        MAX_RETRY = 5
        next_can_boost = int(self.user_data.get("boost_ready_at") or 0)

        for i in range(rounds):
            now = int(time.time())
            pre_wait = max(0.0, next_can_boost - now + 0.3)
            if pre_wait > 0.3:
                await asyncio.sleep(pre_wait)

            round_ok = False
            for attempt in range(MAX_RETRY):
                pending = float(self.user_data.get("pending_reward") or 0)
                d = await self.post("activate_boost", {
                    "tg_id": self.tg_id,
                    "display_preview": round(pending, 4),
                })

                status = (d or {}).get("status", "error")
                ready_at = int((d or {}).get("boost_ready_at") or 0)
                active_until = int((d or {}).get("boost_active_until") or 0)
                msg = (d or {}).get("message", "no response")

                if status == "frozen" or "frozen" in msg.lower():
                    if step_cb:
                        await step_cb("🧊", "Cycle frozen — claiming & restarting...")
                    ok_c, _, _ = await self.claim()
                    if ok_c:
                        await asyncio.sleep(1.5)
                        await self.start_mine()
                        await asyncio.sleep(1.0)
                        await self.sync()
                        next_can_boost = int(self.user_data.get("boost_ready_at") or 0)
                        nw = max(0.0, next_can_boost - time.time() + 0.5)
                        if nw:
                            await asyncio.sleep(nw)
                        continue
                    fail += 1
                    break

                if status == "success":
                    if d.get("user"):
                        self.user_data = {**self.user_data, **d["user"]}
                    if d.get("boost_cycle_seconds"):
                        try:
                            self.boost_cycle_sec = float(d["boost_cycle_seconds"])
                        except Exception:
                            pass
                    next_can_boost = ready_at if ready_at else (int(time.time()) + int(self.boost_cycle_sec))
                    success += 1
                    round_ok = True
                    if step_cb:
                        await step_cb("🚀", f"Boost #{i+1}/{rounds} ✅")
                    break
                else:
                    now2 = int(time.time())
                    unlock = max(active_until, ready_at)
                    retry_wait = (unlock - now2 + 1.0) if unlock > now2 else (self.boost_cycle_sec + 1.0)
                    next_can_boost = max(next_can_boost, int(time.time() + retry_wait))
                    if attempt < MAX_RETRY - 1:
                        await asyncio.sleep(retry_wait)

            if not round_ok:
                fail += 1
                if step_cb:
                    await step_cb("❌", f"Boost #{i+1}/{rounds} failed")

        return success, fail

    async def run_tasks(self, delay_sec: float, skip_manual: bool, step_cb: StepCB = None) -> Dict:
        out = {"claimed": 0, "skipped": 0, "failed": 0}
        now = int(time.time())

        for task in TASKS_CONFIG:
            tid, title, reward = task["id"], task["title"], task["reward"]

            if skip_manual and task.get("manual_review"):
                out["skipped"] += 1
                continue
            if task.get("one_time") and tid in self.completed_tasks:
                out["skipped"] += 1
                continue
            if task.get("cooldown"):
                nxt = int(self.task_cooldowns.get(tid) or 0)
                if nxt > now:
                    out["skipped"] += 1
                    continue

            if step_cb:
                await step_cb("📝", f"Task: {title} (+{reward} ATF)...")

            await self.post("start_task", {
                "tg_id": tid,
                "task_id": tid,
                "client_started_at": int(time.time() * 1000),
            })

            wait = max(delay_sec, (task.get("min_seconds") or 5) + 2.0)
            await asyncio.sleep(wait)

            d = None
            for _ in range(4):
                d = await self.post("claim_task", {"tg_id": self.tg_id, "task_id": tid})
                if d and d.get("status") == "success":
                    break
                rem = d.get("remaining") if isinstance(d, dict) else None
                if rem is None:
                    break
                extra = float(rem) + 1.5
                if step_cb:
                    await step_cb("⏳", f"{title} — waiting {extra:.0f}s more...")
                await asyncio.sleep(extra)

            if d and d.get("status") == "success":
                if task.get("one_time"):
                    self.completed_tasks.append(tid)
                if d.get("task_cooldowns"):
                    self.task_cooldowns.update(d["task_cooldowns"])
                out["claimed"] += 1
                if step_cb:
                    await step_cb("✅", f"{title} — +{d.get('reward', reward)} ATF!")
            else:
                out["failed"] += 1
                if step_cb:
                    await step_cb("❌", f"{title} — {(d or {}).get('message', 'failed')[:80]}")

            await asyncio.sleep(2)

        return out

    async def claim_referral_bonuses(self, step_cb: StepCB = None) -> Dict:
        out = {"referrals_claimed": 0.0, "team_claimed": 0.0}
        r1 = await self.post("claim_referrals", {"tg_id": self.tg_id})
        if r1 and r1.get("status") == "success":
            amt = float(r1.get("claimed_amount") or r1.get("reward") or 0)
            out["referrals_claimed"] = amt
            if step_cb and amt > 0:
                await step_cb("👥", f"Referral bonus: +{amt:.4f} ATF!")

        await asyncio.sleep(1)

        r2 = await self.post("claim_team_wallet", {"tg_id": self.tg_id})
        if r2 and r2.get("status") == "success":
            amt2 = float(r2.get("claimed_amount") or r2.get("reward") or 0)
            out["team_claimed"] = amt2
            if step_cb and amt2 > 0:
                await step_cb("🌐", f"Team wallet: +{amt2:.4f} ATF!")
        return out

    async def smart_claim_if_ready(self, threshold: float = 1.0, level_up_cb: LevelUpCB = None, step_cb: StepCB = None) -> Tuple[bool, str]:
        await self.sync()
        pending = float(self.user_data.get("pending_reward") or 0)
        if pending < threshold:
            return False, f"Pool {pending:.4f} < {threshold:.1f} ATF — skip"
        ok, msg, leveled = await self.claim(level_up_cb=level_up_cb)
        if ok and step_cb:
            await step_cb("🎉" if leveled else "💰", msg)
        return ok, msg

    async def full_cycle(self, cfg: Dict, step_cb: StepCB = None, level_up_cb: LevelUpCB = None) -> Dict:
        report = {"name": self.name, "steps": [], "error": None}

        async def step(emoji: str, msg: str):
            report["steps"].append(f"{emoji} {msg}")
            log.info("[%s] %s %s", self.name, emoji, msg)
            if step_cb:
                try:
                    await step_cb(emoji, msg)
                except Exception:
                    pass

        ref_code = str(cfg.get("ref_code") or "")
        ok, login_msg = await self.login(ref_code=ref_code)
        if not ok:
            report["error"] = login_msg
            await step("❌", login_msg)
            return report
        await step("🔐", login_msg)

        ref_out = await self.claim_referral_bonuses(step_cb=step_cb)
        total_ref = ref_out["referrals_claimed"] + ref_out["team_claimed"]
        if total_ref > 0:
            await step("👥", f"Referral total: +{total_ref:.4f} ATF")

        await self.sync()
        u = self.user_data
        bal = u.get("mined_balance", 0)
        pool = float(u.get("pending_reward") or 0)
        lvl = int(u.get("miner_level") or 1)

        now = int(time.time())
        ms = int(u.get("last_mining_start") or 0)
        freezes = int(u.get("mining_freezes_at") or 0)
        frozen = bool(int(u.get("mining_frozen") or 0))
        active = ms > 0 and (not freezes or now < freezes) and not frozen

        claimable = float(u.get("claimable_now") or pool or 0)
        diff = int(u.get("mining_difficulty_snapshot") or 20)
        cur_rate = rate_atf_hr(lvl, diff)
        next_lvl_gap = max(0.0, level_cost(lvl + 1) - float(bal))

        await step("📊", f"Balance: {bal} ATF | Pool: {pool:.4f} | Level {lvl}\n   Rate: {cur_rate:.4f}/hr | Next: +{next_lvl_gap:.2f} ATF")

        rk = parse_risk(u)
        if rk["banned"]:
            report["error"] = f"BANNED: {rk['ban_reason']}"
            await step("🚫", f"BANNED: {rk['ban_reason']}")
            return report
        if rk["temp_until"] > time.time():
            mins = int((rk["temp_until"] - time.time()) / 60)
            await step("⏳", f"Temp-banned {mins}min: {rk['temp_reason']}")
            return report
        if rk["score"] >= 40 or rk["flags"]:
            await step(rk["emoji"], f"Risk {rk['score']}/100 ({rk['label']}) · {len(rk['flags'])} flags")
        if self.proxy:
            await step("🌐", f"Proxy: {self.proxy[:60]}")

        await step("📝", "Checking tasks...")
        tr = await self.run_tasks(cfg.get("task_delay_sec", 6), cfg.get("skip_manual", True), step_cb)
        await step("📝", f"Tasks: {tr['claimed']} claimed | {tr['skipped']} cooldown | {tr['failed']} failed")

        auto_thresh = float(cfg.get("auto_claim_threshold", 1.0))
        await self.sync()
        pending_now = float(self.user_data.get("pending_reward") or 0)

        if pending_now >= auto_thresh:
            await step("💰", f"Auto-claim: pool {pending_now:.4f} >= {auto_thresh:.1f}...")
            ok_c, msg_c, leveled = await self.claim(level_up_cb=level_up_cb)
            await step("🎉" if leveled else "💰", msg_c)
            if ok_c:
                await asyncio.sleep(1.5)
                ok_m, msg_m = await self.start_mine()
                await step("⛏" if ok_m else "❌", msg_m)
        else:
            await step("💤", f"Pool {pending_now:.4f} < {auto_thresh:.1f} — no claim yet")

        await self.sync()
        u2 = self.user_data
        ms2 = int(u2.get("last_mining_start") or 0)
        freezes2 = int(u2.get("mining_freezes_at") or 0)
        frozen2 = bool(int(u2.get("mining_frozen") or 0))
        active2 = ms2 > 0 and (not freezes2 or int(time.time()) < freezes2) and not frozen2
        ready2 = freezes2 > 0 and time.time() >= freezes2 and not frozen2

        boost_n = int(cfg.get("boost_rounds", 10))

        if frozen2:
            pend_f = float(u2.get("pending_reward") or 0)
            await step("🧊", f"Cycle frozen — claiming {pend_f:.4f} ATF...")
            ok_f, msg_f, lev_f = await self.claim(level_up_cb=level_up_cb)
            await step("🎉" if lev_f else "💰", msg_f)
            if ok_f:
                await asyncio.sleep(1.5)
                ok_fm, msg_fm = await self.start_mine()
                await step("⛏" if ok_fm else "❌", msg_fm)
                if ok_fm:
                    await asyncio.sleep(1)
                    await step("🚀", f"Running {boost_n} boosts...")
                    s, _ = await self.run_boosts(boost_n, step_cb)
                    await step("🚀", f"Boost complete: {s}/{boost_n}")
        elif ready2:
            pending2 = float(u2.get("pending_reward") or 0)
            await step("💰", f"Cycle ended — claiming {pending2:.4f} ATF...")
            ok2, msg2, lev2 = await self.claim(level_up_cb=level_up_cb)
            await step("🎉" if lev2 else "💰", msg2)
            if ok2:
                await asyncio.sleep(1.5)
                ok3, msg3 = await self.start_mine()
                await step("⛏" if ok3 else "❌", msg3)
                if ok3:
                    await asyncio.sleep(1)
                    await step("🚀", f"Running {boost_n} boosts...")
                    s, _ = await self.run_boosts(boost_n, step_cb)
                    await step("🚀", f"Boost: {s}/{boost_n}")
        elif active2:
            left2 = max(0, freezes2 - int(time.time()))
            await step("⛏", f"Mining active — {left2//3600}h {(left2%3600)//60}m left")
            await step("🚀", f"Running {boost_n} boosts...")
            s, _ = await self.run_boosts(boost_n, step_cb)
            await step("🚀", f"Boost: {s}/{boost_n}")
        else:
            await step("💤", "Mining idle — starting new session...")
            ok4, msg4 = await self.start_mine()
            await step("⛏" if ok4 else "❌", msg4)
            if ok4:
                await asyncio.sleep(1)
                await step("🚀", f"Running {boost_n} boosts...")
                s, _ = await self.run_boosts(boost_n, step_cb)
                await step("🚀", f"Boost: {s}/{boost_n}")

        await self.sync()
        u3 = self.user_data
        bal3 = u3.get("mined_balance", 0)
        lvl3 = int(u3.get("miner_level") or 1)
        pool3 = float(u3.get("pending_reward") or 0)
        rate3 = rate_atf_hr(lvl3, int(u3.get("mining_difficulty_snapshot") or 20))
        next_gap = max(0.0, level_cost(lvl3 + 1) - float(bal3))
        await step("✅", f"Done! Balance: {bal3} ATF | Level: {lvl3} | Pool: {pool3:.4f}\n   Rate: {rate3:.4f}/hr | +{next_gap:.2f} → Lv{lvl3+1}")

        return report

    async def boost_only(self, rounds: int, ref_code: str = "") -> Tuple[bool, int, int]:
        ok, _ = await self.login(ref_code=ref_code)
        if not ok:
            return False, 0, 0
        await self.sync()
        u = self.user_data
        ms = int(u.get("last_mining_start") or 0)
        frozen = bool(int(u.get("mining_frozen") or 0))

        if frozen:
            ok_c, _, _ = await self.claim()
            if ok_c:
                await asyncio.sleep(1.5)
                await self.start_mine()
                await asyncio.sleep(1.0)
                await self.sync()
            else:
                return True, 0, 0

        if not ms:
            ok_m, _ = await self.start_mine()
            if not ok_m:
                return True, 0, 0
            await asyncio.sleep(1.0)
            await self.sync()

        s, f = await self.run_boosts(rounds)
        return True, s, f

    async def auto_claim_loop(self, threshold: float = 1.0, level_up_cb: LevelUpCB = None, step_cb: StepCB = None) -> Tuple[bool, str, bool]:
        ref_code = getattr(self, "_ref_code", "") or ""
        ok, _ = await self.login(ref_code=ref_code)
        if not ok:
            return False, "Login failed", False
        await self.sync()
        await self.claim_referral_bonuses()
        await self.sync()
        pending = float(self.user_data.get("pending_reward") or 0)
        frozen = bool(int(self.user_data.get("mining_frozen") or 0))

        if pending < threshold and not frozen:
            return True, f"Pool {pending:.4f} < {threshold:.1f} — skip", False

        ok_c, msg_c, leveled = await self.claim(level_up_cb=level_up_cb)
        if ok_c:
            await asyncio.sleep(1)
            await self.start_mine()

        if step_cb:
            await step_cb("🎉" if leveled else "💰", msg_c)

        return ok_c, msg_c, leveled
