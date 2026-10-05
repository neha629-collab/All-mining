const axios = require('axios');
const proxyManager = require('../services/proxyManager');
const { apiLog } = require('../logger');

const API_BASE = "https://mrg.up.railway.app";

class MRGApi {
  constructor(initData, proxyUrl = null) {
    this.initData = initData;
    this.proxyUrl = proxyUrl;

    const agent = proxyManager.createAgent(proxyUrl);
    this.client = axios.create({
      baseURL: API_BASE,
      timeout: 20000,
      httpAgent: agent,
      httpsAgent: agent,
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36',
        'Origin': 'https://app.mrgtoken.xyz',
        'Referer': 'https://app.mrgtoken.xyz/',
        'Accept': 'application/json'
      }
    });
  }

  async verify(startParam = '') {
    try {
      const res = await this.client.post('/api/auth/verify', {
        initData: this.initData,
        startParam: startParam || ''
      });
      return { success: true, data: res.data };
    } catch (err) {
      return { success: false, error: err.response?.data?.message || err.message };
    }
  }

  async getMe() {
    try {
      const res = await this.client.post('/api/user/me', {
        initData: this.initData
      });
      return { success: true, data: res.data };
    } catch (err) {
      return { success: false, error: err.response?.data?.message || err.message };
    }
  }

  async claimMining() {
    try {
      const res = await this.client.post('/api/user/claim-mining', {
        initData: this.initData
      });
      return { success: true, data: res.data };
    } catch (err) {
      return { success: false, error: err.response?.data?.message || err.message };
    }
  }

  async claimCommission() {
    try {
      const res = await this.client.post('/api/user/claim-commission', {
        initData: this.initData
      });
      return { success: true, data: res.data };
    } catch (err) {
      return { success: false, error: err.response?.data?.message || err.message };
    }
  }

  async claimOneTimeBonus() {
    try {
      const res = await this.client.post('/api/user/claim-one-time-bonus', {
        initData: this.initData
      });
      return { success: true, data: res.data };
    } catch (err) {
      return { success: false, error: err.response?.data?.message || err.message };
    }
  }

  async runMissions() {
    const verified = await this.verify();
    if (!verified.success) return;

    // 1. Claim Mining
    await this.claimMining();
    // 2. Claim Commission
    await this.claimCommission();
    // 3. Claim One-Time Bonus
    await this.claimOneTimeBonus();

    // 4. Try recurring tasks
    const tasks = verified.data?.tasks || [];
    for (const t of tasks) {
      try {
        await this.client.post('/api/user/claim-task', {
          initData: this.initData,
          taskId: t.taskId
        });
      } catch (e) {}
    }
  }
}

module.exports = MRGApi;
