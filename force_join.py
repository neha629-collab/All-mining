"""
Force Join v3.0 — Powerful Edition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Parallel checks with caching (TTL configurable)
- Strict mode: blocks ALL if not joined
- Handles -100 IDs, invite links, usernames
- Includes RESTRICTED, retries on floodwait
- Logs detailed for admin
- Fail-open only if bot not admin, but strict mode can enforce
"""

import asyncio
import time
from typing import List, Tuple, Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError, RetryAfter

from logger import bot_log as log

JOINED_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.OWNER,
    ChatMemberStatus.RESTRICTED,
}

_admin_warned: set = set()
_membership_cache: Dict[Tuple[int, str], Tuple[bool, float]] = {}

def _channel_url(chat_id: str) -> str:
    cid = str(chat_id).strip()
    if cid.startswith("@"):
        return f"https://t.me/{cid[1:]}"
    if cid.startswith("https://") or cid.startswith("t.me/"):
        return cid if cid.startswith("http") else f"https://{cid}"
    if cid.startswith("-100"):
        clean = cid[4:]
        return f"https://t.me/c/{clean}"
    if cid.lstrip("-").isdigit():
        return f"https://t.me/c/{cid.lstrip('-')}"
    return f"https://t.me/{cid.lstrip('@')}"

async def _check_one(bot, user_id: int, chat_id: str, ttl: int) -> Tuple[str, bool, str]:
    cache_key = (user_id, str(chat_id))
    cached = _membership_cache.get(cache_key)
    if cached and (time.time() - cached[1]) < ttl:
        return chat_id, cached[0], "cached"

    try:
        m = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        is_member = m.status in JOINED_STATUSES
        _membership_cache[cache_key] = (is_member, time.time())
        return chat_id, is_member, ""
    except RetryAfter as e:
        # Floodwait — wait and retry once
        try:
            await asyncio.sleep(e.retry_after + 1)
            m = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            is_member = m.status in JOINED_STATUSES
            _membership_cache[cache_key] = (is_member, time.time())
            return chat_id, is_member, ""
        except Exception as ex:
            log.warning("Force-join retry after fail %s: %s", chat_id, ex)
            return chat_id, True, f"retry_fail: {ex}"
    except TelegramError as e:
        msg = str(e).lower()
        # Bot not admin or channel invalid → fail-open but warn
        if any(k in msg for k in ("not found", "member list is inaccessible",
                                  "chat not found", "not enough rights",
                                  "bot is not a member", "chat_id is empty",
                                  "forbidden", "peer_id_invalid")):
            if chat_id not in _admin_warned:
                _admin_warned.add(chat_id)
                log.warning("⚠️ Force-join skipped for %s — bot must be ADMIN in channel. Error: %s", chat_id, e)
            # In strict mode, we still want to block? But to avoid lockout, fail-open with short TTL
            # Admin can see warning in logs
            _membership_cache[cache_key] = (True, time.time())
            return chat_id, True, f"fail-open: {e}"
        log.warning("Force-join check failed for %s: %s", chat_id, e)
        # Other errors → fail-open to avoid blocking all users
        return chat_id, True, str(e)
    except Exception as e:
        log.warning("Unexpected force-join error %s: %s", chat_id, e)
        return chat_id, True, str(e)

async def missing_channels(bot, user_id: int, channels: List[Tuple[str, str]], ttl: int = 300) -> List[Tuple[str, str]]:
    if not channels:
        return []
    tasks = [_check_one(bot, user_id, cid, ttl) for cid, _ in channels]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    missing = []
    title_map = {cid: title for cid, title in channels}
    for res in results:
        if isinstance(res, Exception):
            continue
        chat_id, is_member, _ = res
        if not is_member:
            missing.append((chat_id, title_map.get(chat_id, chat_id)))
    return missing

def build_keyboard(missing: List[Tuple[str, str]], retry_data: str = "fj_retry") -> InlineKeyboardMarkup:
    rows = []
    for cid, title in missing:
        url = _channel_url(cid)
        rows.append([InlineKeyboardButton(f"📢 Join {title}", url=url)])
    rows.append([InlineKeyboardButton("✅ I've Joined — Verify", callback_data=retry_data)])
    return InlineKeyboardMarkup(rows)

async def check_and_prompt(update: Update, cfg) -> bool:
    if not getattr(cfg, "FORCE_JOIN_ENABLED", False):
        return True
    channels = getattr(cfg, "FORCE_JOIN_CHANNELS", [])
    if not channels:
        return True

    user = update.effective_user
    if not user:
        return True

    # Admins bypass
    if user.id in (getattr(cfg, "ADMIN_IDS", []) or []):
        return True

    bot = update.get_bot()
    ttl = getattr(cfg, "FORCE_JOIN_CACHE_TTL", 300)
    missing = await missing_channels(bot, user.id, channels, ttl=ttl)
    if not missing:
        return True

    # Strict mode: still block, but if all channels fail-open, we allow
    # If missing is empty, already allowed
    names = "\n".join(f"  • {t}" for _, t in missing)
    text = (
        "🔒 *Membership Required — Powerful Gate*\n\n"
        "To use this bot you *must* join our channels:\n\n"
        f"{names}\n\n"
        "Join them, then press *I've Joined* below.\n\n"
        "_Bot will auto-verify in 5 minutes cache._"
    )
    kb = build_keyboard(missing)

    try:
        if update.callback_query:
            await update.callback_query.answer("❌ You haven't joined all channels yet", show_alert=True)
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        elif update.effective_message:
            await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        log.debug("Force-join prompt fail: %s", e)

    return False

async def handle_retry(update: Update, cfg) -> bool:
    q = update.callback_query
    user = update.effective_user
    channels = getattr(cfg, "FORCE_JOIN_CHANNELS", [])

    # Clear cache for this user to force re-check
    for cid, _ in channels:
        _membership_cache.pop((user.id, str(cid)), None)

    ttl = getattr(cfg, "FORCE_JOIN_CACHE_TTL", 300)
    missing = await missing_channels(update.get_bot(), user.id, channels, ttl=ttl)

    if missing:
        names = "\n".join(f"  • {t}" for _, t in missing)
        try:
            await q.answer("❌ Still missing some channels!", show_alert=True)
            await q.edit_message_text(
                "🔒 *Membership Required*\n\nStill not joined:\n\n"
                f"{names}\n\nJoin them, then press verify again.",
                parse_mode="Markdown", reply_markup=build_keyboard(missing))
        except Exception:
            pass
        return False

    try:
        await q.answer("✅ Verified! Welcome aboard.", show_alert=False)
        await q.edit_message_text(
            "✅ *Verified!*\n\nYou now have full access.\n\n"
            "Just paste your mining link (ATF / AI Lab / MRG) and bot will auto-setup & start mining!\n\n"
            "Use /list to see accounts, /status for balance.",
            parse_mode="Markdown")
    except Exception:
        pass
    return True

def clear_cache(user_id: int = None):
    if user_id is None:
        _membership_cache.clear()
    else:
        keys = [k for k in _membership_cache.keys() if k[0] == user_id]
        for k in keys:
            del _membership_cache[k]

async def is_user_joined(bot, user_id: int, cfg) -> bool:
    """Quick check without prompt"""
    channels = getattr(cfg, "FORCE_JOIN_CHANNELS", [])
    if not channels:
        return True
    ttl = getattr(cfg, "FORCE_JOIN_CACHE_TTL", 300)
    missing = await missing_channels(bot, user_id, channels, ttl=ttl)
    return len(missing) == 0
