# ⛏️ All-Mining Pro (Single-Port Jexactyl + Telegram WebApp + Cloudflare Tunnel)

A pure **Node.js** multi-mining automation bot designed specifically for containerized hosting environments like **Jexactyl / Pterodactyl** using a single fixed port with **Cloudflare Zero Trust Tunnel** and direct **Telegram WebApp** auto-loading!

---

## 🚀 What Was Updated & Configured:

1. **Telegram WebApp Auto-Account Detection:**
   - When a user taps **`🚀 Open Mining WebApp`** inside Telegram, the WebApp SDK (`window.Telegram.WebApp.initDataUnsafe.user`) automatically detects their Telegram User ID and name.
   - The dashboard dynamically filters and loads **only that specific user's connected accounts, slot counts, and pending OTPs**!
   - Responsive mobile-first UI with dark theme matching Telegram's native styling.

2. **Hardcoded Settings (No .env file needed):**
   - Config file `src/config.js` now holds all server credentials, database URI, and tokens directly.

3. **Single Port Hosting (Jexactyl Allocation: `92.118.206.4:30078`):**
   - Fixed listening port: **`30078`**
   - Host: **`0.0.0.0`**
   - Cloudflare Tunnel forwards public requests directly to this single port.

4. **Cloudflare Zero Trust Tunnel (Auto-Active):**
   - **Tunnel Token:** `eyJhIjoiNTRjMGMzZGQ0Z...`
   - **Domain:** `https://airdropx.eu.cc`
   - Zero terminal commands needed: `cloudflared` is auto-downloaded on boot and connects instantly to Cloudflare's Edge network (`sea01`, `sea08`, `sea09`, `sea11`).

---

## 📱 How Users Experience the WebApp in Telegram:

1. User opens your bot in Telegram and sends `/start`.
2. A large button appears: **`🚀 Open Mining WebApp`**.
3. Upon clicking:
   - The WebApp opens inside Telegram with HTTPS via `https://airdropx.eu.cc`.
   - The user's profile and accounts load automatically (no login needed).
   - If an account hits a Leaf Safety Check, an OTP box appears directly on top for 1-tap verification.

---

## 🛠️ Deploying to Jexactyl:

- Simply upload `/home/user/all-mining-js` contents.
- Start Command:
  ```bash
  node index.js
  ```
Everything runs together on single port `30078`: Telegram Bot + WebApp Server + Scheduler + Proxy Rotation + Cloudflare Tunnel.
