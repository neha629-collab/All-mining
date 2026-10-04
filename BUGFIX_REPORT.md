# 🐛 Bug Fix Report — v1 → v2.0-PRO

## Critical Security Bugs (FIXED)

### 1. `eval()` Code Injection in atf_api.py
**Location:** `_solve_math()` L115
```python
# OLD (DANGEROUS):
return str(int(round(eval(q))))  # noqa: S307
```
**Risk:** If server sends malicious question like `__import__('os').system('rm -rf /')`, eval executes it!
**Fix:** Replaced with safe AST parser:
```python
def _safe_eval(expr):
    # Only allows digits and + - * / ( )
    # Uses ast.parse + operator mapping
```
**Status:** ✅ FIXED

### 2. Markdown Injection
**Location:** bot.py — user-controlled label inserted directly into Markdown
**Risk:** Label `*bold*` or `` `code` `` breaks formatting, can spoof messages
**Fix:** Added `sanitize_markdown()` and validation `^[a-zA-Z0-9_-]+$`
**Status:** ✅ FIXED

---

## Race Conditions & Data Loss

### 3. DB Race Condition
**Location:** db.py — `threading.Lock()` used but async code can interleave
- Two coroutines calling `add_account` simultaneously could corrupt JSON
- No atomic write — crash mid-write = empty file

**Fix:**
- Use `RLock` + atomic write (write to .tmp then os.replace)
- Backup on JSONDecodeError
- Added `BACKUP_DIR` with timestamped backups
- Fixed `_AILAB_FILE` path bug: was `os.path.dirname(os.path.abspath(__file__))` + `data/ailab.json` which could be wrong when imported. Now uses `cfg.DATA_DIR`

**Status:** ✅ FIXED

### 4. Proxy Assignment Race
**Location:** proxy_manager.py — `assigned` dict mutated without lock
**Fix:** Added `asyncio.Lock` for refresh, sync lock for assignment
**Status:** ✅ FIXED

### 5. Progress Message Rate Limit
**Location:** bot.py & scheduler.py — `LiveProgress.add()` edited message on every step without throttle
**Risk:** Telegram returns 429 FloodWait, bot gets blocked
**Fix:** Throttle to 1.5s minimum between edits, handle BadRequest silently
**Status:** ✅ FIXED

---

## Logic Bugs

### 6. Sequential Execution (Performance Bug)
**Location:** bot.py `_run_accounts_bg()` — ran accounts one by one:
```python
for acc in accounts:
    await run(acc)
    await sleep(delay)
```
With 10 accounts × 90s boost = 15 minutes blocking!

**Fix:** Parallel with semaphore:
```python
sem = Semaphore(3)
await gather(*[run_one(acc) for acc in accounts])
```
Now 10 accounts in ~3 batches = 4.5 minutes, 3x faster
**Status:** ✅ FIXED

### 7. Proxy Retirement Too Aggressive
**Location:** proxy_manager.py `report_failure()` — retired after 1 failure
**Fix:** Now after 2 consecutive failures, with success_count tracking
**Status:** ✅ FIXED

### 8. Force-Join URL Bug for -100 IDs
**Location:** force_join.py `_channel_url()`:
```python
# OLD:
return f"https://t.me/c/{cid.lstrip('-100')}"  # -100123 -> 23 (WRONG!)
# lstrip('-100') removes ANY char in set {'-','1','0','0'}, not prefix!
```
Example: `-1001234567890` → `234567890` (missing 1)

**Fix:**
```python
if cid.startswith("-100"):
    clean = cid[4:]  # Remove exactly "-100"
```
**Status:** ✅ FIXED

### 9. initData Extractor Fragile
**Location:** bot.py `extract_init_data()` — split by `#` then `parse_qs` but fragment may be double-encoded
**Fix:** Moved to `utils/extractors.py` with 3-level unquote, robust regex fallback, HTML entity decode
**Status:** ✅ FIXED

### 10. Label Validation Missing
**Location:** bot.py `/add` — allowed spaces, special chars
- `/add My Label url` → label=`My`, url=`Label url` → broken
- `/remove My Label` → only removes `My`

**Fix:** Added `is_valid_label()` → `^[a-zA-Z0-9_-]+$`, 2-32 chars
**Status:** ✅ FIXED

### 11. Max Accounts No Limit
**Risk:** User could add 1000 accounts → memory blow, API ban
**Fix:** Added `MAX_ACCOUNTS_PER_USER=20` configurable
**Status:** ✅ FIXED

### 12. Scheduler Jitter Missing (Thundering Herd)
**Location:** scheduler.py — all schedulers sleep fixed interval, all bots restart at same time → server sees spike
**Fix:** Added random jitter ±60s
**Status:** ✅ FIXED

### 13. Task Leak in AILabScheduler
**Location:** scheduler.py `_watch_loop()` — created tasks but never cancelled if account removed
**Fix:** Now tracks `want` set, cancels tasks not in want
**Status:** ✅ FIXED

### 14. Missing Error Handling in Callback
**Location:** bot.py `callback_handler()` — no try/except for `query.answer()` if query expired
**Fix:** Added error handler, safe_edit wrapper
**Status:** ✅ FIXED

### 15. Config No Validation
**Location:** config.py — BOT_TOKEN placeholder not checked, bot crashes with cryptic error
**Fix:** Added `validate()` function that checks token, thresholds, concurrency
**Status:** ✅ FIXED

### 16. Proxy Manager SOCKS Fallback
**Location:** proxy_manager.py — if `aiohttp_socks` not installed, SOCKS proxies still tried and fail
**Fix:** Added `_sanitize_proxy_url()` that filters SOCKS if `HAS_SOCKS=False`, logs warning
**Status:** ✅ FIXED

### 17. Math Challenge Solver Incomplete
**Location:** atf_api.py `_solve_math()` — only handled single op, not `(2+3)*4`
**Fix:** Safe AST eval handles complex expressions
**Status:** ✅ FIXED

### 18. Referral Bonus Silent Fail
**Location:** atf_api.py `claim_referral_bonuses()` — checked `message` contains "nothing" but server may return different case
**Fix:** Lowercase check + debug log
**Status:** ✅ FIXED (kept but improved)

---

## UX Bugs (User-Friendly Improvements)

### 19. No Main Menu
**Old:** Only commands, user must remember
**Fix:** Added ReplyKeyboardMarkup with 8 buttons + admin panel
**Status:** ✅ IMPROVED

### 20. No Confirmation on Delete
**Old:** `/remove` or button instantly deletes
**Fix:** Added confirmation dialog `del:confirm:<label>`
**Status:** ✅ IMPROVED

### 21. No Auto-Detect Help
**Old:** If user pastes URL without /add, bot says generic message
**Fix:** Now detects miner type via `auto_detect_miner()` and suggests exact command
**Status:** ✅ IMPROVED

### 22. No Export/Backup
**Old:** No way to backup accounts
**Fix:** Added `/export` command that sends JSON file, plus auto backup dir
**Status:** ✅ NEW

### 23. No Settings Command
**Old:** No way to see current config
**Fix:** Added `/settings` with all thresholds, proxy stats, miner list
**Status:** ✅ NEW

---

## Architecture Improvements (Professional)

### 24. Monolithic bot.py
**Old:** 1179 lines, all logic in one file, hard to add new miners
**Fix:** Split into:
- `miners/base.py` — abstract base class
- `miners/registry.py` — registry + auto-detect
- `miners/template.py` — copy-paste template
- `utils/` — extractors, formatters, validators
- `logger.py` — centralized logging
- `scheduler.py` — SchedulerManager

Now adding new miner = 5 minutes, just copy template.py
**Status:** ✅ REFACTORED

### 25. No Env Support
**Old:** Token hardcoded in config.py → risk committing to git
**Fix:** Added `python-dotenv` support, `.env.example`, env overrides for all settings
**Status:** ✅ IMPROVED

### 26. Logging
**Old:** BasicConfig with file + stream, no rotation → log file grows infinite
**Fix:** RotatingFileHandler 5MB x 5, structured, level from env
**Status:** ✅ IMPROVED

---

## Summary

| Category | Count |
|----------|-------|
| Critical Security | 2 |
| Race/Data Loss | 3 |
| Logic | 12 |
| UX | 5 |
| Architecture | 3 |
| **Total Fixed** | **25** |

All files now compile, type-hinted, documented, and ready for production.

**Next:** Add new miners via `miners/` folder — see `miners/template.py`
