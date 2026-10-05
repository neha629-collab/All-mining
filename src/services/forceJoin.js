/**
 * Force Join Service for Telegram Bot
 * Enforces channel membership before granting access to commands or web features.
 * Caches member status to avoid Telegram API rate limits.
 */
const config = require('../config');
const { botLog } = require('../logger');

const membershipCache = new Map(); // key: `${userId}_${channelId}` -> { joined: bool, timestamp: number }

const JOINED_STATUSES = ['creator', 'administrator', 'member', 'restricted'];

function getChannelUrl(channelId) {
  const cid = String(channelId).trim();
  if (cid.startsWith('@')) return `https://t.me/${cid.slice(1)}`;
  if (cid.startsWith('https://') || cid.startsWith('t.me/')) return cid.startsWith('http') ? cid : `https://${cid}`;
  if (cid.startsWith('-100')) return `https://t.me/c/${cid.slice(4)}`;
  return `https://t.me/${cid.replace(/^@/, '')}`;
}

function parseChannels(channelsConfig) {
  if (!Array.isArray(channelsConfig)) return [];
  return channelsConfig.map(entry => {
    if (typeof entry === 'string') {
      const parts = entry.split(':');
      const id = parts[0].trim();
      const title = parts.slice(1).join(':').trim() || id;
      return { id, title };
    }
    return entry;
  });
}

async function checkOneChannel(bot, userId, channelId, ttlSec = 300) {
  const cacheKey = `${userId}_${channelId}`;
  const cached = membershipCache.get(cacheKey);
  const now = Date.now();

  if (cached && (now - cached.timestamp) < ttlSec * 1000) {
    return { channelId, isMember: cached.joined };
  }

  try {
    const member = await bot.api.getChatMember(channelId, userId);
    const isMember = JOINED_STATUSES.includes(member.status);
    membershipCache.set(cacheKey, { joined: isMember, timestamp: now });
    return { channelId, isMember };
  } catch (err) {
    const msg = (err.message || '').toLowerCase();
    // If bot is not admin or channel is inaccessible, fail-open to not block users permanently
    if (msg.includes('chat not found') || msg.includes('not enough rights') || msg.includes('bot is not a member') || msg.includes('member list is inaccessible')) {
      botLog.warn(`[ForceJoin] Bot cannot verify channel ${channelId}: ${err.message}. (Ensure bot is ADMIN in the channel)`);
      membershipCache.set(cacheKey, { joined: true, timestamp: now });
      return { channelId, isMember: true };
    }
    botLog.warn(`[ForceJoin] Check failed for ${channelId}: ${err.message}`);
    return { channelId, isMember: true };
  }
}

async function getMissingChannels(bot, userId) {
  if (!config.FORCE_JOIN_ENABLED) return [];
  if (config.ADMIN_IDS.includes(Number(userId))) return []; // Admins bypass

  const channels = parseChannels(config.FORCE_JOIN_CHANNELS);
  if (!channels.length) return [];

  const ttl = config.FORCE_JOIN_CACHE_TTL || 300;
  const checks = await Promise.all(channels.map(ch => checkOneChannel(bot, userId, ch.id, ttl)));

  const missing = [];
  checks.forEach((res, i) => {
    if (!res.isMember) {
      missing.push(channels[i]);
    }
  });

  return missing;
}

function clearUserCache(userId) {
  for (const key of membershipCache.keys()) {
    if (key.startsWith(`${userId}_`)) {
      membershipCache.delete(key);
    }
  }
}

module.exports = {
  getMissingChannels,
  clearUserCache,
  getChannelUrl,
  parseChannels
};
