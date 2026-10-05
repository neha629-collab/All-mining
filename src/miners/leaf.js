const { api } = require('./leaf_lib/leafapi');
const { playGame, PLAYERS } = require('./leaf_lib/gamecore');
const { extractInitData } = require('../utils/extractors');
const { leafLog: logger } = require('../logger');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

class LeafMiner {
  constructor(initDataOrAccount, proxy = null) {
    if (typeof initDataOrAccount === 'string') {
      this.initData = extractInitData(initDataOrAccount);
      this.account = { name: 'Leaf Account', initData: initDataOrAccount };
    } else if (initDataOrAccount && typeof initDataOrAccount === 'object') {
      this.account = initDataOrAccount;
      this.initData = extractInitData(initDataOrAccount.initData || initDataOrAccount.token);
    }
    this.proxy = proxy;
    this.isRunning = false;
    this.cachedState = {
      level: 1,
      leaf: 0,
      energy: 0,
      energyMax: 100,
      heart: 0,
      points: 0,
      safetyRequired: false,
      safetyPassed: false,
      status: 'idle',
      lastUpdate: Date.now()
    };
  }

  // API wrappers matching callers
  async sync() {
    return await api.sync(this.initData);
  }

  async mineStatus() {
    return await api.mineStatus(this.initData);
  }

  async mineClaim() {
    return await api.mineClaim(this.initData);
  }

  async safetyStatus() {
    return await api.safetyStatus(this.initData);
  }

  async sendSafetyCheck() {
    return await api.sendSafetyCheck(this.initData);
  }

  async verifySafetyCheck(code) {
    return await api.verifySafetyCheck(this.initData, code);
  }

  async rpc(service, method, reqType, payload, resType) {
    // If raw RPC needed
    return { ok: true };
  }

  getLiveStatus() {
    return {
      type: 'LEAF',
      name: this.account.name || this.account.label || 'Leaf Account',
      enabled: this.account.enabled !== false,
      level: this.cachedState.level || 1,
      balance: this.cachedState.leaf || 0,
      heart: this.cachedState.heart || 0,
      energy: `${this.cachedState.energy || 0}/${this.cachedState.energyMax || 100}`,
      status: this.cachedState.safetyRequired ? '🛡 Safety Check Required' : (this.cachedState.status || 'Active'),
      safetyRequired: !!this.cachedState.safetyRequired,
      safetyPassed: !!this.cachedState.safetyPassed,
      lastSync: new Date(this.cachedState.lastUpdate).toLocaleTimeString()
    };
  }

  async start() {
    this.isRunning = true;
    logger.info(`[Leaf] Started mining automation loop for account: ${this.account.name || this.account.label}`);
    this.loop();
  }

  stop() {
    this.isRunning = false;
    logger.info(`[Leaf] Stopped mining loop for account: ${this.account.name || this.account.label}`);
  }

  async loop() {
    while (this.isRunning) {
      try {
        if (!this.initData) {
          this.initData = extractInitData(this.account.initData);
        }
        if (!this.initData) {
          logger.warn(`[Leaf] Missing or invalid initData for ${this.account.name || this.account.label}`);
          await sleep(60000);
          continue;
        }

        // 1. Initial Sync & Profile Status
        await this.syncProfile();

        // Check safety check requirement
        const safeSt = await api.safetyStatus(this.initData);
        if (safeSt.ok && safeSt.data) {
          this.cachedState.safetyPassed = !!safeSt.data.passed;
          this.cachedState.safetyRequired = !safeSt.data.passed;
          if (!safeSt.data.passed) {
            logger.warn(`[Leaf] 🛡 Account ${this.account.name || this.account.label} requires Telegram Safety OTP Verification!`);
            this.cachedState.status = 'Safety Check Required';
            await sleep(30000);
            continue;
          }
        }

        // 2. Automated Free Spin
        await this.runSpin();

        // 3. Automated Ad Watching (Adsgram & Monetag)
        await this.runAds();

        // 4. Automated Quick Tasks
        await this.runQuickTasks();

        // 5. Automated Game Runs (5 Games auto-played)
        await this.runGames();

        // 6. Automated Telegram Giveaway / Star Mining
        await this.runGiveaway();

        // 7. General Tasks / Missions Completion
        await this.runTasks();

        // 8. Mining Tap & Cycle Claim
        await this.runMineCycle();

        // 9. Sync final balance
        await this.syncProfile();
        this.cachedState.status = 'Mining Active';
        this.cachedState.lastUpdate = Date.now();

      } catch (err) {
        logger.error(`[Leaf] Error in main loop for ${this.account.name || this.account.label}: ${err.message}`);
      }

      await sleep(45000 + Math.random() * 15000);
    }
  }

  async syncProfile() {
    try {
      const res = await api.sync(this.initData);
      if (res.ok && res.data && res.data.user) {
        const u = res.data.user;
        this.cachedState.leaf = u.leaf || 0;
        this.cachedState.level = u.level || 1;
        this.cachedState.energy = u.energy || 0;
        this.cachedState.energyMax = u.energy_max || 100;
        this.cachedState.heart = u.heart || 0;
        this.cachedState.lastUpdate = Date.now();
        logger.info(`[Leaf] Sync: Balance = ${this.cachedState.leaf} Leaf, Level = ${this.cachedState.level}, Energy = ${this.cachedState.energy}`);
      } else if (res.message === 'safety_check_required') {
        this.cachedState.safetyRequired = true;
      }
    } catch (e) {
      logger.warn(`[Leaf] Sync failed: ${e.message}`);
    }
  }

  async runSpin() {
    try {
      const st = await api.spinStatus(this.initData);
      if (st.ok && st.data && st.data.can_spin) {
        logger.info(`[Leaf] Executing daily/free spin for ${this.account.name || this.account.label}...`);
        await sleep(3000);
        const spinRes = await api.spin(this.initData, { ads_shown: 1, ads_clicked: 1, ads_offered: 1 });
        if (spinRes.ok) {
          logger.info(`[Leaf] Spin success! Reward: +${spinRes.data?.reward || 0} Leaf`);
        } else if (spinRes.message === 'safety_check_required') {
          this.cachedState.safetyRequired = true;
        }
      }
    } catch (e) {
      logger.warn(`[Leaf] Spin error: ${e.message}`);
    }
  }

  async runAds() {
    try {
      const types = ['ADSGRAM', 'MONETAG', 'ADEXIUM'];
      for (const t of types) {
        const adSt = await api.adViewStatus(this.initData, t);
        if (adSt.ok && adSt.data) {
          const left = Number(adSt.data.views_left || 0);
          if (left > 0) {
            logger.info(`[Leaf] Watching Ad [${t}] - ${left} views remaining for ${this.account.name || this.account.label}`);
            const start = await api.startAdView(this.initData, t);
            if (start.ok && start.data?.token) {
              const waitSec = Math.min(Math.max(Number(start.data.wait_sec || 15), 5), 30);
              logger.info(`[Leaf] Simulating ad view (${waitSec}s)...`);
              await sleep(waitSec * 1000 + 1000);
              const finish = await api.completeAdView(this.initData, start.data.token, { ads_shown: 1, ads_clicked: 1 });
              if (finish.ok) {
                logger.info(`[Leaf] Ad [${t}] rewarded +${finish.data?.reward || 0} Leaf!`);
              }
            } else if (start.message === 'safety_check_required') {
              this.cachedState.safetyRequired = true;
              break;
            }
          }
        }
        await sleep(2000);
      }
    } catch (e) {
      logger.warn(`[Leaf] Ads run error: ${e.message}`);
    }
  }

  async runQuickTasks() {
    try {
      const qs = await api.quickStatus(this.initData, []);
      if (qs.ok && qs.data && qs.data.has_task) {
        const task = qs.data.task;
        logger.info(`[Leaf] Quick Task detected: ${task.title || 'Adsgram Offer'} (Reward: ${task.reward})`);
        const offer = await api.quickOffer(this.initData, task.type || 'ADSGRAM_LINK', '');
        if (offer.ok && offer.data?.token) {
          const waitTime = Math.max(Number(task.wait_sec || 5), 5) * 1000 + 1500;
          await sleep(waitTime);
          const claim = await api.quickClaim(this.initData, offer.data.token);
          if (claim.ok) {
            logger.info(`[Leaf] Quick Task claimed! +${claim.data?.reward || task.reward} Leaf`);
          }
        }
      }
    } catch (e) {
      logger.warn(`[Leaf] Quick task error: ${e.message}`);
    }
  }

  async runGames() {
    try {
      const games = Object.keys(PLAYERS);
      for (const gid of games) {
        if (this.cachedState.safetyRequired) break;
        const gs = await api.runStatus(this.initData, gid);
        if (!gs.ok) continue;
        const used = gs.data.slots_used || 0;
        const cap = gs.data.slots_cap || 6;
        if (used < cap) {
          const nextSlot = Number(gs.data.next_slot_at_ms || 0);
          if (nextSlot > Date.now()) continue;

          logger.info(`[Leaf] Playing game ${PLAYERS[gid]?.label || gid} (${used + 1}/${cap})`);
          try {
            const playRes = await playGame(gid, api, this.initData, null, {});
            if (playRes && playRes.token) {
              await sleep(2000);
              const cl = await api.claimRun(this.initData, playRes.token, { ads_shown: 1 });
              logger.info(`[Leaf] Game ${gid} reward claimed: +${cl.data?.reward || playRes.settled?.reward || 0} Leaf`);
            }
          } catch (ge) {
            if (ge.message.includes('safety_check_required')) {
              this.cachedState.safetyRequired = true;
              break;
            }
            logger.warn(`[Leaf] Game ${gid} attempt: ${ge.message}`);
          }
          await sleep(3000);
        }
      }
    } catch (e) {
      logger.warn(`[Leaf] Games loop error: ${e.message}`);
    }
  }

  async runGiveaway() {
    try {
      const gv = await api.giveawayStatus(this.initData);
      if (gv.ok && gv.data && gv.data.has_event) {
        const step = gv.data.step || 0;
        const steps = gv.data.steps || [];
        const breakUntil = Number(gv.data.break_until_ms || 0);
        const cooldownUntil = Number(gv.data.cooldown_until_ms || 0);

        if (breakUntil <= Date.now() && cooldownUntil <= Date.now() && step < steps.length) {
          logger.info(`[Leaf] Advancing Telegram Premium Giveaway step ${step + 1}/${steps.length}...`);
          const startAd = await api.giveawayStartAd(this.initData);
          if (startAd.ok && startAd.data?.token) {
            await sleep(5000);
            const compAd = await api.giveawayCompleteAd(this.initData, startAd.data.token, { ads_shown: 1, ads_clicked: 1 });
            if (compAd.ok) {
              logger.info(`[Leaf] Giveaway step ${step + 1} completed! Points added: +${compAd.data?.points_added || 0}`);
            }
          } else if (startAd.message === 'safety_check_required') {
            this.cachedState.safetyRequired = true;
          }
        }
      }
    } catch (e) {
      logger.warn(`[Leaf] Giveaway error: ${e.message}`);
    }
  }

  async runTasks() {
    try {
      const res = await api.tasks(this.initData);
      if (res.ok && res.data && res.data.tasks) {
        for (const t of res.data.tasks) {
          if (!t.completed && (t.type === 'LINK' || t.type === 'OTHERS' || t.type === 'TELEGRAM' || t.type === 'X')) {
            logger.info(`[Leaf] Claiming task: ${t.title}`);
            const ct = await api.completeTask(this.initData, t.id);
            if (ct.ok) {
              logger.info(`[Leaf] Task "${t.title}" completed! Reward: +${t.reward || 0} Leaf`);
            } else if (ct.message === 'safety_check_required') {
              this.cachedState.safetyRequired = true;
              break;
            }
            await sleep(1500);
          }
        }
      }
    } catch (e) {
      logger.warn(`[Leaf] Tasks error: ${e.message}`);
    }
  }

  async runMineCycle() {
    try {
      const ms = await api.mineStatus(this.initData);
      if (ms.ok && ms.data) {
        if (ms.data.can_claim) {
          logger.info(`[Leaf] Mining pool ready to claim for ${this.account.name || this.account.label}! Claiming...`);
          const cl = await api.mineClaim(this.initData);
          if (cl.ok) {
            logger.info(`[Leaf] Mine claimed! +${cl.data?.reward || 0} Leaf`);
          }
        }
        if (ms.data.can_tap && ms.data.taps_left > 0) {
          logger.info(`[Leaf] Performing mine taps (${ms.data.taps_left} taps left)...`);
          const tapRes = await api.mineDo(this.initData, { count: Math.min(ms.data.taps_left, 10) });
          if (tapRes.ok) {
            logger.info(`[Leaf] Tap cycle successful, energy remaining: ${tapRes.data?.energy || 0}`);
          }
        }
      }
    } catch (e) {
      logger.warn(`[Leaf] Mine cycle error: ${e.message}`);
    }
  }
}

module.exports = LeafMiner;
