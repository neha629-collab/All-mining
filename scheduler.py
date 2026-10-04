"""
Professional Scheduler v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Unified SchedulerManager
- Jitter to avoid thundering herd
- Better error isolation
- Graceful shutdown
- Per-account watchdog for AI Lab (zero-downtime)

Bug fixes from v1:
- Fixed progress spam (now rate limited)
- Fixed task leaks
- Added jitter
- Added health checks
"""

import asyncio
import random
import time
from typing import Optional, Dict, List

from logger import sched_log as log

def _make_atf_session(acc_data: dict, cfg: dict, owner_id: int = 0):
    from atf_api import ATFSession
    mgr = cfg.get("proxy_mgr")
    key = f"{owner_id or acc_data.get('owner_id', 0)}:{acc_data['label']}"
    proxy = mgr.get_for(key) if mgr else None
    return ATFSession(
        name=acc_data["label"],
        init_data=acc_data["init_data"],
        tg_id=acc_data["tg_id"],
        username=acc_data.get("username", ""),
        device_id=acc_data.get("device_id", ""),
        proxy=proxy,
        proxy_mgr=mgr,
        account_key=key,
    )

class _Progress:
    """Live Telegram progress, rate limited"""
    MAX = 20

    def __init__(self, bot, chat_id: int, header: str):
        self.bot = bot
        self.chat_id = chat_id
        self.header = header
        self.lines: List[str] = []
        self._msg = None
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def start(self):
        try:
            self._msg = await self.bot.send_message(
                chat_id=self.chat_id,
                text=f"{self.header}\n\n⏳ Starting...",
                parse_mode="Markdown",
            )
        except Exception as e:
            log.warning("progress.start: %s", e)

    async def add(self, emoji: str, text: str):
        line = f"{emoji} {text}"
        async with self._lock:
            self.lines.append(line)
            body = "\n".join(self.lines[-self.MAX:])
            now = time.time()
            if now - self._last >= 1.5 and self._msg:
                try:
                    await self._msg.edit_text(
                        f"{self.header}\n\n{body}",
                        parse_mode="Markdown",
                    )
                    self._last = now
                except Exception:
                    pass

    async def finish(self, summary: str):
        async with self._lock:
            self.lines.append(f"\n{summary}")
            body = "\n".join(self.lines[-self.MAX:])
            if self._msg:
                try:
                    await self._msg.edit_text(
                        f"{self.header}\n\n{body}",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

# ══════════════════════════════════════════════════════════════
#  Mining Scheduler (ATF)
# ══════════════════════════════════════════════════════════════

class MiningScheduler:
    def __init__(self, app, cfg: dict):
        self.app = app
        self.cfg = cfg
        self._t: Optional[asyncio.Task] = None
        self._on = False

    def start(self):
        if self._on:
            return
        self._on = True
        self._t = asyncio.create_task(self._loop())
        log.info("MiningScheduler started — every %dmin", self.cfg["check_interval_min"])

    def stop(self):
        self._on = False
        if self._t:
            self._t.cancel()

    async def _loop(self):
        await asyncio.sleep(20 + random.uniform(0, 10))  # jitter
        while self._on:
            try:
                await self._run_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception("MiningScheduler error: %s", e)
            try:
                jitter = random.uniform(-60, 60)  # ±1 min jitter
                await asyncio.sleep(self.cfg["check_interval_min"] * 60 + jitter)
            except asyncio.CancelledError:
                break

    async def _run_all(self):
        from db import get_all_enabled
        accounts = get_all_enabled()
        if not accounts:
            return

        owners: Dict[int, List[Dict]] = {}
        for acc in accounts:
            owners.setdefault(acc["owner_id"], []).append(acc)

        tasks = []
        for owner_id, accs in owners.items():
            for acc_data in accs:
                tasks.append(self._run_one(owner_id, acc_data))

        await asyncio.gather(*tasks, return_exceptions=True)
        log.info("MiningScheduler: %d accounts processed", len(tasks))

    async def _run_one(self, owner_id: int, acc_data: dict):
        label = acc_data["label"]
        header = f"⛏ *{label}* — Auto Cycle\n{'─'*26}"
        progress = _Progress(self.app.bot, owner_id, header)
        await progress.start()
        try:
            sess = _make_atf_session(acc_data, self.cfg, owner_id)

            async def cb(e, m, _p=progress):
                await _p.add(e, m)

            async def level_up_cb(old_lvl, new_lvl, new_pool, _oid=owner_id, _lbl=label):
                from atf_api import rate_atf_hr, level_cost
                rate = rate_atf_hr(new_lvl)
                gap = max(0.0, level_cost(new_lvl + 1) - new_pool)
                try:
                    await self.app.bot.send_message(
                        chat_id=_oid,
                        text=(
                            f"🎉 *LEVEL UP!* [{_lbl}]\n"
                            f"   {old_lvl} → *{new_lvl}*\n"
                            f"   Pool: {new_pool:.4f} ATF\n"
                            f"   Rate: *{rate:.4f} ATF/hr* ({rate*24:.2f}/day)\n"
                            f"   Next: +{gap:.2f} ATF"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

            report = await sess.full_cycle(self.cfg, step_cb=cb, level_up_cb=level_up_cb)
            await progress.finish(
                f"❌ *Error:* `{report['error']}`" if report.get("error") else "✅ *Auto cycle complete!*"
            )
        except asyncio.CancelledError:
            await progress.finish("⛔ *Cancelled.*")
        except Exception as e:
            log.exception("MiningScheduler._run_one %s", label)
            await progress.finish(f"❌ `{e}`")

# ══════════════════════════════════════════════════════════════
#  Boost Scheduler
# ══════════════════════════════════════════════════════════════

class BoostScheduler:
    def __init__(self, app, cfg: dict):
        self.app = app
        self.cfg = cfg
        self._t: Optional[asyncio.Task] = None
        self._on = False

    def start(self):
        if self._on:
            return
        self._on = True
        self._t = asyncio.create_task(self._loop())
        log.info("BoostScheduler started — every %dmin x %d", self.cfg["boost_interval_min"], self.cfg["boost_rounds"])

    def stop(self):
        self._on = False
        if self._t:
            self._t.cancel()

    async def _loop(self):
        await asyncio.sleep(40 + random.uniform(0, 15))
        while self._on:
            try:
                await self._boost_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception("BoostScheduler error: %s", e)
            try:
                jitter = random.uniform(-30, 30)
                await asyncio.sleep(self.cfg["boost_interval_min"] * 60 + jitter)
            except asyncio.CancelledError:
                break

    async def _boost_all(self):
        from db import get_all_enabled
        accounts = get_all_enabled()
        if not accounts:
            return

        log.info("BoostScheduler: boosting %d account(s)", len(accounts))
        tasks = [self._boost_one(acc) for acc in accounts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok_n = sum(1 for r in results if r is True)
        log.info("BoostScheduler: %d/%d OK", ok_n, len(accounts))

    async def _boost_one(self, acc_data: dict) -> bool:
        try:
            sess = _make_atf_session(acc_data, self.cfg, acc_data.get("owner_id", 0))
            # v4.0 Force ATF refer
            ref = str(self.cfg.get("atf_ref_code") or self.cfg.get("ref_code") or "1692540458")
            login_ok, s, f = await sess.boost_only(self.cfg["boost_rounds"], ref_code=ref)
            if login_ok:
                log.info("[%s] Auto-boost: %d/%d (ref %s)", acc_data["label"], s, f, ref)
            return login_ok
        except Exception as e:
            log.warning("[%s] boost_one: %s", acc_data.get("label"), e)
            return False

# ══════════════════════════════════════════════════════════════
#  Claim Scheduler
# ══════════════════════════════════════════════════════════════

class ClaimScheduler:
    def __init__(self, app, cfg: dict):
        self.app = app
        self.cfg = cfg
        self._t: Optional[asyncio.Task] = None
        self._on = False

    def start(self):
        if self._on:
            return
        self._on = True
        self._t = asyncio.create_task(self._loop())
        log.info("ClaimScheduler started — every %dmin, threshold=%.1f", self.cfg["claim_check_min"], self.cfg["auto_claim_threshold"])

    def stop(self):
        self._on = False
        if self._t:
            self._t.cancel()

    async def _loop(self):
        await asyncio.sleep(60 + random.uniform(0, 20))
        while self._on:
            try:
                await self._claim_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception("ClaimScheduler error: %s", e)
            try:
                jitter = random.uniform(-20, 20)
                await asyncio.sleep(self.cfg["claim_check_min"] * 60 + jitter)
            except asyncio.CancelledError:
                break

    async def _claim_all(self):
        from db import get_all_enabled
        accounts = get_all_enabled()
        if not accounts:
            return

        log.info("ClaimScheduler: checking %d account(s)", len(accounts))
        owners: Dict[int, List[Dict]] = {}
        for acc in accounts:
            owners.setdefault(acc["owner_id"], []).append(acc)

        tasks = []
        for owner_id, accs in owners.items():
            for acc_data in accs:
                tasks.append(self._claim_one(owner_id, acc_data))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _claim_one(self, owner_id: int, acc_data: dict):
        label = acc_data["label"]
        try:
            sess = _make_atf_session(acc_data, self.cfg, owner_id)
            # v4.0 Force ATF refer
            sess._ref_code = str(self.cfg.get("atf_ref_code") or self.cfg.get("ref_code") or "1692540458")
            threshold = float(self.cfg["auto_claim_threshold"])

            async def level_up_cb(old_lvl, new_lvl, new_pool, _oid=owner_id, _lbl=label):
                from atf_api import rate_atf_hr, level_cost
                rate = rate_atf_hr(new_lvl)
                gap = max(0.0, level_cost(new_lvl + 1) - new_pool)
                try:
                    await self.app.bot.send_message(
                        chat_id=_oid,
                        text=(
                            f"🎉 *LEVEL UP!* [{_lbl}]\n"
                            f"   {old_lvl} → *{new_lvl}*\n"
                            f"   Pool: {new_pool:.2f} ATF\n"
                            f"   Rate: *{rate:.4f}/hr* ({rate*24:.2f}/day)\n"
                            f"   Next: +{gap:.2f} ATF"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

            ok, msg, leveled = await sess.auto_claim_loop(threshold=threshold, level_up_cb=level_up_cb)
            if ok and "skip" not in msg:
                log.info("[%s] ClaimScheduler: %s | leveled=%s", label, msg, leveled)

        except Exception as e:
            log.warning("[%s] claim_one error: %s", label, e)

# ══════════════════════════════════════════════════════════════
#  AI Lab Scheduler — zero-downtime watchdog
# ══════════════════════════════════════════════════════════════

class AILabScheduler:
    def __init__(self, app, cfg: dict):
        self.app = app
        self.cfg = cfg
        self._tasks: List[asyncio.Task] = []
        self._watch: Dict[str, asyncio.Task] = {}

    def _mk(self, acc: dict):
        from ailab_api import AILabSession
        import db

        owner = acc.get("owner_id", 0)
        label = acc["label"]
        key = f"ai:{owner}:{label}"
        mgr = self.cfg.get("proxy_mgr")

        def _persist(new_session: str):
            db.ai_update(owner, label, session=new_session, last_ok=time.time())

        return AILabSession(
            name=label,
            init_data=acc["init_data"],
            session_token=acc.get("session", ""),
            proxy=mgr.get_for(key) if mgr else None,
            proxy_mgr=mgr,
            account_key=key,
            on_session_change=_persist,
        )

    async def _notify(self, owner_id: int, text: str):
        try:
            await self.app.bot.send_message(owner_id, text, parse_mode="Markdown")
        except Exception:
            pass

    async def _dead_initdata(self, acc: dict, msg: str):
        import db
        owner, label = acc.get("owner_id", 0), acc["label"]
        db.ai_update(owner, label, dead=True)
        await self._notify(owner,
            f"🔑 *AI Lab — action needed* [{label}]\n\n"
            f"{msg}\n\n"
            f"Open @AiLab\\_robot, copy webapp URL and send:\n"
            f"`/ailab_add {label} <new URL>`\n\n"
            f"_Mining paused until then._")

    async def _watch_one(self, acc: dict):
        import db
        owner, label = acc.get("owner_id", 0), acc["label"]
        grace = int(self.cfg.get("ailab_restart_grace_sec", 30))

        while True:
            try:
                fresh = next((a for a in db.ai_get_accounts(owner) if a["label"] == label), None)
                if not fresh or not fresh.get("enabled", True):
                    return
                fresh["owner_id"] = owner

                sess = self._mk(fresh)
                rep = await sess.full_cycle(self.cfg)

                if sess.initdata_dead:
                    await self._dead_initdata(fresh, rep.get("error") or "Session could not be renewed")
                    return

                db.ai_update(owner, label, session=sess.session, last_ok=time.time(), dead=False)

                left = int(rep.get("time_left") or 0)
                if left > 0:
                    sleep_for = left + grace
                    log.info("[ailab:%s] next restart in %s", label, hms_(sleep_for))
                else:
                    sleep_for = int(self.cfg.get("ailab_check_min", 10)) * 60
                    log.info("[ailab:%s] no time_left — retry in %ds", label, sleep_for)

                await asyncio.sleep(sleep_for)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("[ailab:%s] watchdog error: %s", label, e)
                await asyncio.sleep(300)

    async def _watch_loop(self):
        import db
        while True:
            try:
                accs = db.ai_all_enabled()
                want = set()
                for a in accs:
                    if a.get("dead"):
                        continue
                    key = f"{a['owner_id']}:{a['label']}"
                    want.add(key)
                    t = self._watch.get(key)
                    if t is None or t.done():
                        self._watch[key] = asyncio.create_task(self._watch_one(a))
                        log.info("[ailab] watchdog started: %s", key)
                for key, t in list(self._watch.items()):
                    if key not in want:
                        t.cancel()
                        self._watch.pop(key, None)
                        log.info("[ailab] watchdog stopped: %s", key)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("[ailab] watch_loop: %s", e)
            await asyncio.sleep(60)

    async def _keepalive_loop(self):
        import db
        every = int(self.cfg.get("ailab_keepalive_min", 25)) * 60
        await asyncio.sleep(90 + random.uniform(0, 30))
        while True:
            try:
                accs = [a for a in db.ai_all_enabled() if not a.get("dead")]
                if accs:
                    async def ping(a):
                        try:
                            s = self._mk(a)
                            alive = await s.keep_alive()
                            if s.initdata_dead:
                                await self._dead_initdata(a, "initData no longer accepted")
                            elif alive:
                                db.ai_update(a["owner_id"], a["label"], session=s.session, last_ok=time.time())
                        except Exception as e:
                            log.debug("[ailab] keepalive %s: %s", a.get("label"), e)
                    await asyncio.gather(*[ping(a) for a in accs], return_exceptions=True)
                    log.info("[ailab] keep-alive pinged %d account(s)", len(accs))
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("[ailab] keepalive_loop: %s", e)
            await asyncio.sleep(every + random.uniform(-60, 60))

    async def _task_loop(self):
        import db
        every = int(self.cfg.get("ailab_task_min", 30)) * 60
        await asyncio.sleep(150 + random.uniform(0, 30))
        while True:
            try:
                accs = [a for a in db.ai_all_enabled() if not a.get("dead")]
                if accs:
                    async def sweep(a):
                        try:
                            s = self._mk(a)
                            await s.get_miner()
                            if self.cfg.get("ailab_auto_exchange", True):
                                await s.exchange_hashes(float(self.cfg.get("ailab_exchange_min", 0.5)))
                            if self.cfg.get("ailab_auto_tasks", True):
                                await s.run_tasks()
                            if s.initdata_dead:
                                await self._dead_initdata(a, "initData no longer accepted")
                            else:
                                db.ai_update(a["owner_id"], a["label"], session=s.session, last_ok=time.time())
                        except Exception as e:
                            log.debug("[ailab] sweep %s: %s", a.get("label"), e)
                    await asyncio.gather(*[sweep(a) for a in accs], return_exceptions=True)
                    log.info("[ailab] task sweep over %d account(s)", len(accs))
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("[ailab] task_loop: %s", e)
            await asyncio.sleep(every + random.uniform(-120, 120))

    def start(self):
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(self._watch_loop()),
            asyncio.create_task(self._keepalive_loop()),
            asyncio.create_task(self._task_loop()),
        ]
        log.info("AILabScheduler started (watchdog + keep-alive %dm + tasks %dm)",
                 self.cfg.get("ailab_keepalive_min", 25), self.cfg.get("ailab_task_min", 30))

    def stop(self):
        for t in self._tasks:
            t.cancel()
        for t in self._watch.values():
            t.cancel()
        self._tasks, self._watch = [], {}

def hms_(sec) -> str:
    sec = max(0, int(sec))
    h, r = divmod(sec, 3600)
    return f"{h:02d}:{r//60:02d}:{r%60:02d}"

# ══════════════════════════════════════════════════════════════
#  MRG Scheduler — mine + tasks + squad + boost
# ══════════════════════════════════════════════════════════════

def _make_mrg_session(acc_data: dict, cfg: dict, owner_id: int = 0):
    from mrg_api import MRGSession
    mgr = cfg.get("proxy_mgr")
    key = f"mrg:{owner_id or acc_data.get('owner_id', 0)}:{acc_data['label']}"
    proxy = mgr.get_for(key) if mgr else None
    # v4.0 Force MRG refer
    start_param = str(cfg.get("mrg_start_param") or cfg.get("mrg_ref_code") or cfg.get("ref_code") or "ref_XYDUB621")
    return MRGSession(
        name=acc_data["label"],
        init_data=acc_data["init_data"],
        proxy=proxy,
        proxy_mgr=mgr,
        account_key=key,
        start_param=start_param,
    )

class MRGScheduler:
    """Two loops: mine/squad/boost every 30min, tasks every 30min"""
    def __init__(self, app, cfg: dict):
        self.app = app
        self.cfg = cfg
        self._tasks: List[asyncio.Task] = []

    async def _notify(self, owner_id: int, text: str):
        try:
            await self.app.bot.send_message(owner_id, text, parse_mode="Markdown")
        except Exception:
            pass

    async def _run_mine_cycle(self):
        import db
        accounts = db.mrg_all_enabled()
        if not accounts:
            return
        log.info("MRG mine cycle: %d accounts", len(accounts))
        # Group by owner for parallel
        async def run_one(acc):
            try:
                sess = _make_mrg_session(acc, self.cfg, acc.get("owner_id", 0))
                # Use full cycle but with MRG config
                mrg_cfg = {
                    "mineThreshold": self.cfg.get("mrg_mine_threshold", 0.0001),
                    "commissionThreshold": self.cfg.get("mrg_commission_threshold", 0),
                    "autoClaimBonus": self.cfg.get("mrg_auto_claim_bonus", True),
                    "autoUnlockLevels": self.cfg.get("mrg_auto_unlock", True),
                    "maxAutoUnlockLevel": self.cfg.get("mrg_max_unlock_level", 1000),
                }
                # Squad + Mine + Boost
                await sess.flow_squad(mrg_cfg)
                await asyncio.sleep(1)
                await sess.flow_mine(mrg_cfg["mineThreshold"])
                await asyncio.sleep(1)
                await sess.flow_boost(mrg_cfg)

                if sess.initdata_dead:
                    db.mrg_update(acc["owner_id"], acc["label"], dead=True)
                    await self._notify(acc["owner_id"],
                        f"🔑 *MRG — action needed* [{acc['label']}]\n\n"
                        f"initData expired, send new link:\n`/mrg_add {acc['label']} <new URL>`")
            except Exception as e:
                log.warning("[mrg:%s] mine cycle error: %s", acc.get("label"), e)

        await asyncio.gather(*[run_one(a) for a in accounts], return_exceptions=True)

    async def _run_task_cycle(self):
        import db
        accounts = db.mrg_all_enabled()
        if not accounts:
            return
        log.info("MRG task cycle: %d accounts", len(accounts))

        async def run_one(acc):
            try:
                sess = _make_mrg_session(acc, self.cfg, acc.get("owner_id", 0))
                mrg_cfg = {
                    "taskFirstVisitDelaySec": self.cfg.get("mrg_task_first_delay", 15),
                    "taskRevisitDelaySec": self.cfg.get("mrg_task_revisit_delay", 5),
                    "taskClaimDelayMs": self.cfg.get("mrg_task_claim_delay", 2500),
                    "joinRetryAfterH": self.cfg.get("mrg_join_retry_h", 24),
                    "attemptAdsgram": self.cfg.get("mrg_attempt_adsgram", False),
                }
                await sess.flow_tasks(mrg_cfg)
                if sess.initdata_dead:
                    db.mrg_update(acc["owner_id"], acc["label"], dead=True)
            except Exception as e:
                log.warning("[mrg:%s] task cycle error: %s", acc.get("label"), e)

        await asyncio.gather(*[run_one(a) for a in accounts], return_exceptions=True)

    async def _mine_loop(self):
        await asyncio.sleep(50 + random.uniform(0, 20))
        interval = int(self.cfg.get("mrg_check_minutes", 30)) * 60
        while True:
            try:
                await self._run_mine_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception("MRG mine loop: %s", e)
            await asyncio.sleep(interval + random.uniform(-60, 60))

    async def _task_loop(self):
        await asyncio.sleep(80 + random.uniform(0, 20))
        interval = int(self.cfg.get("mrg_task_check_minutes", 30)) * 60
        while True:
            try:
                await self._run_task_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception("MRG task loop: %s", e)
            await asyncio.sleep(interval + random.uniform(-60, 60))

    def start(self):
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(self._mine_loop()),
            asyncio.create_task(self._task_loop()),
        ]
        log.info("MRGScheduler started (mine %dm + tasks %dm)",
                 self.cfg.get("mrg_check_minutes", 30),
                 self.cfg.get("mrg_task_check_minutes", 30))

    def stop(self):
        for t in self._tasks:
            t.cancel()
        self._tasks = []

# ══════════════════════════════════════════════════════════════
#  Scheduler Manager — unified control
# ══════════════════════════════════════════════════════════════

class SchedulerManager:
    def __init__(self, app, cfg: dict):
        self.app = app
        self.cfg = cfg
        self.mining = MiningScheduler(app, cfg)
        self.boost = BoostScheduler(app, cfg)
        self.claim = ClaimScheduler(app, cfg)
        self.ailab = AILabScheduler(app, cfg)
        self.mrg = MRGScheduler(app, cfg)

    def start_all(self):
        self.mining.start()
        self.boost.start()
        self.claim.start()
        if self.cfg.get("ailab_enabled", True):
            self.ailab.start()
        if self.cfg.get("mrg_enabled", True):
            self.mrg.start()
        log.info("All schedulers started (including MRG)")

    def stop_all(self):
        self.mining.stop()
        self.boost.stop()
        self.claim.stop()
        self.ailab.stop()
        self.mrg.stop()
        log.info("All schedulers stopped")
