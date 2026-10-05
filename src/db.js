const { MongoClient } = require('mongodb');
const fs = require('fs');
const path = require('path');
const config = require('./config');
const { log } = require('./logger');

class Database {
  constructor() {
    this.client = null;
    this.db = null;
    this.isMongo = false;
    this.localPath = path.join(config.DATA_DIR, 'local_db.json');
    this.localData = {
      users: {},
      atf_accounts: {},
      ailab_accounts: {},
      mrg_accounts: {},
      leaf_accounts: {}
    };
  }

  async connect() {
    if (!fs.existsSync(config.DATA_DIR)) {
      fs.mkdirSync(config.DATA_DIR, { recursive: true });
    }

    if (config.MONGO_URL) {
      try {
        log.info('Connecting to MongoDB Cloud Cluster...');
        this.client = new MongoClient(config.MONGO_URL, {
          serverSelectionTimeoutMS: 5000
        });
        await this.client.connect();
        this.db = this.client.db(config.MONGO_DB_NAME);
        this.isMongo = true;
        log.info('✅ MongoDB connected successfully');
        return;
      } catch (err) {
        log.warn(`MongoDB connection failed: ${err.message}. Using Local JSON Storage Engine.`);
      }
    }

    this._loadLocal();
    log.info('Using Local JSON Storage Engine.');
  }

  _loadLocal() {
    if (fs.existsSync(this.localPath)) {
      try {
        this.localData = JSON.parse(fs.readFileSync(this.localPath, 'utf8'));
      } catch (e) {
        log.error('Corrupted local DB, resetting.');
      }
    }
  }

  _saveLocal() {
    try {
      const tempPath = `${this.localPath}.tmp`;
      fs.writeFileSync(tempPath, JSON.stringify(this.localData, null, 2), 'utf8');
      fs.renameSync(tempPath, this.localPath);
    } catch (e) {
      log.error('Failed to save local DB', e);
    }
  }

  // --- Users ---
  async getAllUsers() {
    if (this.isMongo) {
      return await this.db.collection('users').find({}).toArray();
    }
    return Object.values(this.localData.users || {});
  }

  async getUser(tgId) {
    const numId = Number(tgId);
    if (this.isMongo) {
      return await this.db.collection('users').findOne({
        $or: [{ id: numId }, { tgId: String(tgId) }, { tgId: numId }]
      });
    }
    return this.localData.users[String(tgId)] || null;
  }

  async ensureUser(tgId, username = '', firstName = '') {
    const numId = Number(tgId);
    const existing = await this.getUser(tgId);
    if (!existing) {
      const newUser = {
        id: numId,
        tgId: String(tgId),
        username: username || '',
        name: firstName || '',
        firstSeen: Date.now(),
        lastSeen: Date.now(),
        slots: {
          atf: config.DEFAULT_SLOT_ATF,
          ailab: config.DEFAULT_SLOT_AILAB,
          mrg: config.DEFAULT_SLOT_MRG,
          leaf: 1,
          maxTotal: config.DEFAULT_MAX_TOTAL
        }
      };
      if (this.isMongo) {
        try {
          await this.db.collection('users').insertOne(newUser);
        } catch (e) {}
      } else {
        this.localData.users[String(tgId)] = newUser;
        this._saveLocal();
      }
      return newUser;
    }
    return existing;
  }

  // --- Accounts Normalization (Adapts legacy schema: { owner_id, tg_id, init_data, enabled }) ---
  async getAccounts(minerType, tgId = null) {
    const colName = `${minerType}_accounts`;
    let rawList = [];

    if (this.isMongo) {
      const q = tgId ? {
        $or: [
          { tg_id: Number(tgId) }, { tg_id: String(tgId) },
          { tgId: Number(tgId) }, { tgId: String(tgId) },
          { owner_id: Number(tgId) }, { owner_id: String(tgId) }
        ]
      } : {};
      rawList = await this.db.collection(colName).find(q).toArray();
    } else {
      const accs = Object.values(this.localData[colName] || {});
      rawList = tgId ? accs.filter(a => String(a.tgId || a.tg_id || a.owner_id) === String(tgId)) : accs;
    }

    // Normalize
    return rawList.map(a => ({
      tgId: a.tg_id || a.tgId || a.owner_id,
      label: a.label || 'main',
      initData: a.init_data || a.initData,
      active: a.enabled !== undefined ? a.enabled : (a.active !== undefined ? a.active : true),
      proxy: a.proxy || null,
      updatedAt: a.updated_at || a.updatedAt
    }));
  }

  async getAllAccountsGlobal() {
    const atf = await this.getAccounts('atf');
    const mrg = await this.getAccounts('mrg');
    const ailab = await this.getAccounts('ailab');
    const leaf = await this.getAccounts('leaf');
    return {
      atf,
      mrg,
      ailab,
      leaf,
      total: atf.length + mrg.length + ailab.length + leaf.length
    };
  }

  async saveAccount(minerType, account) {
    const colName = `${minerType}_accounts`;
    const numId = Number(account.tgId);

    const doc = {
      label: account.label,
      owner_id: numId,
      tg_id: numId,
      tgId: String(account.tgId),
      init_data: account.initData,
      initData: account.initData,
      enabled: account.active !== false,
      active: account.active !== false,
      proxy: account.proxy || null,
      updated_at: Date.now(),
      miner_type: minerType
    };

    if (this.isMongo) {
      await this.db.collection(colName).updateOne(
        {
          $or: [{ tg_id: numId }, { tgId: String(account.tgId) }],
          label: account.label
        },
        { $set: doc },
        { upsert: true }
      );
    } else {
      if (!this.localData[colName]) this.localData[colName] = {};
      this.localData[colName][`${account.tgId}_${account.label}`] = doc;
      this._saveLocal();
    }
  }

  async toggleAccountActive(minerType, tgId, label, active) {
    const colName = `${minerType}_accounts`;
    const numId = Number(tgId);
    if (this.isMongo) {
      await this.db.collection(colName).updateOne(
        { $or: [{ tg_id: numId }, { tgId: String(tgId) }], label },
        { $set: { active, enabled: active } }
      );
    } else {
      const key = `${tgId}_${label}`;
      if (this.localData[colName]?.[key]) {
        this.localData[colName][key].active = active;
        this.localData[colName][key].enabled = active;
        this._saveLocal();
      }
    }
  }

  async deleteAccount(minerType, tgId, label) {
    const colName = `${minerType}_accounts`;
    const numId = Number(tgId);
    if (this.isMongo) {
      await this.db.collection(colName).deleteOne({
        $or: [{ tg_id: numId }, { tgId: String(tgId) }],
        label
      });
    } else {
      const key = `${tgId}_${label}`;
      if (this.localData[colName]) {
        delete this.localData[colName][key];
        this._saveLocal();
      }
    }
  }
}

module.exports = new Database();
