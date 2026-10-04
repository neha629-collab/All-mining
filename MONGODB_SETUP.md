# MongoDB Setup Guide — v4.0 MONGO

## 1. Create Free MongoDB Atlas Cluster

1. Go to https://cloud.mongodb.com → Sign up / Login
2. Create new Project → Build a Database → Free M0
3. Choose region closest to your bot server (e.g. Mumbai, Singapore)
4. Create User: username + password (save it!)
5. Network Access → Add IP Address → Allow All `0.0.0.0/0` (or your server IP)
6. Database → Connect → Drivers → Copy connection string:
   ```
   mongodb+srv://YOUR_USERNAME:YOUR_PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```

## 2. Add to Bot .env

Open `.env` file:

```env
BOT_TOKEN=123456:ABC...
ADMIN_IDS=123456789
MONGO_URL=mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGO_DB_NAME=mining_bot

# Force Refer — Your Links (Already set)
ATF_REF_CODE=1692540458
ATF_REF_LINK=https://t.me/ATF_AIRDROP_bot?start=1692540458
MRG_REF_CODE=ref_XYDUB621
MRG_REF_LINK=https://t.me/mrgminerbot/app?startapp=ref_XYDUB621
MRG_START_PARAM=ref_XYDUB621
```

## 3. Install & Run

```bash
pip install -r requirements.txt
python bot.py
```

Bot will show:
```
✅ MongoDB connected: MongoDB @ cluster0.xxxxx.mongodb.net / mining_bot
🚀 Mining Bot v4.0-MONGO — MONGO + FORCE REFER
   DB: MongoDB @ cluster0.xxxxx.mongodb.net / mining_bot
   ATF Ref: 1692540458 → https://t.me/ATF_AIRDROP_bot?start=1692540458
   MRG Ref: ref_XYDUB621 → https://t.me/mrgminerbot/app?startapp=ref_XYDUB621
```

## 4. How It Works

- **If MONGO_URL set:** All accounts, slots, etc saved in MongoDB → persistent, scalable, no file loss on restart
- **If MONGO_URL empty:** Falls back to JSON files in `data/` folder (old behavior)

Collections auto-created:
- `atf_accounts` — ATF miner accounts
- `ailab_accounts` — AI Lab accounts
- `mrg_accounts` — MRG token accounts
- `generic_accounts` — Other miners
- `slots` — Per-user slot limits

## 5. Force Refer System

### ATF:
- Your link: `https://t.me/ATF_AIRDROP_bot?start=1692540458`
- Code: `1692540458`
- When user adds ATF account, bot logs in with `ref_code=1692540458`
- You get referral bonus automatically!

### MRG:
- Your link: `https://t.me/mrgminerbot/app?startapp=ref_XYDUB621`
- Code: `ref_XYDUB621`
- When user adds MRG account, bot verifies with `startParam=ref_XYDUB621`
- You get referral bonus!

All new users = your referrals! No extra code needed.

## 6. Admin Panel — MongoDB Stats

`/admin` → `🗄️ MongoDB Stats` button shows:
- Connected or fallback reason
- Count per collection
- DB name and host

## 7. Migration from JSON

If you had old JSON data in `data/` and now switching to MongoDB:
- Old JSON stays in `data/` folder
- New accounts will go to MongoDB
- To migrate old data, you can run bot with both, or manually import

For auto migration, you can write a small script or ask admin to re-add accounts (they just need to paste token again).

## 8. Troubleshooting

- `MongoDB connection failed` → Check password (URL encode if contains special chars), IP whitelist, network
- `No MONGO_URL set — using JSON` → Normal if you didn't set URL, bot still works with JSON
- Atlas free tier sleeps? No, M0 is always on but has 512MB limit — enough for thousands of accounts

Enjoy! 🚀
