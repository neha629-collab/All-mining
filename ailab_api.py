"""
AI Lab Agent API Client v2.0 — Professional Rewrite
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Improvements:
- Robust initData extractor
- Safe retry on 401, 429, 5xx
- Keep-alive & session longevity
- Better error handling
- Proxy support
"""

import asyncio
import json
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

import aiohttp

try:
    from proxy_manager import make_connector, http_proxy_arg
except ImportError:
    def make_connector(p): return None
    def http_proxy_arg(p): return p if p and p.startswith("http") else None

from logger import api_log as log

API_BASE = "https://api.ailab-agent.online/api/v1"

HEADERS_BASE = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
    "Origin": "https://ailab-agent.online",
    "Referer": "https://ailab-agent.online/",
}

AUTH_ERRORS = {401}
BANNED_ERROR = 401001

StepCB = Optional[Callable[[str, str], Awaitable[None]]]

def hms(sec: float) -> str:
    sec = max(0, int(sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def extract_ailab_init_data(raw: str) -> str:
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
        for _ in range(3):
            if s.startswith("user="):
                break
            decoded = urllib.parse.unquote(s)
            if decoded == s:
                break
            s = decoded

    if not s.startswith("user=") and "user=" in s:
        s = s[s.index("user="):]

    return s if s.startswith("user=") else ""

class AILabSession:
    def __init__(self, name: str, init_data: str,
                 session_token: str = "",
                 proxy: Optional[str] = None, proxy_mgr=None,
                 account_key: str = "",
                 on_session_change: Optional[Callable[[str], None]] = None):
        self.name = name
        self.init_data = init_data
        self.session = session_token or ""
        self.proxy = proxy
        self.proxy_mgr = proxy_mgr
        self.account_key = account_key or name
        self.on_session_change = on_session_change

        self.user_info: Dict[str, Any] = {}
        self.miner: Dict[str, Any] = {}
        self.last_ok: float = 0.0
        self.login_count: int = 0
        self.initdata_dead: bool = False

    def _headers(self) -> Dict[str, str]:
        h = dict(HEADERS_BASE)
        if self.session:
            h["Authorization"] = f"Bearer {self.session}"
        return h

    async def _raw(self, method: str, path: str,
                   body: Optional[Dict] = None,
                   proxy: Optional[str] = None) -> Tuple[int, Dict]:
        conn = make_connector(proxy)
        kw: Dict[str, Any] = {}
        hp = http_proxy_arg(proxy)
        if hp:
            kw["proxy"] = hp
        data = json.dumps(body) if body is not None else None
        timeout = aiohttp.ClientTimeout(total=30 if proxy else 25)
        async with aiohttp.ClientSession(connector=conn, timeout=timeout) as s:
            async with s.request(
                method, API_BASE + path,
                headers=self._headers(), data=data,
                **kw,
            ) as r:
                try:
                    j = await r.json(content_type=None)
                except Exception:
                    j = {"_raw": (await r.text())[:300]}
                return r.status, (j or {})

    async def _http(self, method: str, path: str,
                    body: Optional[Dict] = None) -> Tuple[int, Dict]:
        attempts = 3 if self.proxy_mgr else 1
        last = "unknown"
        for i in range(attempts):
            try:
                st, j = await self._raw(method, path, body, self.proxy)
                if self.proxy_mgr:
                    self.proxy_mgr.report_success(self.proxy)
                return st, j
            except asyncio.TimeoutError:
                last = "timeout"
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
            if self.proxy_mgr and self.proxy and i < attempts - 1:
                new_p = self.proxy_mgr.report_failure(self.account_key, self.proxy)
                log.warning("[%s] proxy failed (%s) → %s", self.name, last, new_p or "DIRECT")
                self.proxy = new_p
                await asyncio.sleep(0.5)
        if self.proxy:
            try:
                return await self._raw(method, path, body, None)
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
        return 0, {"_error": last}

    @staticmethod
    def _err_code(j: Dict) -> int:
        ri = j.get("request_info") or {}
        try:
            return int(ri.get("error_code") or 0)
        except Exception:
            return 0

    @staticmethod
    def _err_msg(j: Dict) -> str:
        ri = j.get("request_info") or {}
        return str(ri.get("error_message") or j.get("_error") or "")[:200]

    async def login(self) -> Tuple[bool, str]:
        st, j = await self._http("POST", "/users/auth/login", {"user": self.init_data})
        res = j.get("result") or {}
        sess = res.get("session") or res.get("sessionId") or res.get("bearer")

        if not sess:
            code = self._err_code(j)
            msg = self._err_msg(j) or f"HTTP {st}"
            if code == BANNED_ERROR:
                self.initdata_dead = True
                return False, "Account BANNED by AI Lab"
            if st == 401 or code == 401:
                self.initdata_dead = True
                return False, f"initData expired — send new link ({msg})"
            return False, f"Login failed: {msg}"

        self.session = sess
        self.login_count += 1
        self.initdata_dead = False
        self.last_ok = time.time()
        if res.get("user"):
            self.user_info = res["user"]
        if self.on_session_change:
            try:
                self.on_session_change(sess)
            except Exception:
                pass
        log.info("[%s] session minted (#%d)", self.name, self.login_count)
        return True, "Logged in"

    async def api(self, method: str, path: str, body: Optional[Dict] = None) -> Dict:
        for attempt in range(2):
            if not self.session:
                ok, msg = await self.login()
                if not ok:
                    return {"_error": msg, "_auth_dead": self.initdata_dead}

            st, j = await self._http(method, path, body)
            code = self._err_code(j)

            if st in AUTH_ERRORS or code == 401:
                log.info("[%s] session expired → re-login", self.name)
                self.session = ""
                if attempt == 0:
                    continue
                return {"_error": "auth failed twice", "_auth_dead": self.initdata_dead}

            # Handle rate limit
            if st == 429:
                wait = int(j.get("retry_after") or 5)
                log.warning("[%s] rate limited, wait %ds", self.name, wait)
                await asyncio.sleep(wait)
                continue

            if j.get("user_info"):
                self.user_info = j["user_info"]
            self.last_ok = time.time()
            return j

        return {"_error": "unreachable"}

    async def keep_alive(self) -> bool:
        j = await self.api("GET", "/miner")
        return not j.get("_error")

    async def get_miner(self) -> Dict:
        j = await self.api("GET", "/miner")
        res = j.get("result") or {}
        self.miner = res.get("miner") or {}
        return j

    async def start_mining(self) -> Tuple[bool, str, int]:
        j = await self.api("POST", "/miner-start_mining", {"start_mining": True})
        if j.get("_error"):
            return False, j["_error"], 0
        res = j.get("result") or {}
        left = int(res.get("time_left") or 0)
        code = self._err_code(j)
        if left:
            return True, f"Mining started — {hms(left)} session", left
        if code == 228001:
            return True, "Mining already running", 0
        return False, self._err_msg(j) or "start failed", 0

    async def exchange_hashes(self, min_hashes: float) -> Tuple[bool, str, float]:
        hashes = float(self.miner.get("hashes_balance") or 0)
        if hashes < min_hashes:
            return False, f"{hashes:.3f} hashes < {min_hashes} threshold", 0.0
        j = await self.api("POST", "/miner-exchange_hashes", {"exchange": True})
        if j.get("_error"):
            return False, j["_error"], 0.0
        res = j.get("result") or {}
        amt = res.get("received_amount")
        if isinstance(amt, (int, float)):
            newb = float(res.get("new_balance") or 0)
            return True, f"{hashes:.3f} hashes → +${amt:.6f} (bal ${newb:.6f})", float(amt)
        return False, self._err_msg(j) or "exchange failed", 0.0

    async def run_tasks(self, step_cb: StepCB = None) -> Dict:
        out = {"claimed": 0, "pending": 0, "locked": 0, "reward": 0}
        j = await self.api("GET", "/tasks")
        if j.get("_error"):
            return out
        res = j.get("result") or {}

        for cat in ("referral", "follow", "other"):
            for t in (res.get(cat) or []):
                tid = t.get("id")
                if tid is None:
                    continue
                prog, fin = t.get("progress_current"), t.get("progress_finish")
                done = isinstance(prog, (int, float)) and isinstance(fin, (int, float)) and prog >= fin
                if cat == "referral" and not done:
                    out["locked"] += 1
                    continue

                r = await self.api("POST", "/task-check", {"task_id": tid, "action": "check"})
                rres = r.get("result") or {}
                code = self._err_code(r)

                if rres.get("error") or code in (400004, 400002):
                    out["pending"] += 1
                elif code == 400003:
                    out["locked"] += 1
                elif code == 0 and not r.get("_error"):
                    out["claimed"] += 1
                    out["reward"] += int(t.get("reward") or 0)
                    if step_cb:
                        await step_cb("🎯", f"Task #{tid} ({cat}) +{t.get('reward')} power")
                else:
                    out["pending"] += 1
                await asyncio.sleep(0.8)
        return out

    async def full_cycle(self, cfg: Dict, step_cb: StepCB = None) -> Dict:
        rep = {"name": self.name, "steps": [], "error": None, "time_left": 0}

        async def step(e: str, m: str):
            rep["steps"].append(f"{e} {m}")
            log.info("[%s] %s %s", self.name, e, m)
            if step_cb:
                try:
                    await step_cb(e, m)
                except Exception:
                    pass

        if not self.session:
            ok, msg = await self.login()
            if not ok:
                rep["error"] = msg
                await step("❌", msg)
                return rep

        j = await self.get_miner()
        if j.get("_error"):
            rep["error"] = j["_error"]
            await step("❌", j["_error"])
            return rep

        m = self.miner
        cm = m.get("current_miner") or {}
        u = self.user_info or {}
        balance = float(u.get("balance") or 0)
        hashes = float(m.get("hashes_balance") or 0)
        power = m.get("current_power") or 0
        running = bool(cm.get("is_running"))
        left = int(cm.get("time_left") or 0)

        await step("💰", f"Balance ${balance:.6f} | Power {power} | Hashes {hashes:.3f}\n   Mining: {'🟢 RUNNING (' + hms(left) + ' left)' if running else '🔴 STOPPED'}")
        if self.proxy:
            await step("🌐", f"Proxy: {self.proxy[:60]}")

        if not running and cfg.get("ailab_auto_start", True):
            await step("⛏", "Mining stopped — starting now...")
            ok_s, msg_s, new_left = await self.start_mining()
            await step("✅" if ok_s else "❌", msg_s)
            if new_left:
                left = new_left
        rep["time_left"] = left

        if cfg.get("ailab_auto_exchange", True):
            ok_e, msg_e, _ = await self.exchange_hashes(float(cfg.get("ailab_exchange_min", 0.5)))
            await step("💱" if ok_e else "💤", msg_e)

        if cfg.get("ailab_auto_tasks", True):
            tr = await self.run_tasks(step_cb)
            await step("📋", f"Tasks: {tr['claimed']} claimed (+{tr['reward']} power) | {tr['pending']} pending | {tr['locked']} locked")

        await self.get_miner()
        cm2 = (self.miner.get("current_miner") or {})
        u2 = self.user_info or {}
        left2 = int(cm2.get("time_left") or left)
        rep["time_left"] = left2
        await step("✅", f"Done! Balance ${float(u2.get('balance') or 0):.6f} | Power {self.miner.get('current_power') or 0} | Next restart in {hms(left2)}")
        return rep

    async def status(self) -> Dict:
        j = await self.get_miner()
        if j.get("_error"):
            return {"ok": False, "error": j["_error"], "auth_dead": self.initdata_dead}
        m = self.miner
        cm = m.get("current_miner") or {}
        u = self.user_info or {}
        return {
            "ok": True,
            "username": u.get("username") or "?",
            "user_id": u.get("user_id") or 0,
            "balance": float(u.get("balance") or 0),
            "power": m.get("current_power") or 0,
            "hashes": float(m.get("hashes_balance") or 0),
            "running": bool(cm.get("is_running")),
            "left": int(cm.get("time_left") or 0),
            "per_hour": m.get("profit_per_hour") or 0,
            "per_day": m.get("profit_per_day") or 0,
        }
