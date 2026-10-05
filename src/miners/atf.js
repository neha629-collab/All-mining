const axios = require('axios');
const proxyManager = require('../services/proxyManager');
const { apiLog } = require('../logger');

const BASE_URL = "https://atfminers.asloni.online/miner/index.php";

const TASKS = [
  { id: 'telegram_react_latest', title: 'React to TG post', minSec: 20 },
  { id: 'website_visit', title: 'Visit atftoken.com', minSec: 15 },
  { id: 'youtube_like_comment', title: 'YouTube Like & Comment', minSec: 30 },
  { id: 'twitter_retweet', title: 'X Retweet', minSec: 30 }
];

class ATFApi {
  constructor(initData, proxyUrl = null) {
    this.initData = initData;
    this.proxyUrl = proxyUrl;
    
    this.tgId = 0;
    this.username = '';
    try {
      const sp = new URLSearchParams(initData);
      const userStr = sp.get('user');
      if (userStr) {
        const u = JSON.parse(userStr);
        this.tgId = u.id;
        this.username = u.username || '';
      }
    } catch (e) {}

    const agent = proxyManager.createAgent(proxyUrl);
    this.client = axios.create({
      timeout: 20000,
      httpAgent: agent,
      httpsAgent: agent,
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36 Telegram-Android/11.0.0',
        'Origin': 'https://atfminers.asloni.online',
        'Referer': 'https://atfminers.asloni.online/miner/index.html',
        'X-Telegram-Init-Data': initData
      }
    });
    this.sessionToken = '';
  }

  async postAction(action, extra = {}) {
    const url = `${BASE_URL}?action=${action}&t=${Date.now()}`;
    const body = {
      initData: this.initData,
      request_id: 'req_' + Math.random().toString(36).substring(2, 10),
      device_id: `dev-${this.tgId}`,
      ...extra
    };

    const headers = {};
    if (this.sessionToken) {
      headers['X-ATF-TMA-Session'] = this.sessionToken;
    }

    try {
      const res = await this.client.post(url, body, { headers });
      return res.data;
    } catch (err) {
      return { status: 'error', message: err.response?.data?.message || err.message };
    }
  }

  async login(refCode = '') {
    const payload = { tg_id: this.tgId, username: this.username };
    if (refCode) payload.ref_code = String(refCode);

    const d = await this.postAction('login', payload);
    if (d && d.status === 'success') {
      if (d.tma_session_token) this.sessionToken = d.tma_session_token;
      return { success: true, data: d };
    }
    return { success: false, error: d?.message || 'Login failed' };
  }

  async sync() {
    return await this.postAction('sync_pool', { tg_id: this.tgId });
  }

  async claim() {
    if (!this.sessionToken) await this.login();
    const syncRes = await this.sync();
    const pending = syncRes?.user?.pending_reward || 0;

    const res = await this.postAction('claim', {
      tg_id: this.tgId,
      claim_preview: Number(pending)
    });

    if (res && res.status === 'success') {
      return { success: true, data: res };
    }
    return { success: false, error: res?.message || 'Claim failed' };
  }

  async boost() {
    if (!this.sessionToken) await this.login();
    const res = await this.postAction('activate_boost', { tg_id: this.tgId });
    if (res && res.status === 'success') {
      return { success: true, data: res };
    }
    return { success: false, error: res?.message || 'Boost failed' };
  }

  async runMissions() {
    if (!this.sessionToken) await this.login();
    // Claim team wallet
    await this.postAction('claim_team_wallet', { tg_id: this.tgId }).catch(() => null);
    await this.postAction('claim_referrals', { tg_id: this.tgId }).catch(() => null);

    // Auto cycle through tasks
    for (const t of TASKS) {
      try {
        await this.postAction('start_task', {
          tg_id: t.id,
          task_id: t.id,
          client_started_at: Date.now()
        });
        await new Promise(r => setTimeout(r, 2000));
        await this.postAction('claim_task', { tg_id: this.tgId, task_id: t.id });
      } catch (e) {}
    }
  }
}

module.exports = ATFApi;
