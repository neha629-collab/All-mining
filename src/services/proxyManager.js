const axios = require('axios');
const fs = require('fs');
const path = require('path');
const { SocksProxyAgent } = require('socks-proxy-agent');
const { HttpsProxyAgent } = require('https-proxy-agent');
const config = require('../config');
const { createLogger } = require('../logger');

const log = createLogger('PROXY');

// 25+ High Quality Public Proxy Sources (HTTP, SOCKS4, SOCKS5)
const PROXY_SOURCES = [
  // SOCKS5 (Best for bypassing bot IP ban restrictions)
  { url: 'https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=socks5&proxy_format=ipport&format=text', type: 'socks5' },
  { url: 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt', type: 'socks5' },
  { url: 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt', type: 'socks5' },
  { url: 'https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt', type: 'socks5' },
  { url: 'https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt', type: 'socks5' },
  { url: 'https://api.openproxylist.xyz/socks5.txt', type: 'socks5' },
  { url: 'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt', type: 'socks5' },
  
  // SOCKS4
  { url: 'https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=socks4&proxy_format=ipport&format=text', type: 'socks4' },
  { url: 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt', type: 'socks4' },
  { url: 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt', type: 'socks4' },
  { url: 'https://api.openproxylist.xyz/socks4.txt', type: 'socks4' },

  // HTTP / HTTPS
  { url: 'https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&proxy_format=ipport&format=text', type: 'http' },
  { url: 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt', type: 'http' },
  { url: 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt', type: 'http' },
  { url: 'https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt', type: 'http' },
  { url: 'https://api.openproxylist.xyz/http.txt', type: 'http' },
  { url: 'https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt', type: 'http' },
  { url: 'https://raw.githubusercontent.com/proxy4parsing/proxy-list/main/http.txt', type: 'http' }
];

class ProxyManager {
  constructor() {
    this.enabled = config.USE_PROXY;
    this.healthyProxies = [];
    this.stickyMap = new Map(); // accountKey -> proxy
    this.stateFile = path.join(config.DATA_DIR, 'proxies.json');
    this.lastRefresh = 0;
    this.isValidating = false;
  }

  async init() {
    if (!this.enabled) {
      log.info('Proxy manager is disabled in config.');
      return;
    }
    this._loadSaved();
    if (this.healthyProxies.length < config.PROXY_MIN_HEALTHY) {
      this.refreshProxies().catch(e => log.error('Initial proxy refresh error', e.message));
    }
    // Schedule periodic refresh
    setInterval(() => {
      this.refreshProxies().catch(e => log.error('Periodic proxy refresh error', e.message));
    }, config.PROXY_REFRESH_HOURS * 3600 * 1000);
  }

  _loadSaved() {
    try {
      if (fs.existsSync(this.stateFile)) {
        const raw = fs.readFileSync(this.stateFile, 'utf8');
        const data = JSON.parse(raw);
        this.healthyProxies = data.healthy || [];
        log.info(`Loaded ${this.healthyProxies.length} healthy proxies from disk cache.`);
      }
    } catch (e) {
      this.healthyProxies = [];
    }
  }

  _saveState() {
    try {
      fs.writeFileSync(this.stateFile, JSON.stringify({
        lastRefresh: this.lastRefresh,
        count: this.healthyProxies.length,
        healthy: this.healthyProxies
      }, null, 2), 'utf8');
    } catch (e) {
      log.error('Failed to save proxy state', e.message);
    }
  }

  async fetchAllSources() {
    log.info(`Fetching proxies from ${PROXY_SOURCES.length} free providers...`);
    const rawList = new Set();

    await Promise.allSettled(PROXY_SOURCES.map(async (src) => {
      try {
        const res = await axios.get(src.url, { timeout: 10000 });
        const lines = String(res.data).split(/\r?\n/);
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed && trimmed.includes(':') && !trimmed.startsWith('#')) {
            const proto = src.type || (trimmed.startsWith('socks') ? 'socks5' : 'http');
            const cleanUrl = trimmed.includes('://') ? trimmed : `${proto}://${trimmed}`;
            rawList.add(cleanUrl);
          }
        }
      } catch (err) {
        // Ignore single source failures
      }
    }));

    log.info(`Collected ${rawList.size} candidate proxies. Starting validation...`);
    return Array.from(rawList);
  }

  async validateProxy(proxyUrl) {
    let agent;
    try {
      if (proxyUrl.startsWith('socks')) {
        agent = new SocksProxyAgent(proxyUrl, { timeout: config.PROXY_TIMEOUT_SEC * 1000 });
      } else {
        agent = new HttpsProxyAgent(proxyUrl, { timeout: config.PROXY_TIMEOUT_SEC * 1000 });
      }

      const start = Date.now();
      // Test target: lightweight API response
      const res = await axios.get('https://api.ipify.org?format=json', {
        httpAgent: agent,
        httpsAgent: agent,
        timeout: config.PROXY_TIMEOUT_SEC * 1000
      });

      if (res.status === 200 && res.data?.ip) {
        return {
          url: proxyUrl,
          latency: Date.now() - start,
          ip: res.data.ip,
          checkedAt: new Date().toISOString()
        };
      }
    } catch (err) {
      return null;
    }
    return null;
  }

  async refreshProxies() {
    if (this.isValidating) return;
    this.isValidating = true;
    try {
      const candidates = await this.fetchAllSources();
      const limited = candidates.slice(0, config.PROXY_VALIDATE_MAX);
      const concurrency = config.PROXY_CONCURRENCY;
      const testedHealthy = [];

      for (let i = 0; i < limited.length; i += concurrency) {
        const chunk = limited.slice(i, i + concurrency);
        const results = await Promise.all(chunk.map(p => this.validateProxy(p)));
        for (const r of results) {
          if (r) testedHealthy.push(r);
        }
      }

      // Sort by fastest latency
      testedHealthy.sort((a, b) => a.latency - b.latency);
      this.healthyProxies = testedHealthy;
      this.lastRefresh = Date.now();
      this._saveState();
      log.info(`✅ Proxy validation finished. Total Healthy & Active: ${testedHealthy.length}`);
    } catch (err) {
      log.error('Proxy refresh failed', err);
    } finally {
      this.isValidating = false;
    }
  }

  /**
   * Sticky IP Allocation: Assigns each account a consistent unique proxy
   * to bypass multi-account same-IP ban restrictions!
   */
  getStickyProxy(accountKey) {
    if (!this.enabled || !this.healthyProxies.length) return null;

    if (this.stickyMap.has(accountKey)) {
      const existing = this.stickyMap.get(accountKey);
      if (this.healthyProxies.some(p => p.url === existing)) {
        return existing;
      }
    }

    // Pick an unused or random proxy from top healthy pool
    const topPool = this.healthyProxies.slice(0, 100);
    const chosen = topPool[Math.floor(Math.random() * topPool.length)].url;
    this.stickyMap.set(accountKey, chosen);
    return chosen;
  }

  createAgent(proxyUrl) {
    if (!proxyUrl) return null;
    try {
      if (proxyUrl.startsWith('socks')) {
        return new SocksProxyAgent(proxyUrl, { timeout: 15000 });
      } else {
        return new HttpsProxyAgent(proxyUrl, { timeout: 15000 });
      }
    } catch (e) {
      return null;
    }
  }

  getStatus() {
    return {
      enabled: this.enabled,
      healthyCount: this.healthyProxies.length,
      lastRefresh: this.lastRefresh ? new Date(this.lastRefresh).toLocaleString() : 'Never',
      isValidating: this.isValidating,
      topProxies: this.healthyProxies.slice(0, 5)
    };
  }
}

module.exports = new ProxyManager();
