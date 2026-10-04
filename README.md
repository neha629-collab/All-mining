# ⛏ ATF Miner Bot v2.0 — Professional Edition

**Multi-miner Telegram bot** with auto-claim, auto-boost, proxy rotation, risk monitoring, and extensible architecture for adding new mining bots easily.

![Version](https://img.shields.io/badge/version-2.0--PRO-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-green)
![Miners](https://img.shields.io/badge/miners-ATF%20%7C%20AI%20Lab%20%7C%20Custom-orange)

---

## 🚀 What's New in v2.0-PRO

### Bug Fixes from v1
- ❌ **Removed dangerous `eval()`** in math solver → safe AST parser
- ❌ Fixed sequential execution (now parallel with semaphore)
- ❌ Fixed proxy fail-open logic
- ❌ Fixed initData extractor edge cases (double encoding, HTML entities)
- ❌ Fixed race conditions in DB (atomic writes + locks)
- ❌ Fixed markdown injection in messages
- ❌ Fixed message edit rate limiting
- ❌ Fixed force-join URL for -100 IDs

### Professional Improvements
- ✅ **Modular architecture** — `miners/base.py` makes adding new miners trivial
- ✅ **User-friendly onboarding** — menu keyboard, auto-detect, step-by-step
- ✅ **Parallel execution** — 3 concurrent accounts with rate limiting
- ✅ **Smart proxy manager** — health scoring, circuit breaker, sticky IP
- ✅ **Unified scheduler manager** — jitter, graceful shutdown, health checks
- ✅ **Professional logging** — rotating files, structured logs
- ✅ **Validation** — label validation, initData validation, config validation
- ✅ **Export/backup** — `/export` command, auto backup on corruption
- ✅ **Confirmation dialogs** — delete with confirmation
- ✅ **Caching** — force-join cache 5min TTL, parallel checks

---

## 📦 Features

| Feature | ATF Miner | AI Lab | Custom Miners |
|---------|-----------|--------|---------------|
| Auto Mining | ✅ | ✅ | ✅ (via base) |
| Auto Claim | ✅ Every 5min | — | ✅ |
| Auto Boost | ✅ 1.61x speed | — | ✅ |
| Auto Tasks | ✅ | ✅ | ✅ |
| Proxy Rotation | ✅ Sticky IP | ✅ | ✅ |
| Risk Monitor | ✅ | — | — |
| Zero-downtime Watchdog | — | ✅ | — |
| Force Join | ✅ | ✅ | ✅ |
| Admin Panel | ✅ | ✅ | ✅ |

---

## 🏗 Architecture

```
mining-bot/
├── bot.py              # Main Telegram bot (v2.0)
├── config.py           # Env-aware config with validation
├── db.py               # Atomic JSON DB with backup
├── proxy_manager.py    # Proxy rotation v2.0
├── force_join.py       # Force join with caching
├── atf_api.py          # ATF API client (safe math)
├── ailab_api.py        # AI Lab client
├── scheduler.py        # Unified scheduler manager
├── logger.py           # Rotating logger
├── miners/
│   ├── base.py         # Abstract base for new miners ⭐
│   ├── registry.py     # Miner registry
│   ├── template.py     # Template for new miners ⭐
│   └── __init__.py
├── utils/
│   ├── extractors.py   # Robust initData parsing
│   ├── formatters.py   # Human readable
│   └── validators.py   # Input validation
├── data/               # Accounts, proxies, backups
├── logs/               # Rotating logs
├── requirements.txt
├── .env.example
└── README.md
```

### How to Add a New Mining Bot (5 minutes)

1. **Copy template:**
   ```bash
   cp miners/template.py miners/hamster.py
   ```

2. **Edit `hamster.py`:**
   ```python
   @register_miner
   class HamsterMiner(BaseMiner):
       miner_id = "hamster"
       display_name = "Hamster Kombat"
       
       async def login(self): ...
       async def get_status(self): ...
       async def full_cycle(self, config, step_cb=None): ...
   ```

3. **Done!** Bot auto-detects it. Add commands in `bot.py` if needed:
   ```python
   # In bot.py, add handlers similar to ATF/AI Lab
   ```

See `miners/template.py` for full example.

---

## ⚡ Quick Setup

### 1. Install
```bash
git clone <your-repo>
cd mining-bot
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env and set BOT_TOKEN
nano .env
```

Or edit `config.py` directly:
```python
BOT_TOKEN = "123456:ABC..."
ADMIN_IDS = [your_telegram_id]
```

### 3. Run
```bash
python bot.py
```

Background:
```bash
nohup python bot.py > logs/nohup.log 2>&1 &
# or
screen -S miner
python bot.py
```

---

## 🤖 Bot Commands

### ATF Miner
| Command | Description |
|---------|-------------|
| `/add <label> <URL>` | Add ATF account |
| `/run` | Run full cycle now (all accounts, parallel) |
| `/stop` | Stop running cycle |
| `/status` | Balance, level, rate |
| `/list` | List accounts with Run/Remove buttons |
| `/remove <label>` | Remove account |
| `/risk` | Risk score + flags |
| `/proxy` | Proxy pool & your IPs |

### AI Lab
| Command | Description |
|---------|-------------|
| `/ailab_add <label> <URL>` | Add AI Lab account |
| `/ailab` | Status of all AI Lab accounts |
| `/ailab_run` | Run cycle now |
| `/ailab_list` | List + delete buttons |
| `/ailab_remove <label>` | Remove |

### General
| Command | Description |
|---------|-------------|
| `/start` | Main menu |
| `/help` | Help |
| `/settings` | Settings & info |
| `/export` | Backup your data |

### Admin
| Command | Description |
|---------|-------------|
| `/admin` | Admin panel |
| `/broadcast <msg>` | Message all users |
| `/purge <user_id>` | Delete user |

---

## 🔧 Configuration

All settings in `config.py` can be overridden via `.env`:

```env
BOT_TOKEN=...
ADMIN_IDS=123,456
REF_CODE=1692540458
AUTO_CLAIM_THRESHOLD=1.0
CLAIM_CHECK_MINUTES=5
BOOST_ROUNDS=10
BOOST_INTERVAL_MINUTES=20
USE_PROXY=True
FORCE_JOIN_ENABLED=True
AILAB_ENABLED=True
MAX_ACCOUNTS_PER_USER=20
```

---

## 🌐 Proxy System v2.0

**Why?** Server flags `same_exact_ip_2_accounts` → risk score ↑

**Solution:**
- Each account gets **sticky IP** (consistent, not rotating per request)
- 12 free sources, refreshed daily
- Validated against **real ATF endpoint** (not httpbin)
- Auto-rotate on failure, direct fallback
- Health scoring, circuit breaker

**Stats:**
- ~11% of public proxies work (SOCKS5 best)
- Live: 91 healthy / 700 tested in 33s

`/proxy` to see your pool.

---

## 🛡 Risk Monitoring

`/risk` decodes server anti-bot flags:

```
🟠 Risk Score: 72/100 — HIGH
Flags:
  🕐 Account younger than 7 days
  🌐 2 accounts share this exact IP
```

| Score | Level |
|-------|-------|
| 0-19 | ✅ SAFE |
| 20-39 | 🟢 LOW |
| 40-59 | 🟡 MEDIUM |
| 60-79 | 🟠 HIGH |
| 80+ | 🔴 CRITICAL |

---

## 🧪 AI Lab Zero-Downtime Watchdog

Mining runs in ~8h sessions. Old bot polled every 10min → up to 10min gap.

**New:** Reads `time_left` from server and sleeps until exactly that moment + 30s grace:

```
session ends ──► +30s ──► auto restart
```

- Each account has its own watchdog task (parallel)
- Keep-alive ping every 25min → session lasts days
- Silent re-login on 401
- Only asks for new link when initData truly expired

---

## 🔒 Force Join

Users must join channels before using bot.

- Bot must be **ADMIN** in each channel
- Fail-open if not admin (warns in logs, doesn't lock users out)
- Caching 5min TTL, parallel checks
- Admins bypass

Set in `config.py`:
```python
FORCE_JOIN_CHANNELS = [
    ("@auto_miningX", "Auto Mining X"),
    ("@ExtremePrimeX", "Extreme Prime X"),
]
```

---

## 📊 Mining Economics (ATF)

Pool balance → Level → Rate (snowball effect)

| Pool | Level | Rate | Daily |
|------|-------|------|-------|
| 0 ATF | 1 | 0.06/hr | 1.5 |
| 354 ATF | 51 | 1.35/hr | 32 |
| 436 ATF | 60 | 1.57/hr | 37 |
| 1204 ATF | 100 | 3.32/hr | 79 (+181%) |
| 4287 ATF | 150 | 8.15/hr | 195 (+505%) |

**Strategy:** Claim often (every 1 ATF) → pool grows → level up → higher rate!

Bot does this automatically every 5min.

---

## 🐛 Bug Fixes Detailed

### Critical Security
- **eval() removal:** Old code used `eval()` on math challenge → code injection possible. Now uses `ast` safe parser.

### Race Conditions
- **DB:** Old used `threading.Lock` but async code could interleave → now `RLock` + atomic write (tmp + replace) + backup on corruption
- **Progress:** Old edited message without rate limit → Telegram 429. Now 1.5s throttle

### Logic
- **Sequential run:** Old ran accounts one by one with delay → slow. New uses `asyncio.gather` + semaphore(3) → parallel, fast
- **Proxy:** Old retired proxy after 1 fail → too aggressive. New after 2 fails + health scoring
- **Force-join:** Old URL for -100 IDs broken (`https://t.me/c/-100...`). Fixed to strip -100

### UX
- **No validation:** Old allowed any label (including spaces → breaks /remove). New validates `^[a-zA-Z0-9_-]+$`, 2-32 chars
- **No confirmation:** Delete instantly → accidental loss. New asks confirmation
- **No menu:** Only commands. New adds ReplyKeyboardMarkup menu

---

## 🔮 Roadmap for New Miners

The `miners/` system is ready. To add:

- [ ] Hamster Kombat
- [ ] Blum
- [ ] Notcoin
- [ ] TapSwap
- [ ] Yescoin

Just create file in `miners/` and implement 3 methods. See `miners/template.py`.

Future: Generic `/miner_add <miner_id> <label> <URL>` command that works for any registered miner.

---

## 📝 Logs

- `logs/bot.log` — rotating, 5MB x 5 files
- `data/proxies.json` — proxy pool
- `data/accounts.json` — ATF accounts
- `data/ailab.json` — AI Lab accounts
- `data/backups/` — auto backups on corruption

---

## ⚠️ Notes

- `initData` expires ~24h → refresh via `/add` again
- Proxy free sources are unreliable — bot falls back to DIRECT
- Risk score is server-side — bot only reports, can't lower it (except using 1 IP per account)
- Level-up is from pool balance — no TON purchase needed

---

## 👨‍💻 Developer

- Original: ATF Miner Bot v1
- Professional Rewrite: v2.0-PRO
- Extensible Miner Architecture: `miners/base.py`

**Support:** @auto_miningX | @ExtremePrimeX

---

## 📄 License

MIT — Use freely, but keep referral code if you like the bot ❤️

`REF_CODE = "1692540458"` — supports developer
