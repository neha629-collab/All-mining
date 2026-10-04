# 💎 MRG Token Integration — Added to Multi-Miner Bot v2.1

MRG bot (`app.mrgtoken.xyz`, `@mrgminerbot`) has been **ported from Node.js to Python** and integrated into your professional Telegram bot.

## ✨ What was ported

From original JS bot (Node.js):
- `api.js` → `mrg_api.py` (all endpoints with retry, proxy, auth detection)
- `econ.js` → level economics (exact replica, tested)
- `engine.js` → `MRGSession.full_cycle()` (mine + tasks + squad + boost)
- `store.js` → task cooldown state, totals, age parsing
- `bot.js` → Telegram commands `/mrg_*`

### Original JS features preserved:
| Feature | JS | Python Port |
|---------|----|-------------|
| Mine claim | `claim-mining` | ✅ `flow_mine()` |
| Tasks START→WAIT→CLAIM | `claim-task` | ✅ `flow_tasks()` with 15s/5s delays |
| Task schedule (READY/cooling/join-locked) | `tasksSchedule` | ✅ `/mrg_tasks` |
| Squad commission 10% | `claim-commission` | ✅ `flow_squad()` |
| Invite bonus +100 | `claim-one-time-bonus` | ✅ |
| Boost auto-unlock (FREE Proof-of-Holding) | `unlock-level` | ✅ `flow_boost()` |
| Level economics L1-L1000 | `econ.js` | ✅ exact replica |
| Proxy rotation | — | ✅ via ProxyManager |
| Auth/ban/maintenance detect | `isAuthError` etc | ✅ |
| Auto-retry 429/5xx | `call()` | ✅ exponential backoff |

## 🚀 New Telegram Commands

```
/mrg_add <label> <URL>  — Add MRG account (app.mrgtoken.xyz URL)
/mrg                    — Status all MRG accounts (balance, holding, level, squad, wallet, ID age)
/mrg_run                — Full cycle: squad + tasks + mine + boost (parallel)
/mrg_tasks              — Task schedule: READY/cooling/join-locked + next time
/mrg_list               — List MRG accounts + delete buttons
/mrg_remove <label>     — Remove
```

Auto-detect: Paste MRG URL → bot suggests `/mrg_add`

## 📊 MRG Economics

Level = Proof-of-Holding: `app balance + wallet balance` (unclaimed NOT counted)

```
L1 = 100 MRG → 0.2 TH/s → ~5 MRG/day
L203 = 10,000 MRG → 7.56 TH/s
L1000 = 3,875,968,992 MRG → 5000 TH/s

holdingOf(user) = inAppBalance + (tonWalletBalance if isTonConnected)
maxLevelForHolding() = binary search 1..1000
```

Bot auto-unlocks eligible levels for FREE.

## ⚙️ Settings (config.py / .env)

```python
MRG_ENABLED = True
MRG_MINE_THRESHOLD = 0.0001      # claim if unclaimed > this
MRG_CHECK_MINUTES = 30          # mine+squad+boost tick
MRG_TASK_CHECK_MINUTES = 30     # task sweep tick (catches 3h recurring)
MRG_AUTO_UNLOCK = True          # auto-unlock levels
MRG_MAX_UNLOCK_LEVEL = 1000
MRG_TASK_FIRST_DELAY = 15       # START→WAIT→CLAIM mimic
MRG_TASK_REVISIT_DELAY = 5
MRG_JOIN_RETRY_H = 24           # park join-locked tasks 24h
```

## 🔁 Scheduler

New `MRGScheduler` in `scheduler.py`:

- **Mine loop** every 30min: squad commission + bonus → mine claim → boost unlock
- **Task loop** every 30min: sweep tasks, handle cooldowns, join-locks
- Both loops parallel per account, with jitter ±60s
- Auto-marks dead initData and notifies user: `/mrg_add <label> <new URL>`

## 🛡 Safety (from original)

- Withdraw **never auto** — manual only, guarded by `allowWithdraw` (not in Telegram bot for safety)
- Wallet must be connected for mining claim (bot warns)
- Adsgram tasks auto-skipped (needs SDK)
- Join-locked tasks parked 24h + shows join link
- initData age warning after 20h but keeps using until server rejects (21h tested OK)

## 📝 Example Flow

```
/mrg_add alvee https://app.mrgtoken.xyz/#tgWebAppData=user%3D...

Bot: 🔐 Testing MRG alvee...
     ✅ alvee MRG added! 💎
     Balance 31.17 MRG, Holding 5000 → L120 (2.1 TH/s)
     Squad: 5 friends, Comm 0.5, Bonus 100
     Wallet ✅ | ID 2h old

/mrg → Status:
  alvee — bal 45.46 unclaimed 0.1 holding 7000 → L166
  Speed 5.2 TH/s ~130/day, missing 0 for next level

/mrg_run → Live progress:
  👥 Squad: friends=5 comm=0.5 bonus=100
  👥 Commission +0.5 MRG
  🎁 Bonus +100 MRG
  📋 Tasks: 6 active, 2 to attempt
  📝 START YouTube Shorts (wait 15s)...
  ⏳ CLAIM YouTube Shorts +5
  ✅ YouTube Shorts DONE +5 MRG
  ⛏ Mine claim +4.28 MRG
  🚀 Unlock L121 → 2.2 TH/s
  ✅ Done! +4.28 mined, +10 tasks
```

## 🔧 Files Added/Modified

- **New:** `mrg_api.py` (750 lines) — full API client + economics
- **New:** `miners/mrg.py` — wrapper + registry
- **Modified:** `config.py` — MRG settings
- **Modified:** `db.py` — mrg_* helpers + generic support
- **Modified:** `scheduler.py` — MRGScheduler + SchedulerManager
- **Modified:** `bot.py` — MRG commands, menu, auto-detect, admin panel
- **Modified:** `utils/extractors.py` — MRG extractor + detect
- **Modified:** `.env.example` — MRG env vars

All compiles: `python -m py_compile` OK
Miners list: `['atf', 'ailab', 'mrg']`

## 🚀 How to Use

```bash
# Add MRG account
/mrg_add myMrg https://app.mrgtoken.xyz/#tgWebAppData=user=...&hash=...

# Check status
/mrg

# Check task schedule
/mrg_tasks

# Run now
/mrg_run

# List
/mrg_list

# Remove
/mrg_remove myMrg
```

Auto-loop runs every 30min in background — no need manual `/mrg_run` after add!

## 📦 Next Steps

You can now add more miners same way:
1. Copy `miners/mrg.py` → `miners/newminer.py`
2. Implement API client like `mrg_api.py`
3. Register with `@register_miner`
4. Add commands in `bot.py` + scheduler in `scheduler.py`

See `miners/template.py` for template.
