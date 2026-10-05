const axios = require('axios');
const proxyManager = require('../services/proxyManager');
const { apiLog } = require('../logger');

class AILabApi {
  constructor(initData, proxyUrl = null) {
    this.initData = initData;
    this.baseUrl = 'https://api.ailab.world/api';

    const agent = proxyManager.createAgent(proxyUrl);
    this.client = axios.create({
      baseURL: this.baseUrl,
      timeout: 15000,
      httpAgent: agent,
      httpsAgent: agent,
      headers: {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${initData}`
      }
    });
  }

  async getStatus() {
    try {
      const res = await this.client.get('/user/status');
      return { success: true, data: res.data };
    } catch (err) {
      return { success: false, error: err.response?.data?.message || err.message };
    }
  }

  async keepAlive() {
    try {
      const res = await this.client.post('/miner/keep-alive', {});
      return { success: true, data: res.data };
    } catch (err) {
      return { success: false, error: err.message };
    }
  }
}

module.exports = AILabApi;
