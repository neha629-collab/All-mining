const db = require('../db');
const ATFApi = require('../miners/atf');
const MRGApi = require('../miners/mrg');
const AILabApi = require('../miners/ailab');
const LeafApi = require('../miners/leaf');
const proxyManager = require('./proxyManager');
const otpManager = require('./otpNotifier');
const { schedLog } = require('../logger');

class Scheduler {
  constructor() {
    this.intervalHandle = null;
    this.isRunning = false;
    this.stats = {
      totalRuns: 0,
      successfulClaims: 0,
      errors: 0,
      lastRunAt: null,
      activeAccounts: { atf: 0, mrg: 0, ailab: 0, leaf: 0 }
    };
  }

  start() {
    if (this.isRunning) return;
    this.isRunning = true;
    schedLog.info('⚡ High-performance mining scheduler started.');
    
    // Run loop every 2 minutes
    this.intervalHandle = setInterval(() => this.runCycle(), 2 * 60 * 1000);
    setTimeout(() => this.runCycle(), 2000);
  }

  async runCycle() {
    schedLog.info('Executing complete mining cycle across all platforms...');
    this.stats.totalRuns++;
    this.stats.lastRunAt = new Date().toISOString();

    try {
      await Promise.allSettled([
        this.processATF(),
        this.processMRG(),
        this.processAILab(),
        this.processLeaf()
      ]);
    } catch (err) {
      this.stats.errors++;
      schedLog.error('Error in scheduler cycle', err);
    }
  }

  async processATF() {
    const accounts = await db.getAccounts('atf');
    this.stats.activeAccounts.atf = accounts.length;

    for (const acc of accounts) {
      if (acc.active === false) continue;
      const proxy = proxyManager.getStickyProxy(`atf_${acc.tgId}_${acc.label}`);
      try {
        const client = new ATFApi(acc.initData, proxy);
        // 1. Claim Mined
        const claimRes = await client.claim();
        if (claimRes.success) {
          this.stats.successfulClaims++;
          schedLog.info(`[ATF] Claim success for ${acc.label} (${acc.tgId})`);
        }
        // 2. Run Boost
        await client.boost();
        // 3. Run Missions / Team Wallet Claims
        await client.runMissions();
      } catch (e) {
        this.stats.errors++;
        schedLog.warn(`[ATF] Error for ${acc.label}: ${e.message}`);
      }
    }
  }

  async processMRG() {
    const accounts = await db.getAccounts('mrg');
    this.stats.activeAccounts.mrg = accounts.length;

    for (const acc of accounts) {
      if (acc.active === false) continue;
      const proxy = proxyManager.getStickyProxy(`mrg_${acc.tgId}_${acc.label}`);
      try {
        const client = new MRGApi(acc.initData, proxy);
        // Run full mission + claim suite
        await client.runMissions();
        this.stats.successfulClaims++;
      } catch (e) {
        this.stats.errors++;
        schedLog.warn(`[MRG] Error for ${acc.label}: ${e.message}`);
      }
    }
  }

  async processAILab() {
    const accounts = await db.getAccounts('ailab');
    this.stats.activeAccounts.ailab = accounts.length;

    for (const acc of accounts) {
      if (acc.active === false) continue;
      const proxy = proxyManager.getStickyProxy(`ailab_${acc.tgId}_${acc.label}`);
      try {
        const client = new AILabApi(acc.initData, proxy);
        await client.keepAlive();
      } catch (e) {
        this.stats.errors++;
        schedLog.warn(`[AILab] Error for ${acc.label}: ${e.message}`);
      }
    }
  }

  async processLeaf() {
    const accounts = await db.getAccounts('leaf');
    this.stats.activeAccounts.leaf = accounts.length;

    for (const acc of accounts) {
      if (acc.active === false) continue;
      const proxy = proxyManager.getStickyProxy(`leaf_${acc.tgId}_${acc.label}`);
      try {
        const client = new LeafApi(acc.initData, proxy);
        
        // 1. Safety check check
        const safety = await client.safetyStatus().catch(() => null);
        if (safety && safety.ok && safety.data) {
          const s = safety.data;
          if (!s.passed && (s.sent || s.code_left_sec > 0)) {
            schedLog.warn(`[Leaf] Safety check required for ${acc.label} (${acc.tgId})`);
            await otpManager.notifyOtpRequired('leaf', acc.tgId, acc.label, acc.initData, s.code_left_sec || 300);
            continue;
          }
        }

        // 2. Sync
        await client.sync().catch(() => null);

        // 3. Mine tap with ads reporting
        await client.rpc('leaf.v1.MineService', 'Mine', 'leaf.v1.MineRequest', {
          ads_shown: 1,
          ads_clicked: 1,
          ads_offered: 1
        }, 'leaf.v1.MineStatusResponse').catch(() => null);

        // 4. Claim if mined threshold reached
        const status = await client.mineStatus().catch(() => null);
        if (status && status.ok && status.data && status.data.mined > 50) {
          const claimRes = await client.mineClaim().catch(() => null);
          if (claimRes && claimRes.ok) {
            this.stats.successfulClaims++;
            schedLog.info(`[Leaf] Mined claim success for ${acc.label} (${acc.tgId})`);
          }
        }
      } catch (e) {
        this.stats.errors++;
        schedLog.warn(`[Leaf] Error for ${acc.label}: ${e.message}`);
      }
    }
  }

  getLiveStats() {
    return {
      ...this.stats,
      isSchedulerRunning: this.isRunning
    };
  }

  stop() {
    if (this.intervalHandle) clearInterval(this.intervalHandle);
    this.isRunning = false;
  }
}

module.exports = new Scheduler();
