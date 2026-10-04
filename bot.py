"""
Mining Bot v5.2-POWERFUL — Professional + Powerful MRG
- Clean professional UI, full English
- Daily check-in auto-claim priority
- Tap boost via ping keep-alive for max TH/s
- Language selector in settings (EN/BN)
- Force refer hidden from public, only admin sees
- MongoDB supported internally
"""

import asyncio
import os
import sys
import time
import re
from typing import Optional, List, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telegram.error import BadRequest
from telegram.constants import ParseMode

import config as cfg
import db
import force_join
from atf_api import ATFSession, rate_atf_hr, level_cost
from ailab_api import AILabSession, extract_ailab_init_data, hms as ai_hms
from mrg_api import MRGSession, extract_mrg_init_data, age_str as mrg_age_str, parse_auth_date as mrg_parse_date
from proxy_manager import ProxyManager
from scheduler import SchedulerManager
from logger import bot_log as log
from utils.extractors import extract_init_data, extract_tg_id, extract_username, detect_miner_type
from utils.formatters import fmt_mining_status
from miners.registry import auto_detect_miner, list_miners

RUN_CFG = {
    "boost_rounds": cfg.BOOST_ROUNDS,
    "boost_interval_min": cfg.BOOST_INTERVAL_MINUTES,
    "check_interval_min": cfg.CHECK_INTERVAL_MINUTES,
    "claim_check_min": cfg.CLAIM_CHECK_MINUTES,
    "auto_claim_threshold": cfg.AUTO_CLAIM_THRESHOLD,
    "task_delay_sec": cfg.TASK_DELAY_SEC,
    "delay_between_accs_sec": cfg.RUN_DELAY_BETWEEN_ACCOUNTS,
    "skip_manual": cfg.SKIP_MANUAL_TASKS,
    "ref_code": cfg.ATF_REF_CODE,
    "atf_ref_code": cfg.ATF_REF_CODE,
    "atf_ref_link": cfg.ATF_REF_LINK,
    "mrg_ref_code": cfg.MRG_REF_CODE,
    "mrg_ref_link": cfg.MRG_REF_LINK,
    "mrg_start_param": cfg.MRG_START_PARAM,
    "use_proxy": cfg.USE_PROXY,
    "proxy_refresh_hours": cfg.PROXY_REFRESH_HOURS,
    "proxy_min_healthy": cfg.PROXY_MIN_HEALTHY,
    "proxy_validate_max": cfg.PROXY_VALIDATE_MAX,
    "proxy_concurrency": cfg.PROXY_CONCURRENCY,
    "proxy_timeout_sec": cfg.PROXY_TIMEOUT_SEC,
    "proxy_sources_extra": cfg.PROXY_SOURCES_EXTRA,
    "ailab_auto_start": cfg.AILAB_AUTO_START,
    "ailab_auto_exchange": cfg.AILAB_AUTO_EXCHANGE,
    "ailab_auto_tasks": cfg.AILAB_AUTO_TASKS,
    "ailab_exchange_min": cfg.AILAB_EXCHANGE_MIN,
    "ailab_restart_grace_sec": cfg.AILAB_RESTART_GRACE_SEC,
    "ailab_keepalive_min": cfg.AILAB_KEEPALIVE_MIN,
    "ailab_task_min": cfg.AILAB_TASK_MIN,
    "ailab_check_min": cfg.AILAB_CHECK_MIN,
    "ailab_enabled": cfg.AILAB_ENABLED,
    "mrg_enabled": cfg.MRG_ENABLED,
    "mrg_api_base": cfg.MRG_API_BASE,
    "mrg_mine_threshold": cfg.MRG_MINE_THRESHOLD,
    "mrg_commission_threshold": cfg.MRG_COMMISSION_THRESHOLD,
    "mrg_auto_claim_bonus": cfg.MRG_AUTO_CLAIM_BONUS,
    "mrg_task_first_delay": cfg.MRG_TASK_FIRST_DELAY,
    "mrg_task_revisit_delay": cfg.MRG_TASK_REVISIT_DELAY,
    "mrg_task_claim_delay": cfg.MRG_TASK_CLAIM_DELAY,
    "mrg_join_retry_h": cfg.MRG_JOIN_RETRY_H,
    "mrg_attempt_adsgram": cfg.MRG_ATTEMPT_ADSGRAM,
    "mrg_auto_unlock": cfg.MRG_AUTO_UNLOCK,
    "mrg_max_unlock_level": cfg.MRG_MAX_UNLOCK_LEVEL,
    "mrg_check_minutes": cfg.MRG_CHECK_MINUTES,
    "mrg_task_check_minutes": cfg.MRG_TASK_CHECK_MINUTES,
    "mrg_initdata_warn_h": cfg.MRG_INITDATA_WARN_H,
    "mineThreshold": cfg.MRG_MINE_THRESHOLD,
    "commissionThreshold": cfg.MRG_COMMISSION_THRESHOLD,
    "autoClaimBonus": cfg.MRG_AUTO_CLAIM_BONUS,
    "taskFirstVisitDelaySec": cfg.MRG_TASK_FIRST_DELAY,
    "taskRevisitDelaySec": cfg.MRG_TASK_REVISIT_DELAY,
    "taskClaimDelayMs": cfg.MRG_TASK_CLAIM_DELAY,
    "joinRetryAfterH": cfg.MRG_JOIN_RETRY_H,
    "attemptAdsgram": cfg.MRG_ATTEMPT_ADSGRAM,
    "autoUnlockLevels": cfg.MRG_AUTO_UNLOCK,
    "maxAutoUnlockLevel": cfg.MRG_MAX_UNLOCK_LEVEL,
}

PROXY = ProxyManager(RUN_CFG, os.path.join(os.path.dirname(__file__), "data", "proxies.json"))
RUN_CFG["proxy_mgr"] = PROXY

_active_runs: Dict[int, asyncio.Task] = {}
_pending_add: Dict[int, Dict] = {}

# ── Translations v5.0 ──────────────────────────────────────────
T = {
    "en": {
        "welcome": "⛏ *Welcome to Auto Mining Bot v5.2*\n\nPowerful auto mining for ATF, AI Lab & MRG.\n\n*Features:*\n• Daily check-in auto-claim\n• Tap boost - max speed 24/7\n• Auto tasks + mining + squad\n• Level auto-unlock\n\n*How to start:*\n1. Open your mining bot and copy link\n2. Paste here - auto setup\n3. Mining runs automatically\n\n*Commands:*\n/list - Your accounts\n/status - Mining status\n/help - How to get link\n/settings - Preferences",
        "help": "📖 *How to get your mining link*\n\n*ATF Miner:*\n1. Open @ATF_AIRDROP_bot\n2. Tap *Start Mining*\n3. Copy URL (contains `user=` and `hash=`)\n4. Paste here\n\n*MRG Token:*\n1. Open @mrgminerbot\n2. Open app, wait 2-3 sec\n3. Copy URL (should have `chat_instance=`)\n4. Paste here immediately\n\n*AI Lab:*\n1. Open @AiLab_robot → Open app → Copy URL\n\n*Tips:*\n• Use fresh link (<1h old)\n• Avoid `query_id=` links - they expire fast\n• Bot auto claims daily check-in + tap boost\n\nNeed help? Contact {contact}",
        "list_empty": "📋 *No accounts yet*\n\nPaste your mining link to add your first account.\n\nExample: `https://...#tgWebAppData=user=...&hash=...`",
        "list_title": "📋 *Your Accounts* - {total}/{max_total}",
        "slots": "Slots: ATF {atf} | AI Lab {ai} | MRG {mrg}",
        "slot_full": "❌ *Limit Reached*\n\nYou already have {current}/{allowed} {miner} account(s).\nRemove the existing one before adding a new one.\n\nUse /list to manage.\n\nNeed more slots? Contact {contact}",
        "invalid_token": "❌ *Invalid Link*\n\nPlease send a full mining URL containing `user=` and `hash=`\n\nGet it from your mining app's browser.",
        "verifying": "⏳ Verifying your {miner} account...\n`{label}`",
        "atf_added": "✅ *ATF Account Added*\n\n👤 `{label}` | Level `{lvl}` | `{rate:.4f}/hr`\n💰 `{bal}` ATF | Pool `{pool}`\n\nMining will run automatically every 30 minutes.\nCheck status with /status",
        "ailab_added": "✅ *AI Lab Added*\n\n`{label}` - {username}\n💰 `${bal:.6f}` | Power `{power}`\n{run_txt}\n\nAuto-restart is active.",
        "mrg_added": "✅ *MRG Account Added*\n\n`{label}` - {username}\n💰 `{bal:.4f} MRG` | Unclaimed `{uncl:.4f}`\n🏆 Level {lvl} ({speed} TH/s)\n\n*Powerful features active:*\n📅 Daily check-in auto-claim\n👆 Tap boost (ping) for max speed\n⛏ Auto mining every 30m",
        "settings_title": "⚙️ *Settings*",
        "settings_body": "*Accounts:*\nATF: `{atf_n}/{atf_s}`\nAI Lab: `{ai_n}/{ai_s}`\nMRG: `{mrg_n}/{mrg_s}`\nTotal: `{total}/{max_total}`\n\n*MRG Powerful:*\n📅 Daily auto-claim: ON\n👆 Tap boost: ON (ping keep-alive)\n🚀 Max TH/s: Always\n\n*Language:* `{lang}`\n\n*Support:* {contact}",
        "lang_changed": "✅ Language changed to {lang}",
        "no_accounts_status": "No accounts found. Paste your mining link to start.",
        "fetching": "⏳ Fetching status...",
        "status_title": "📊 *Mining Status*",
        "export_title": "📦 *Backup* - ATF `{atf}` | AI Lab `{ai}` | MRG `{mrg}`",
        "auto_mode_hint": "💡 Just paste your mining link — no commands needed!\n\n/list to view accounts\n/status for status",
    },
    "bn": {
        "welcome": "⛏ *Auto Mining Bot v5.2 te Swagotom*\n\nPowerful auto mining - ATF, AI Lab & MRG.\n\n*Features:*\n• Daily check-in auto claim\n• Tap boost - max speed 24/7\n• Auto tasks + mining + level unlock\n\n*Kivabe shuru:*\n1. Mining bot theke link copy korun\n2. Ekhane paste korun\n3. Auto mining cholbe\n\n*Command:*\n/list - Account\n/status - Status\n/help - Link kivabe\n/settings - Settings",
        "help": "📖 *Mining link kivabe paben*\n\n*ATF Miner:*\n1. @ATF_AIRDROP_bot open korun\n2. Start Mining tap korun\n3. Browser theke URL copy korun\n\n*MRG Token:*\n1. @mrgminerbot open korun\n2. App open korun 2-3 sec wait korun\n3. URL copy korun (chat_instance thakbe)\n4. 1 hour er moddhe paste korun\n\n*Tips:*\n• Fresh link use korun\n• query_id link expire hoy fast\n• Bot daily check-in + tap boost auto korbe\n\nHelp lagle: {contact}",
        "list_empty": "📋 *Kono account nei*\n\nMining link paste korun first account add korte.",
        "list_title": "📋 *Apnar Accounts* - {total}/{max_total}",
        "slots": "Slot: ATF {atf} | AI Lab {ai} | MRG {mrg}",
        "slot_full": "❌ *Limit Ses*\n\nApnar {current}/{allowed} {miner} account ache.\nNotun add korar age puran ta remove korun.\n\n/list diye manage korun.\n\nBeshi slot lagle: {contact}",
        "invalid_token": "❌ *Invalid Link*\n\nFull URL din jekhane `user=` ebong `hash=` ache.",
        "verifying": "⏳ Apnar {miner} account verify hocche...\n`{label}`",
        "atf_added": "✅ *ATF Account Added*\n\n👤 `{label}` | Level `{lvl}` | `{rate:.4f}/hr`\n💰 `{bal}` ATF | Pool `{pool}`\n\nMining auto cholbe proti 30 min por por.\n/status diye check korun",
        "ailab_added": "✅ *AI Lab Added*\n\n`{label}` - {username}\n💰 `${bal:.6f}` | Power `{power}`\n{run_txt}\n\nAuto-restart active.",
        "mrg_added": "✅ *MRG Account Added*\n\n`{label}` - {username}\n💰 `{bal:.4f} MRG`\n\nMining auto cholbe.",
        "settings_title": "⚙️ *Settings*",
        "settings_body": "*Accounts:*\nATF: `{atf_n}/{atf_s}`\nAI Lab: `{ai_n}/{ai_s}`\nMRG: `{mrg_n}/{mrg_s}`\nTotal: `{total}/{max_total}`\n\n*Language:* `{lang}`\n\n*Support:* {contact}",
        "lang_changed": "✅ Language {lang} te change holo",
        "no_accounts_status": "Kono account pai ni. Link paste korun shuru korte.",
        "fetching": "⏳ Status anchi...",
        "status_title": "📊 *Mining Status*",
        "export_title": "📦 *Backup* - ATF `{atf}` | AI Lab `{ai}` | MRG `{mrg}`",
        "auto_mode_hint": "💡 Sudhu mining link paste korun — kono command lagbe na!\n\n/list - account dekhte\n/status - status dekhte",
    }
}

def tr(user_id: int, key: str, **kwargs) -> str:
    lang = db.get_user_lang(user_id) if user_id else cfg.DEFAULT_LANG
    if lang not in T:
        lang = "en"
    template = T[lang].get(key, T["en"].get(key, key))
    try:
        return template.format(**kwargs)
    except Exception:
        return template

def is_admin(uid: int) -> bool:
    return cfg.is_admin(uid)

async def guard(update: Update) -> bool:
    return await force_join.check_and_prompt(update, cfg)

async def safe_reply(update: Update, text: str, **kw):
    try:
        return await update.message.reply_text(text, **kw)
    except BadRequest as e:
        err = str(e).lower()
        if "can't parse" in err or "parse entities" in err:
            try:
                kw_no_md = {k: v for k, v in kw.items() if k != "parse_mode"}
                return await update.message.reply_text(text, **kw_no_md)
            except Exception:
                try:
                    return await update.message.reply_text(text[:4000])
                except Exception:
                    pass
        raise

async def safe_edit(msg: Message, text: str, **kw):
    try:
        await msg.edit_text(text, **kw)
    except BadRequest as e:
        err = str(e).lower()
        if "can't parse" in err or "parse entities" in err:
            try:
                kw_no_md = {k: v for k, v in kw.items() if k != "parse_mode"}
                await msg.edit_text(text, **kw_no_md)
                return
            except Exception:
                pass
        if "not modified" not in err:
            log.debug("safe_edit: %s", e)
    except Exception as e:
        log.debug("safe_edit: %s", e)

def make_atf_session(acc_data: dict, owner_id: int = 0) -> ATFSession:
    key = f"{owner_id or acc_data.get('owner_id', 0)}:{acc_data['label']}"
    return ATFSession(
        name=acc_data["label"],
        init_data=acc_data["init_data"],
        tg_id=acc_data["tg_id"],
        username=acc_data.get("username", ""),
        device_id=acc_data.get("device_id", ""),
        proxy=PROXY.get_for(key),
        proxy_mgr=PROXY,
        account_key=key,
    )

def make_ailab_session(acc: dict, owner_id: int) -> AILabSession:
    key = f"ai:{owner_id}:{acc['label']}"
    def _persist(new_session: str):
        db.ai_update(owner_id, acc["label"], session=new_session, last_ok=time.time())
    return AILabSession(
        name=acc["label"],
        init_data=acc["init_data"],
        session_token=acc.get("session", ""),
        proxy=PROXY.get_for(key),
        proxy_mgr=PROXY,
        account_key=key,
        on_session_change=_persist,
    )

def make_mrg_session(acc: dict, owner_id: int) -> MRGSession:
    key = f"mrg:{owner_id or acc.get('owner_id', 0)}:{acc['label']}"
    start_param = RUN_CFG.get("mrg_start_param") or RUN_CFG.get("mrg_ref_code") or "ref_XYDUB621"
    return MRGSession(
        name=acc["label"],
        init_data=acc["init_data"],
        proxy=PROXY.get_for(key),
        proxy_mgr=PROXY,
        account_key=key,
        start_param=start_param,
    )

def main_menu_kb(is_admin_user: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        ["📋 My Accounts", "📊 Status"],
        ["❓ Help", "⚙️ Settings"],
    ]
    if is_admin_user:
        buttons.append(["👑 Admin Panel"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def auto_label(miner_id: str, init_data: str, owner_first: str = "") -> str:
    try:
        uname = extract_username(init_data)
        if uname and len(uname) >= 2:
            safe = re.sub(r'[^a-zA-Z0-9_-]', '', uname)[:12]
            if safe:
                return f"{safe}_{miner_id}"
    except Exception:
        pass
    if owner_first:
        safe_first = re.sub(r'[^a-zA-Z0-9]', '', owner_first)[:10]
        if safe_first:
            return f"{safe_first}_{miner_id}"
    return miner_id

class LiveProgress:
    MAX = 18
    def __init__(self, bot, chat_id: int, header: str):
        self.bot = bot
        self.chat_id = chat_id
        self.header = header
        self.lines: List[str] = []
        self._msg: Optional[Message] = None
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def start(self):
        self._msg = await self.bot.send_message(
            chat_id=self.chat_id,
            text=f"{self.header}\n\n⏳ Starting...",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def add(self, emoji: str, text: str):
        line = f"{emoji} {text}"
        async with self._lock:
            self.lines.append(line)
            body = "\n".join(self.lines[-self.MAX:])
            now = time.time()
            if now - self._last >= 1.5 and self._msg:
                try:
                    await self._msg.edit_text(f"{self.header}\n\n{body}", parse_mode=ParseMode.MARKDOWN)
                    self._last = now
                except Exception:
                    pass

    async def finish(self, summary: str):
        async with self._lock:
            self.lines.append(f"\n{summary}")
            body = "\n".join(self.lines[-self.MAX:])
            if self._msg:
                try:
                    await self._msg.edit_text(f"{self.header}\n\n{body}", parse_mode=ParseMode.MARKDOWN)
                except Exception:
                    try:
                        await self._msg.edit_text(f"{self.header}\n\n{body}")
                    except Exception:
                        pass

async def auto_add_flow(update: Update, raw_text: str, forced_miner: str = None):
    uid = update.effective_user.id
    first_name = update.effective_user.first_name or ""

    if not await guard(update):
        return

    raw_text = raw_text.strip()
    if len(raw_text) < 20:
        return

    detected = forced_miner or auto_detect_miner(raw_text) or detect_miner_type(raw_text)
    low = raw_text.lower()
    if not detected:
        if any(k in low for k in ["mrgtoken.xyz", "mrgminerbot", "mrg.up.railway.app"]):
            detected = "mrg"
        elif "ailab-agent.online" in low:
            detected = "ailab"
        elif "atfminers.asloni.online" in low:
            detected = "atf"
        elif "user=" in low and "hash=" in low:
            _pending_add[uid] = {"raw": raw_text, "time": time.time()}
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⛏ ATF Miner", callback_data="addsel:atf"),
                 InlineKeyboardButton("🧪 AI Lab", callback_data="addsel:ailab")],
                [InlineKeyboardButton("💎 MRG Token", callback_data="addsel:mrg")],
            ])
            await safe_reply(update,
                "🔍 *Select Platform*\n\nCould not auto-detect. Please choose:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb
            )
            return

    if not detected:
        return

    miner_id = detected.lower()

    if miner_id == "atf":
        clean = extract_init_data(raw_text)
    elif miner_id == "ailab":
        clean = extract_ailab_init_data(raw_text)
    elif miner_id == "mrg":
        clean = extract_mrg_init_data(raw_text)
    else:
        clean = extract_init_data(raw_text) or extract_ailab_init_data(raw_text) or extract_mrg_init_data(raw_text) or raw_text.strip()

    if not clean or len(clean) < 30 or "user=" not in clean or "hash=" not in clean:
        await safe_reply(update, tr(uid, "invalid_token"), parse_mode=ParseMode.MARKDOWN)
        return

    can_add, reason, current, allowed = db.can_add_account(uid, miner_id)
    if not can_add:
        miner_display = {"atf": "ATF", "ailab": "AI Lab", "mrg": "MRG"}.get(miner_id, miner_id.upper())
        await safe_reply(update,
            tr(uid, "slot_full", current=current, allowed=allowed, miner=miner_display, contact=cfg.ADMIN_CONTACT),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    label = auto_label(miner_id, clean, first_name)
    label = re.sub(r'[^a-zA-Z0-9_-]', '_', label)[:20]
    if len(label) < 2:
        label = miner_id

    msg = await safe_reply(update, tr(uid, "verifying", miner=miner_id.upper(), label=label), parse_mode=ParseMode.MARKDOWN)

    try:
        if miner_id == "atf":
            tg_id = extract_tg_id(clean)
            username = extract_username(clean)
            sess = ATFSession(name=label, init_data=clean, tg_id=tg_id, username=username,
                              proxy=PROXY.get_for(f"{uid}:{label}"), proxy_mgr=PROXY, account_key=f"{uid}:{label}")
            ok, summary = await sess.login(ref_code=RUN_CFG.get("atf_ref_code","1692540458"))
            if not ok:
                await safe_edit(msg, f"❌ *ATF Login Failed:*\n`{summary}`", parse_mode=ParseMode.MARKDOWN)
                return
            db.add_account(uid, label, clean, tg_id, username)
            u = sess.user_data
            lvl = int(u.get("miner_level") or 1)
            bal = u.get("mined_balance", 0)
            pool = u.get("pending_reward", 0)
            r = rate_atf_hr(lvl)
            await safe_edit(msg, tr(uid, "atf_added", label=label, lvl=lvl, rate=r, bal=bal, pool=pool), parse_mode=ParseMode.MARKDOWN)
            if cfg.AUTO_RUN_ON_ADD:
                asyncio.create_task(_run_single_atf(update, label))

        elif miner_id == "ailab":
            sess = AILabSession(name=label, init_data=clean,
                                proxy=PROXY.get_for(f"ai:{uid}:{label}"), proxy_mgr=PROXY, account_key=f"ai:{uid}:{label}")
            ok, login_msg = await sess.login()
            if not ok:
                await safe_edit(msg, f"❌ AI Lab login failed: {login_msg}", parse_mode=ParseMode.MARKDOWN)
                return
            st = await sess.status()
            db.ai_add_account(uid, label, clean, sess.session)
            db.ai_update(uid, label, last_ok=time.time())
            if st.get("ok"):
                run_txt = f"🟢 Running ({ai_hms(st['left'])} left)" if st["running"] else "🔴 Stopped - will auto-restart"
                await safe_edit(msg, tr(uid, "ailab_added", label=label, username=st['username'], bal=st['balance'], power=st['power'], run_txt=run_txt), parse_mode=ParseMode.MARKDOWN)
            else:
                await safe_edit(msg, f"✅ *{label}* added", parse_mode=ParseMode.MARKDOWN)
            if cfg.AUTO_RUN_ON_ADD:
                asyncio.create_task(_run_single_ailab(update, label))

        elif miner_id == "mrg":
            sess = MRGSession(name=label, init_data=clean,
                              proxy=PROXY.get_for(f"mrg:{uid}:{label}"), proxy_mgr=PROXY, account_key=f"mrg:{uid}:{label}",
                              start_param=RUN_CFG.get("mrg_start_param","ref_XYDUB621"))
            snap = await sess.snapshot()
            if not snap.get("ok"):
                err_detail = snap.get('detail') or snap.get('reason') or "unknown"
                err_low = str(err_detail).lower()
                # Helpful hint for query_id / old link
                if "invalid hmac" in err_low or "invalid signature" in err_low or "hmac" in err_low:
                    if "query_id=" in clean:
                        hint = (
                            "\n\n💡 *Tip:* This link uses `query_id=` which expires fast (single-use).\n"
                            "Please get a fresh link:\n"
                            "1. Open @mrgminerbot → Open App\n"
                            "2. Wait 2-3 sec\n"
                            "3. Copy URL again - it should contain `chat_instance=` not `query_id=`\n"
                            "4. Paste here immediately (within 1 hour)"
                        )
                        await safe_edit(msg, f"❌ MRG login failed: {err_detail}{hint}", parse_mode=ParseMode.MARKDOWN)
                        return
                    else:
                        # Check age
                        try:
                            from mrg_api import parse_auth_date
                            ad = parse_auth_date(clean)
                            if ad and ad.get("ageH", 0) > 20:
                                hint = f"\n\n💡 Link age {ad['ageH']:.1f}h - might be expired. Get a fresh link and try again within 1 hour."
                                await safe_edit(msg, f"❌ MRG login failed: {err_detail}{hint}", parse_mode=ParseMode.MARKDOWN)
                                return
                        except Exception:
                            pass
                await safe_edit(msg, f"❌ MRG login failed: {err_detail}", parse_mode=ParseMode.MARKDOWN)
                return
            db.mrg_add_account(uid, label, clean, extra={"added_at": time.time(), "last_ok": time.time()})
            st = await sess.get_status()
            if st.get("ok"):
                await safe_edit(msg, tr(uid, "mrg_added", label=label, username=st['username'], bal=st['balance'], uncl=st['unclaimed'], lvl=st['level'], speed=st['speed']), parse_mode=ParseMode.MARKDOWN)
            else:
                await safe_edit(msg, f"✅ MRG `{label}` added", parse_mode=ParseMode.MARKDOWN)
            if cfg.AUTO_RUN_ON_ADD:
                asyncio.create_task(_run_single_mrg(update, label))

        else:
            db.generic_add_account(uid, miner_id, label, clean)
            await safe_edit(msg, f"✅ *{miner_id.upper()}* `{label}` added", parse_mode=ParseMode.MARKDOWN)

        _pending_add.pop(uid, None)

    except Exception as e:
        log.exception("auto_add_flow error")
        await safe_edit(msg, f"❌ Error: `{str(e)[:200]}`", parse_mode=ParseMode.MARKDOWN)

async def _run_single_atf(update: Update, label: str):
    uid = update.effective_user.id
    accs = [a for a in db.get_accounts(uid) if a["label"] == label]
    if not accs:
        return
    try:
        app = update.get_bot()
        header = f"⛏ *{label}* - Auto Cycle\n{'─'*28}"
        progress = LiveProgress(app, uid, header)
        await progress.start()
        sess = make_atf_session(accs[0], uid)
        async def cb(e,m,_p=progress): await _p.add(e,m)
        report = await sess.full_cycle(RUN_CFG, step_cb=cb)
        await progress.finish("✅ Completed - runs every 30m" if not report.get("error") else f"❌ {report.get('error')}")
    except Exception as e:
        log.warning("auto-run ATF %s: %s", label, e)

async def _run_single_ailab(update: Update, label: str):
    uid = update.effective_user.id
    accs = [a for a in db.ai_get_accounts(uid) if a["label"] == label]
    if not accs:
        return
    try:
        app = update.get_bot()
        progress = LiveProgress(app, uid, f"🧪 *{label}* - AI Lab\n{'─'*26}")
        await progress.start()
        s = make_ailab_session(accs[0], uid)
        async def cb(e,m,_p=progress): await _p.add(e,m)
        rep = await s.full_cycle(RUN_CFG, step_cb=cb)
        if s.initdata_dead:
            db.ai_update(uid, label, dead=True)
            await progress.finish(f"🔑 Expired - send new link")
        else:
            db.ai_update(uid, label, session=s.session, last_ok=time.time(), dead=False)
            await progress.finish(f"✅ Done")
    except Exception as e:
        log.warning("auto-run AI Lab %s: %s", label, e)

async def _run_single_mrg(update: Update, label: str):
    uid = update.effective_user.id
    accs = [a for a in db.mrg_get_accounts(uid) if a["label"] == label]
    if not accs:
        return
    try:
        app = update.get_bot()
        progress = LiveProgress(app, uid, f"💎 *{label}* - MRG\n{'─'*28}")
        await progress.start()
        s = make_mrg_session(accs[0], uid)
        async def cb(e,m,_p=progress): await _p.add(e,m)
        rep = await s.full_cycle(RUN_CFG, step_cb=cb)
        if s.initdata_dead:
            db.mrg_update(uid, label, dead=True)
            await progress.finish(f"🔑 Expired")
        else:
            db.mrg_update(uid, label, last_ok=time.time(), dead=False)
            await progress.finish(f"✅ Done")
    except Exception as e:
        log.warning("auto-run MRG %s: %s", label, e)

# ── Commands ─────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    uid = update.effective_user.id
    # Professional short welcome - no internal details
    await safe_reply(update, tr(uid, "welcome", contact=cfg.ADMIN_CONTACT), parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb(is_admin(uid)))

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    uid = update.effective_user.id
    await safe_reply(update, tr(uid, "help", contact=cfg.ADMIN_CONTACT), parse_mode=ParseMode.MARKDOWN)

async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    uid = update.effective_user.id
    slots = db.get_user_slots(uid)
    atf_accs = db.get_accounts(uid)
    ai_accs = db.ai_get_accounts(uid)
    mrg_accs = db.mrg_get_accounts(uid)
    total = len(atf_accs) + len(ai_accs) + len(mrg_accs)

    if total == 0:
        await safe_reply(update, tr(uid, "list_empty"), parse_mode=ParseMode.MARKDOWN)
        return

    lines = [
        tr(uid, "list_title", total=total, max_total=slots['max_total']),
        tr(uid, "slots", atf=f"{len(atf_accs)}/{slots['atf']}", ai=f"{len(ai_accs)}/{slots['ailab']}", mrg=f"{len(mrg_accs)}/{slots['mrg']}"),
        ""
    ]

    kb_rows = []

    if atf_accs:
        lines.append("*⛏ ATF:*")
        for a in atf_accs:
            mark = "🟢" if a.get("enabled", True) else "🔴"
            added = time.strftime("%m-%d", time.localtime(a.get("added_at",0))) if a.get("added_at") else "?"
            lines.append(f"  {mark} `{a['label']}` - {added}")
            kb_rows.append([
                InlineKeyboardButton(f"▶ {a['label']}", callback_data=f"runatf:{a['label']}"),
                InlineKeyboardButton(f"🗑 {a['label']}", callback_data=f"rm:atf:{a['label']}")
            ])

    if ai_accs:
        lines.append("\n*🧪 AI Lab:*")
        for a in ai_accs:
            mark = "🔑" if a.get("dead") else ("🟢" if a.get("enabled",True) else "🔴")
            last = a.get("last_ok") or 0
            ago = f"{(time.time()-last)/60:.0f}m ago" if last else "never"
            lines.append(f"  {mark} `{a['label']}` - {ago}")
            kb_rows.append([
                InlineKeyboardButton(f"▶ {a['label']}", callback_data=f"runai:{a['label']}"),
                InlineKeyboardButton(f"🗑 {a['label']}", callback_data=f"rm:ailab:{a['label']}")
            ])

    if mrg_accs:
        lines.append("\n*💎 MRG:*")
        for a in mrg_accs:
            mark = "🔑" if a.get("dead") else ("🟢" if a.get("enabled",True) else "🔴")
            last = a.get("last_ok") or 0
            ago = f"{(time.time()-last)/60:.0f}m ago" if last else "never"
            ad = mrg_parse_date(a.get("init_data",""))
            age = mrg_age_str(ad["ageH"]) if ad else "?"
            lines.append(f"  {mark} `{a['label']}` - {ago} | {age}")
            kb_rows.append([
                InlineKeyboardButton(f"▶ {a['label']}", callback_data=f"runmrg:{a['label']}"),
                InlineKeyboardButton(f"🗑 {a['label']}", callback_data=f"rm:mrg:{a['label']}")
            ])

    await safe_reply(update, "\n".join(lines)[:4000], parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb_rows) if kb_rows else None)

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    uid = update.effective_user.id
    atf_accs = db.get_accounts(uid)
    ai_accs = db.ai_get_accounts(uid)
    mrg_accs = db.mrg_get_accounts(uid)

    if not atf_accs and not ai_accs and not mrg_accs:
        await safe_reply(update, tr(uid, "no_accounts_status"))
        return

    msg = await safe_reply(update, tr(uid, "fetching"))

    lines = [tr(uid, "status_title") + f" - v{cfg.BOT_VERSION}\n"]

    if atf_accs:
        lines.append(f"*⛏ ATF ({len(atf_accs)}):*")
        for a in atf_accs:
            try:
                s = make_atf_session(a, uid)
                ok, _ = await s.login(ref_code=cfg.ATF_REF_CODE)
                if not ok:
                    lines.append(f"  ❌ `{a['label']}` - login failed")
                    continue
                u = s.user_data
                bal = float(u.get("mined_balance") or 0)
                pool = float(u.get("pending_reward") or 0)
                lvl = int(u.get("miner_level") or 1)
                r = rate_atf_hr(lvl)
                gap = max(0.0, level_cost(lvl+1)-bal)
                lines.append(f"  🟢 `{a['label']}` Lv.{lvl} `{r:.4f}/hr`\n     💰 `{bal:.4f}` Pool `{pool:.4f}` Next `+{gap:.2f}`\n     {fmt_mining_status(u)}")
            except Exception as e:
                lines.append(f"  ❌ `{a['label']}` {str(e)[:50]}")
        lines.append("")

    if ai_accs:
        lines.append(f"*🧪 AI Lab ({len(ai_accs)}):*")
        for a in ai_accs:
            label = a["label"]
            if a.get("dead"):
                lines.append(f"  🔑 `{label}` - expired")
                continue
            try:
                s = make_ailab_session(a, uid)
                st = await s.status()
                if s.initdata_dead:
                    db.ai_update(uid, label, dead=True)
                    lines.append(f"  🔑 `{label}` - expired")
                    continue
                if not st.get("ok"):
                    lines.append(f"  ⚠️ `{label}` {st.get('error','error')[:40]}")
                    continue
                db.ai_update(uid, label, session=s.session, last_ok=time.time(), dead=False)
                mining = f"🟢 {ai_hms(st['left'])} left" if st["running"] else "🔴 Stopped"
                lines.append(f"  🟢 `{label}` {st['username']} `${st['balance']:.6f}` Power `{st['power']}`\n     {mining}")
            except Exception as e:
                lines.append(f"  ⚠️ `{label}` {str(e)[:40]}")
        lines.append("")

    if mrg_accs:
        lines.append(f"*💎 MRG ({len(mrg_accs)}):*")
        for a in mrg_accs:
            label = a["label"]
            if a.get("dead"):
                lines.append(f"  🔑 `{label}` - expired")
                continue
            try:
                s = make_mrg_session(a, uid)
                st = await s.get_status()
                if s.initdata_dead:
                    db.mrg_update(uid, label, dead=True)
                    lines.append(f"  🔑 `{label}` - expired")
                    continue
                if not st.get("ok"):
                    lines.append(f"  ⚠️ `{label}` {st.get('error','error')[:40]}")
                    continue
                db.mrg_update(uid, label, last_ok=time.time(), dead=False)
                wallet = "✅" if st["wallet_connected"] else "❌"
                lines.append(
                    f"  🟢 `{label}` {st['username']} `{st['balance']:.4f}` Uncl `{st['unclaimed']:.4f}`\n"
                    f"     L{st['level']} ({st['speed']} TH/s) Hold `{st['holding']:.1f}` Wallet {wallet} ID {st['id_age']}"
                )
            except Exception as e:
                lines.append(f"  ⚠️ `{label}` {str(e)[:40]}")
        lines.append("")

    await safe_edit(msg, "\n".join(lines)[:4000], parse_mode=ParseMode.MARKDOWN)

async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    uid = update.effective_user.id
    slots = db.get_user_slots(uid)
    atf_n = len(db.get_accounts(uid))
    ai_n = len(db.ai_get_accounts(uid))
    mrg_n = len(db.mrg_get_accounts(uid))
    total = atf_n + ai_n + mrg_n
    lang = db.get_user_lang(uid)
    lang_display = {"en": "English 🇬🇧", "bn": "Bengali 🇧🇩"}.get(lang, lang)

    text = tr(uid, "settings_body",
              atf_n=atf_n, atf_s=slots['atf'],
              ai_n=ai_n, ai_s=slots['ailab'],
              mrg_n=mrg_n, mrg_s=slots['mrg'],
              total=total, max_total=slots['max_total'],
              lang=lang_display,
              contact=cfg.ADMIN_CONTACT)

    full_text = f"{tr(uid, 'settings_title')}\n{'─'*20}\n\n{text}"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
         InlineKeyboardButton("🇧🇩 Bengali", callback_data="lang:bn")],
        [InlineKeyboardButton("📋 My Accounts", callback_data="goto:list"),
         InlineKeyboardButton("📊 Status", callback_data="goto:status")],
        [InlineKeyboardButton("❓ Help", callback_data="goto:help")],
    ])

    await safe_reply(update, full_text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

async def cmd_export(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    uid = update.effective_user.id
    data = db.export_user_data(uid)
    mrg_len = len(data.get('generic',{}).get('mrg',[])) if not data.get('mongo') else len(data.get('mrg_accounts',[]))
    await safe_reply(update, tr(uid, "export_title", atf=len(data['atf']), ai=len(data['ailab']), mrg=mrg_len), parse_mode=ParseMode.MARKDOWN)
    try:
        import json, tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(data,f,indent=2,ensure_ascii=False); fname=f.name
        await update.message.reply_document(document=open(fname,'rb'), filename=f"backup_{uid}_{int(time.time())}.json", caption="🔐 Private backup")
        os.unlink(fname)
    except Exception as e:
        log.warning("Export fail: %s", e)

# ── Admin Panel v5.0 ──────────────────────────────────────────
def _admin_panel_text() -> str:
    st = db.global_stats()
    ai = db.ai_stats()
    mrg = db.mrg_stats()
    px = PROXY.stats()
    age = f"{px['age_hours']:.1f}h" if px['age_hours']>=0 else "never"
    slots_all = db.get_all_slots()
    total_users = len(db.get_all_users())
    mongo = db.mongo_status()
    mongo_txt = f"🟢 {mongo.get('db')} ATF:{mongo.get('atf')} MRG:{mongo.get('mrg')}" if mongo.get("enabled") else f"🟡 {mongo.get('reason')}"

    return (
        f"👑 *Admin Panel v{cfg.BOT_VERSION}*\n{'─'*28}\n\n"
        f"*DB:* {mongo_txt}\n"
        f"*Refer:* ATF `{cfg.ATF_REF_CODE}` | MRG `{cfg.MRG_REF_CODE}`\n\n"
        f"*Users:* `{total_users}` | Slots custom `{len(slots_all)}`\n"
        f"ATF: `{st['accounts']}` ({st['enabled']} on) Users `{st['users']}`\n"
        f"AI Lab: `{ai['accounts']}` ({ai['enabled']}) Dead `{ai['dead']}`\n"
        f"MRG: `{mrg['accounts']}` ({mrg['enabled']}) Dead `{mrg['dead']}`\n\n"
        f"*Proxy:* `{px['healthy']}/{cfg.PROXY_MIN_HEALTHY}` | Sources `{px['sources']}` | Age `{age}`\n"
        f"*Miners:* `{', '.join(list_miners())}`\n"
    )

def _admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Users", callback_data="ad_users"),
         InlineKeyboardButton("📋 Accounts", callback_data="ad_accs")],
        [InlineKeyboardButton("🌐 Proxy", callback_data="ad_proxy"),
         InlineKeyboardButton("🔄 Refresh Proxy", callback_data="px_refresh")],
        [InlineKeyboardButton("💎 Slots", callback_data="ad_slots"),
         InlineKeyboardButton("📈 System", callback_data="ad_sys")],
        [InlineKeyboardButton("🗄️ MongoDB", callback_data="ad_mongo"),
         InlineKeyboardButton("🔗 Refer", callback_data="ad_refer")],
        [InlineKeyboardButton("▶️ Enable All", callback_data="ad_en_all"),
         InlineKeyboardButton("⏸ Disable All", callback_data="ad_dis_all")],
        [InlineKeyboardButton("🚀 Run All", callback_data="ad_runall"),
         InlineKeyboardButton("📢 Broadcast", callback_data="ad_bc")],
        [InlineKeyboardButton("♻️ Refresh", callback_data="ad_home")],
    ])

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await safe_reply(update, "⛔ Admins only.")
        return
    await safe_reply(update, _admin_panel_text(), parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())

async def cmd_setslot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await safe_reply(update, "⛔ Admins only."); return
    if len(ctx.args) < 3:
        await safe_reply(update,
            "Usage: `/setslot <user_id> <miner> <count>`\n\nMiner: atf, ailab, mrg, max_total",
            parse_mode=ParseMode.MARKDOWN); return
    try:
        target = int(ctx.args[0]); miner = ctx.args[1].lower(); count = int(ctx.args[2])
    except ValueError:
        await safe_reply(update, "❌ user_id and count must be numbers."); return
    if miner not in ("atf", "ailab", "mrg", "max_total"):
        await safe_reply(update, "❌ Miner must be: atf, ailab, mrg, max_total"); return
    if db.set_user_slot(target, miner, count):
        slots = db.get_user_slots(target)
        await safe_reply(update, f"✅ Slot updated for `{target}`: {miner} = `{count}`\nATF `{slots['atf']}` AI `{slots['ailab']}` MRG `{slots['mrg']}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await safe_reply(update, "❌ Failed")

async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): await safe_reply(update, "⛔ Admins only."); return
    if not ctx.args: await safe_reply(update, "Usage: /broadcast <msg>"); return
    text = " ".join(ctx.args); users = db.get_all_users()
    m = await safe_reply(update, f"📢 Sending to {len(users)} users...")
    ok = fail = 0
    for u in users:
        try: await ctx.bot.send_message(u, f"📢 *Announcement*\n\n{text}", parse_mode=ParseMode.MARKDOWN); ok+=1
        except Exception: fail+=1
        await asyncio.sleep(0.05)
    await safe_edit(m, f"📢 Done. ✅ {ok} ❌ {fail}")

async def cmd_purge(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): await safe_reply(update, "⛔ Admins only."); return
    if not ctx.args: await safe_reply(update, "Usage: /purge <user_id>"); return
    try: target = int(ctx.args[0])
    except ValueError: await safe_reply(update, "❌ user_id must be number."); return
    n = db.purge_user(target)
    await safe_reply(update, f"🗑 Removed {n} account(s) of `{target}`.", parse_mode=ParseMode.MARKDOWN)

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data or ""

    if data == "fj_retry":
        await force_join.handle_retry(update, cfg)
        return

    if data.startswith("addsel:"):
        miner_id = data.split(":",1)[1]
        pending = _pending_add.get(uid)
        if not pending:
            await query.answer("❌ No pending token. Paste again.", show_alert=True)
            return
        await query.answer(f"Selected {miner_id.upper()}", show_alert=False)
        try:
            await query.edit_message_text(f"⏳ Adding to *{miner_id.upper()}*...", parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        raw = pending.get("raw")
        _pending_add.pop(uid, None)
        await auto_add_flow(update, raw, forced_miner=miner_id)
        return

    # Language change
    if data.startswith("lang:"):
        lang = data.split(":",1)[1]
        db.set_user_lang(uid, lang)
        lang_name = {"en": "English 🇬🇧", "bn": "Bengali 🇧🇩"}.get(lang, lang)
        await query.answer(tr(uid, "lang_changed", lang=lang_name), show_alert=False)
        # Refresh settings
        try:
            slots = db.get_user_slots(uid)
            atf_n = len(db.get_accounts(uid)); ai_n = len(db.ai_get_accounts(uid)); mrg_n = len(db.mrg_get_accounts(uid))
            total = atf_n+ai_n+mrg_n
            lang_display = {"en": "English 🇬🇧", "bn": "Bengali 🇧🇩"}.get(lang, lang)
            text = tr(uid, "settings_body", atf_n=atf_n, atf_s=slots['atf'], ai_n=ai_n, ai_s=slots['ailab'], mrg_n=mrg_n, mrg_s=slots['mrg'], total=total, max_total=slots['max_total'], lang=lang_display, contact=cfg.ADMIN_CONTACT)
            full = f"{tr(uid, 'settings_title')}\n{'─'*20}\n\n{text}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"), InlineKeyboardButton("🇧🇩 Bengali", callback_data="lang:bn")],
                [InlineKeyboardButton("📋 My Accounts", callback_data="goto:list"), InlineKeyboardButton("📊 Status", callback_data="goto:status")],
            ])
            await safe_edit(query.message, full, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            pass
        return

    # Goto from settings
    if data.startswith("goto:"):
        dest = data.split(":",1)[1]
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
        # Create fake update for command
        if dest == "list":
            await cmd_list(update, ctx)
        elif dest == "status":
            await cmd_status(update, ctx)
        elif dest == "help":
            await cmd_help(update, ctx)
        return

    await query.answer()

    if data == "px_refresh":
        await safe_edit(query.message, "🔄 Refreshing proxy pool...\n~30-90s", parse_mode=ParseMode.MARKDOWN)
        n = await PROXY.refresh(force=True)
        px = PROXY.stats()
        await safe_edit(query.message, f"✅ Proxy refreshed: *{n}* healthy\nSources: `{px['sources']}`", parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("ad_"):
        if not is_admin(uid):
            await query.answer("⛔ Admins only.", show_alert=True); return

        if data == "ad_home":
            await safe_edit(query.message, _admin_panel_text(), parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())
        elif data == "ad_users":
            users = db.get_all_users()
            slots_all = db.get_all_slots()
            lines = ["👥 *Users*\n", "─"*20]
            kb_rows = []
            for u in users[:30]:
                atf = len(db.get_accounts(u)); ai = len(db.ai_get_accounts(u)); mrg = len(db.mrg_get_accounts(u))
                slot = slots_all.get(str(u), db.get_default_slots())
                lines.append(f"`{u}` - ATF {atf}/{slot.get('atf',1)} AI {ai}/{slot.get('ailab',1)} MRG {mrg}/{slot.get('mrg',1)}")
                kb_rows.append([InlineKeyboardButton(f"👤 {u} ({atf+ai+mrg})", callback_data=f"ad_user:{u}")])
            kb_rows.append([InlineKeyboardButton("♻️ Refresh", callback_data="ad_home")])
            await safe_edit(query.message, "\n".join(lines)[:4000] or "No users", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb_rows))
        elif data.startswith("ad_user:"):
            try: target = int(data.split(":")[1])
            except Exception: return
            slots = db.get_user_slots(target)
            atf_accs = db.get_accounts(target); ai_accs = db.ai_get_accounts(target); mrg_accs = db.mrg_get_accounts(target)
            text = f"👤 *User {target}*\n{'─'*20}\n\nATF `{len(atf_accs)}/{slots['atf']}` AI `{len(ai_accs)}/{slots['ailab']}` MRG `{len(mrg_accs)}/{slots['mrg']}` Total `{len(atf_accs)+len(ai_accs)+len(mrg_accs)}/{slots['max_total']}`\n"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"ATF {slots['atf']} -", callback_data=f"slot:{target}:atf:-1"), InlineKeyboardButton(f"ATF {slots['atf']} +", callback_data=f"slot:{target}:atf:+1")],
                [InlineKeyboardButton(f"AI {slots['ailab']} -", callback_data=f"slot:{target}:ailab:-1"), InlineKeyboardButton(f"AI {slots['ailab']} +", callback_data=f"slot:{target}:ailab:+1")],
                [InlineKeyboardButton(f"MRG {slots['mrg']} -", callback_data=f"slot:{target}:mrg:-1"), InlineKeyboardButton(f"MRG {slots['mrg']} +", callback_data=f"slot:{target}:mrg:+1")],
                [InlineKeyboardButton("🗑 Purge", callback_data=f"ad_purge:{target}"), InlineKeyboardButton("📋 View", callback_data=f"ad_viewacc:{target}")],
                [InlineKeyboardButton("🔙 Users", callback_data="ad_users"), InlineKeyboardButton("🏠 Home", callback_data="ad_home")],
            ])
            await safe_edit(query.message, text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        elif data == "ad_slots":
            slots_all = db.get_all_slots()
            lines = ["💎 *Slots*\n", "─"*24]
            if not slots_all:
                lines.append("No custom slots")
            else:
                for uid_str, slot in list(slots_all.items())[:30]:
                    try: uid_int = int(uid_str)
                    except: continue
                    atf = len(db.get_accounts(uid_int)); ai = len(db.ai_get_accounts(uid_int)); mrg = len(db.mrg_get_accounts(uid_int))
                    lines.append(f"`{uid_str}` - ATF {atf}/{slot.get('atf',1)} AI {ai}/{slot.get('ailab',1)} MRG {mrg}/{slot.get('mrg',1)}")
            await safe_edit(query.message, "\n".join(lines)[:4000], parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())
        elif data == "ad_sys":
            st = db.global_stats(); ai = db.ai_stats(); mrg = db.mrg_stats(); px = PROXY.stats()
            import psutil, platform
            try: mem = psutil.virtual_memory(); mem_txt = f"{mem.percent}%"; cpu = f"{psutil.cpu_percent()}%"
            except: mem_txt = "N/A"; cpu = "N/A"
            text = f"📈 *System*\n{'─'*20}\n\nBot v{cfg.BOT_VERSION} Python {platform.python_version()}\nCPU {cpu} MEM {mem_txt}\n\nUsers `{len(db.get_all_users())}`\nATF `{st['accounts']}` AI `{ai['accounts']}` MRG `{mrg['accounts']}`\nProxy `{px['healthy']}/{cfg.PROXY_MIN_HEALTHY}`"
            await safe_edit(query.message, text, parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())
        elif data == "ad_accs":
            atf = db.all_accounts_flat(); ai = db.ai_all_flat(); mrg = db.mrg_all_flat()
            lines = [f"📋 All - ATF {len(atf)} AI {len(ai)} MRG {len(mrg)}\n", "─"*20]
            for a in atf[:15]: lines.append(f"⛏ `{a['label']}` Owner `{a['owner_id']}`")
            for a in mrg[:10]: lines.append(f"💎 `{a['label']}` Owner `{a['owner_id']}`")
            await safe_edit(query.message, "\n".join(lines)[:4000] or "No accounts", parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())
        elif data == "ad_proxy":
            px = PROXY.stats()
            sample = "\n".join(f"`{p[:50]}`" for p in PROXY.healthy[:10]) or "_empty_"
            await safe_edit(query.message, f"🌐 *Proxy* Healthy `{px['healthy']}` Sources `{px['sources']}`\n\n{sample}", parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())
        elif data == "ad_mongo":
            mongo = db.mongo_status()
            if mongo.get("enabled"):
                text = f"🗄️ *MongoDB* 🟢\nDB `{mongo.get('db')}`\nATF `{mongo.get('atf')}` AI `{mongo.get('ailab')}` MRG `{mongo.get('mrg')}`"
            else:
                text = f"🗄️ *MongoDB* 🟡\n{mongo.get('reason')}"
            await safe_edit(query.message, text, parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())
        elif data == "ad_refer":
            # Only admin sees refer - hidden from public
            text = f"🔗 *Refer (Admin Only)*\n\nATF: `{cfg.ATF_REF_CODE}`\n{cfg.ATF_REF_LINK}\n\nMRG: `{cfg.MRG_REF_CODE}`\n{cfg.MRG_REF_LINK}\nParam `{cfg.MRG_START_PARAM}`"
            await safe_edit(query.message, text, parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())
        elif data == "ad_en_all":
            n = db.set_enabled_all(True)
            await query.answer(f"Enabled {n}", show_alert=True)
            await safe_edit(query.message, _admin_panel_text(), parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())
        elif data == "ad_dis_all":
            n = db.set_enabled_all(False)
            await query.answer(f"Disabled {n}", show_alert=True)
            await safe_edit(query.message, _admin_panel_text(), parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())
        elif data == "ad_runall":
            atf_accs = db.get_all_enabled(); ai_accs = db.ai_all_enabled(); mrg_accs = db.mrg_all_enabled()
            total = len(atf_accs)+len(ai_accs)+len(mrg_accs)
            if total==0: await query.answer("No accounts", show_alert=True); return
            await safe_edit(query.message, f"🚀 Running {total} accounts...", parse_mode=ParseMode.MARKDOWN)
            from collections import defaultdict
            by_owner_atf = defaultdict(list)
            for a in atf_accs: by_owner_atf[a["owner_id"]].append(a)
            for owner, lst in by_owner_atf.items(): asyncio.create_task(_run_atf_bg_wrapper(ctx.application, owner, lst))
            by_owner_mrg = defaultdict(list)
            for a in mrg_accs: by_owner_mrg[a["owner_id"]].append(a)
            for owner, lst in by_owner_mrg.items(): asyncio.create_task(_run_mrg_bg_wrapper(ctx.application, owner, lst))
            for owner in set([a["owner_id"] for a in ai_accs]):
                accs = [a for a in ai_accs if a["owner_id"]==owner]
                asyncio.create_task(_run_ailab_bg_wrapper(ctx.application, owner, accs))
        elif data == "ad_bc":
            await safe_edit(query.message, "📢 Use /broadcast <msg>", parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())
        elif data.startswith("ad_purge:"):
            try: target = int(data.split(":")[1])
            except: return
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ Yes purge {target}", callback_data=f"ad_purge_confirm:{target}")],[InlineKeyboardButton("❌ Cancel", callback_data=f"ad_user:{target}")]])
            await safe_edit(query.message, f"⚠️ Purge user `{target}`?", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        elif data.startswith("ad_purge_confirm:"):
            target = int(data.split(":")[1])
            n = db.purge_user(target)
            await query.answer(f"Purged {n}", show_alert=True)
            await safe_edit(query.message, _admin_panel_text(), parse_mode=ParseMode.MARKDOWN, reply_markup=_admin_kb())
        elif data.startswith("ad_viewacc:"):
            target = int(data.split(":")[1])
            atf = db.get_accounts(target); ai = db.ai_get_accounts(target); mrg = db.mrg_get_accounts(target)
            lines = [f"📋 *{target}*\n", f"ATF {len(atf)} AI {len(ai)} MRG {len(mrg)}\n"]
            for a in atf: lines.append(f"⛏ `{a['label']}`")
            for a in mrg: lines.append(f"💎 `{a['label']}`")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"ad_user:{target}"), InlineKeyboardButton("🏠 Home", callback_data="ad_home")]])
            await safe_edit(query.message, "\n".join(lines)[:4000] or "No accounts", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        return

    if data.startswith("slot:"):
        if not is_admin(uid): await query.answer("⛔ Admins only", show_alert=True); return
        try: _, user_id_str, miner_id, delta_str = data.split(":"); target = int(user_id_str); delta = int(delta_str)
        except: return
        current = db.get_user_slot(target, miner_id)
        new_val = max(0, min(current + delta, cfg.ABSOLUTE_MAX_SLOT_PER_PLATFORM))
        db.set_user_slot(target, miner_id, new_val)
        slots = db.get_user_slots(target)
        text = f"👤 *User {target}* Slot {miner_id} {current}→{new_val}\nATF `{slots['atf']}` AI `{slots['ailab']}` MRG `{slots['mrg']}` Total `{slots['max_total']}`"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"ATF {slots['atf']} -", callback_data=f"slot:{target}:atf:-1"), InlineKeyboardButton(f"ATF {slots['atf']} +", callback_data=f"slot:{target}:atf:+1")],
            [InlineKeyboardButton(f"MRG {slots['mrg']} -", callback_data=f"slot:{target}:mrg:-1"), InlineKeyboardButton(f"MRG {slots['mrg']} +", callback_data=f"slot:{target}:mrg:+1")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"ad_user:{target}"), InlineKeyboardButton("🏠 Home", callback_data="ad_home")],
        ])
        await safe_edit(query.message, text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        await query.answer(f"{miner_id} {current}→{new_val}", show_alert=False)
        return

    if data.startswith("runatf:"):
        label = data.split(":",1)[1]
        accs = [a for a in db.get_accounts(uid) if a["label"]==label]
        if not accs: await query.edit_message_text(f"❌ `{label}` not found.", parse_mode=ParseMode.MARKDOWN); return
        if uid in _active_runs and not _active_runs[uid].done(): await query.edit_message_text("⚠️ Run in progress"); return
        await query.edit_message_text(f"🚀 Starting ATF *{label}*...", parse_mode=ParseMode.MARKDOWN)
        task = asyncio.create_task(_run_atf_bg_wrapper(ctx.application, uid, accs))
        _active_runs[uid]=task
        task.add_done_callback(lambda t: _active_runs.pop(uid,None))
    elif data.startswith("runai:"):
        label = data.split(":",1)[1]
        accs = [a for a in db.ai_get_accounts(uid) if a["label"]==label]
        if not accs: await query.edit_message_text(f"❌ `{label}` not found.", parse_mode=ParseMode.MARKDOWN); return
        await query.edit_message_text(f"🚀 Starting AI Lab *{label}*...", parse_mode=ParseMode.MARKDOWN)
        asyncio.create_task(_run_ailab_bg_wrapper(ctx.application, uid, accs))
    elif data.startswith("runmrg:"):
        label = data.split(":",1)[1]
        accs = [a for a in db.mrg_get_accounts(uid) if a["label"]==label]
        if not accs: await query.edit_message_text(f"❌ `{label}` not found.", parse_mode=ParseMode.MARKDOWN); return
        if uid in _active_runs and not _active_runs[uid].done(): await query.edit_message_text("⚠️ Run in progress"); return
        await query.edit_message_text(f"🚀 Starting MRG *{label}*...", parse_mode=ParseMode.MARKDOWN)
        task = asyncio.create_task(_run_mrg_bg_wrapper(ctx.application, uid, accs))
        _active_runs[uid]=task
        task.add_done_callback(lambda t: _active_runs.pop(uid,None))
    elif data.startswith("rm:"):
        try: _, miner_id, label = data.split(":",2)
        except: return
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ Yes delete {label}", callback_data=f"rmconfirm:{miner_id}:{label}")],[InlineKeyboardButton("❌ Cancel", callback_data="rmcancel")]])
        await query.edit_message_text(f"⚠️ Delete *{miner_id.upper()}* `{label}`?", parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    elif data.startswith("rmconfirm:"):
        _, miner_id, label = data.split(":",2)
        ok = False
        if miner_id == "atf": ok = db.remove_account(uid, label)
        elif miner_id == "ailab": ok = db.ai_remove_account(uid, label)
        elif miner_id == "mrg": ok = db.mrg_remove_account(uid, label)
        else: ok = db.generic_remove_account(uid, miner_id, label)
        if ok: await query.edit_message_text(f"✅ `{miner_id.upper()}` `{label}` removed.", parse_mode=ParseMode.MARKDOWN)
        else: await query.edit_message_text(f"❌ `{label}` not found.", parse_mode=ParseMode.MARKDOWN)
    elif data == "rmcancel":
        await query.edit_message_text("❌ Cancelled.", parse_mode=ParseMode.MARKDOWN)

async def _run_atf_bg_wrapper(app, chat_id: int, accounts: List[Dict]):
    sem = asyncio.Semaphore(3)
    async def run_one(acc_data):
        async with sem:
            label = acc_data["label"]
            header = f"⛏ *{label}* - ATF\n{'─'*26}"
            progress = LiveProgress(app.bot, chat_id, header)
            await progress.start()
            try:
                sess = make_atf_session(acc_data, chat_id)
                async def cb(e,m,_p=progress): await _p.add(e,m)
                report = await sess.full_cycle(RUN_CFG, step_cb=cb)
                await progress.finish(f"❌ `{report['error']}`" if report.get("error") else "✅ Done")
            except Exception as e:
                await progress.finish(f"❌ `{e}`")
            await asyncio.sleep(1.5)
    await asyncio.gather(*[run_one(a) for a in accounts], return_exceptions=True)

async def _run_ailab_bg_wrapper(app, chat_id: int, accs: List[Dict]):
    for a in accs:
        label = a["label"]
        progress = LiveProgress(app.bot, chat_id, f"🧪 *{label}* - AI Lab\n{'─'*26}")
        await progress.start()
        try:
            s = make_ailab_session(a, chat_id)
            async def cb(e,m,_p=progress): await _p.add(e,m)
            rep = await s.full_cycle(RUN_CFG, step_cb=cb)
            if s.initdata_dead: db.ai_update(chat_id, label, dead=True); await progress.finish("🔑 Expired")
            else: db.ai_update(chat_id, label, session=s.session, last_ok=time.time(), dead=False); await progress.finish("✅ Done")
        except Exception as e:
            await progress.finish(f"❌ {e}")
        await asyncio.sleep(2)

async def _run_mrg_bg_wrapper(app, chat_id: int, accounts: List[Dict]):
    sem = asyncio.Semaphore(2)
    async def run_one(acc_data):
        async with sem:
            label = acc_data["label"]
            progress = LiveProgress(app.bot, chat_id, f"💎 *{label}* - MRG\n{'─'*28}")
            await progress.start()
            try:
                s = make_mrg_session(acc_data, chat_id)
                async def cb(e,m,_p=progress): await _p.add(e,m)
                rep = await s.full_cycle(RUN_CFG, step_cb=cb)
                if s.initdata_dead: db.mrg_update(chat_id, label, dead=True); await progress.finish("🔑 Expired")
                else: db.mrg_update(chat_id, label, last_ok=time.time(), dead=False); await progress.finish("✅ Done")
            except Exception as e:
                await progress.finish(f"❌ {e}")
            await asyncio.sleep(2)
    await asyncio.gather(*[run_one(a) for a in accounts], return_exceptions=True)

async def msg_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return

    menu_map = {
        "📋 My Accounts": cmd_list,
        "📊 Status": cmd_status,
        "❓ Help": cmd_help,
        "⚙️ Settings": cmd_settings,
        "👑 Admin Panel": cmd_admin,
    }
    if text in menu_map:
        await menu_map[text](update, ctx)
        return

    low = text.lower()
    is_potential_token = (
        ("user=" in low and "hash=" in low) or
        "tgwebappdata=" in low or
        "atfminers.asloni.online" in low or
        "ailab-agent.online" in low or
        "mrgtoken.xyz" in low or
        "mrgminerbot" in low or
        "mrg.up.railway.app" in low
    )

    if is_potential_token:
        await auto_add_flow(update, text)
        return

    if len(text) > 5 and len(text) < 20:
        await safe_reply(update, "💡 Just paste your mining link to add account.\n\nUse /list to view accounts.", parse_mode=ParseMode.MARKDOWN)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Error: %s", context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text("❌ Error, try again.")
            except Exception:
                pass
    except Exception:
        pass

def main():
    os.makedirs(os.path.join(os.path.dirname(__file__), "logs"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "data"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "data", "miners"), exist_ok=True)

    errors = cfg.validate()
    if errors:
        print("❌ Config errors:")
        for e in errors: print(f"  • {e}")
        if cfg.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
            print("\n💡 Set BOT_TOKEN in .env")
        sys.exit(1)

    try:
        if cfg.MONGO_URL:
            db.mongo_status()
    except Exception as e:
        print(f"⚠️ MongoDB init warning: {e}")

    app = Application.builder().token(cfg.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("setslot", cmd_setslot))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("purge", cmd_purge))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))
    app.add_error_handler(error_handler)

    sched_manager = SchedulerManager(app, RUN_CFG)

    async def _startup(application):
        PROXY.start()
        if PROXY.enabled and len(PROXY.healthy) < PROXY.min_healthy:
            asyncio.create_task(PROXY.refresh(force=True))
        sched_manager.start_all()
        mongo_info = db.mongo_status()
        log.info("Bot v%s started | DB %s | Miners %s", cfg.BOT_VERSION, "MongoDB" if mongo_info.get("enabled") else "JSON", ", ".join(list_miners()))

    async def _shutdown(application):
        sched_manager.stop_all()
        PROXY.stop()
        for t in _active_runs.values():
            if not t.done(): t.cancel()
        log.info("Bot shutdown")

    app.post_init = _startup
    app.post_shutdown = _shutdown

    print(f"🚀 Mining Bot v{cfg.BOT_VERSION} — PROFESSIONAL")
    print(f"   DB: {cfg.mongo_info()}")
    print(f"   ATF Ref: {cfg.ATF_REF_CODE} (hidden from public)")
    print(f"   MRG Ref: {cfg.MRG_REF_CODE} (hidden from public)")
    print(f"   Miners: {', '.join(list_miners())}")

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
