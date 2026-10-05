/**
 * All-Mining Pro — Central Configuration (100% Hardcoded, No .env needed)
 * Single port support for Jexactyl / Pterodactyl container + Cloudflare Tunnel + Telegram WebApp
 */
const path = require('path');

const config = {
  // Telegram Bot Credentials
  BOT_TOKEN: '8774301115:AAGqxk1exPmA7SfI6jXs6yGXk1in6WtEXeI',
  ADMIN_IDS: [1692540458],
  ADMIN_CONTACT: '@abdur081',
  BOT_LANG: 'Eng',
  LOG_LEVEL: 'INFO',

  // Server Host & Single Allocation Port (Jexactyl fixed port)
  WEB_HOST: '0.0.0.0',
  WEB_PORT: 30078, // Server IP: 92.118.206.4:30078
  SERVER_IP_PORT: '92.118.206.4:30078',
  WEB_ADMIN_KEY: 'admin1234',

  // Cloudflare Zero Trust Tunnel
  CLOUDFLARE_TUNNEL_TOKEN: 'eyJhIjoiNTRjMGMzZGQ0ZWI1ZjJhYzllNjY1MWNlMTQxYzBmNDYiLCJ0IjoiNTZlMjhiYWUtNTU4ZC00MDI4LTgwNDktZGVmMTBjYWQ3ZjhhIiwicyI6Ik5UWmxZbUU1TkRNdE5UVTFPQzAwTXpsaUxUa3hZemN0WmpBMk1qVTVNbUl3WkRCayJ9',
  CLOUDFLARE_DOMAIN: 'https://airdropx.eu.cc', // Telegram WebApp requires HTTPS URL

  // MongoDB Cloud Cluster
  MONGO_URL: 'mongodb+srv://n18409675_db_user:GuBsmaukRSTenDvr@cluster0.i8lsdgt.mongodb.net/?appName=Cluster0',
  MONGO_DB_NAME: 'mining_bot',

  // Force Refer / Referral Links (All Mining Platforms)
  ATF_REF_CODE: '1692540458',
  ATF_REF_LINK: 'https://t.me/ATF_AIRDROP_bot?start=1692540458',

  MRG_REF_CODE: 'ref_XYDUB621',
  MRG_REF_LINK: 'https://t.me/mrgminerbot/app?startapp=ref_XYDUB621',
  MRG_START_PARAM: 'ref_XYDUB621',

  LEAF_REF_CODE: '1692540458',
  LEAF_REF_LINK: 'https://t.me/LeafEarnBot/app?startapp=1692540458',

  REF_CODE: '1692540458',

  // Slot System
  DEFAULT_SLOT_ATF: 1,
  DEFAULT_SLOT_AILAB: 1,
  DEFAULT_SLOT_MRG: 1,
  DEFAULT_SLOT_LEAF: 1,
  DEFAULT_MAX_TOTAL: 4,
  ABSOLUTE_MAX_SLOT: 10,

  // ATF Miner Automation
  AUTO_CLAIM_THRESHOLD: 1.0,
  CLAIM_CHECK_MINUTES: 5,
  BOOST_ROUNDS: 10,
  BOOST_INTERVAL_MINUTES: 20,
  CHECK_INTERVAL_MINUTES: 30,
  TASK_DELAY_SEC: 6,

  // Powerful Free Proxy Rotation (Anti-Ban)
  USE_PROXY: true,
  PROXY_REFRESH_HOURS: 12,
  PROXY_MIN_HEALTHY: 100,
  PROXY_VALIDATE_MAX: 1500,
  PROXY_CONCURRENCY: 200,
  PROXY_TIMEOUT_SEC: 10,

  // Force Join Channels
  FORCE_JOIN_ENABLED: true,
  FORCE_JOIN_CHANNELS: [
    '@auto_miningX:Auto Mining X',
    '@ExtremePrimeX:Extreme Prime X'
  ],
  FORCE_JOIN_CACHE_TTL: 300,
  FORCE_JOIN_STRICT: true,

  // Active Miners
  AILAB_ENABLED: true,
  AILAB_AUTO_START: true,
  AILAB_KEEPALIVE_MIN: 25,

  MRG_ENABLED: true,
  MRG_MINE_THRESHOLD: 0.0001,
  MRG_CHECK_MINUTES: 30,
  MRG_TASK_CHECK_MINUTES: 30,
  MRG_AUTO_UNLOCK: true,
  MRG_MAX_UNLOCK_LEVEL: 1000,

  LEAF_ENABLED: true,

  DATA_DIR: path.join(__dirname, '../data')
};

module.exports = config;
