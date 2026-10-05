const { botLog } = require('../logger');

class OTPManager {
  constructor() {
    this.pendingOtps = new Map(); // key: `leaf_${tgId}_${label}` -> { tgId, label, minerType, initData, createdAt, codeLeftSec }
    this.botInstance = null;
  }

  setBot(bot) {
    this.botInstance = bot;
  }

  async notifyOtpRequired(minerType, tgId, label, initData, codeLeftSec = 300) {
    const key = `${minerType}_${tgId}_${label}`;
    const now = Date.now();
    const existing = this.pendingOtps.get(key);

    // Don't spam notifications if notified within last 2 minutes
    if (existing && (now - existing.notifiedAt) < 120000) {
      return;
    }

    this.pendingOtps.set(key, {
      minerType,
      tgId,
      label,
      initData,
      createdAt: now,
      notifiedAt: now,
      codeLeftSec
    });

    botLog.warn(`[OTP] Safety Check Triggered for ${label} (${tgId})!`);

    if (this.botInstance) {
      try {
        const text = `🚨 *URGENT: Safety Check (OTP) Required!*\n\n` +
                     `Account: *${label}* (${minerType.toUpperCase()})\n` +
                     `⏱️ *Time Left:* ~${Math.round(codeLeftSec)} seconds\n\n` +
                     `Leaf server has sent a *4-digit verification code* to your official *@LeafEarnBot* on Telegram.\n\n` +
                     `👉 *How to submit:* \n` +
                     `1. Just reply to this bot with the *4-digit code* (e.g. \`1234\`), OR\n` +
                     `2. Open the Web Dashboard and enter the code in the Safety Portal.`;

        await this.botInstance.api.sendMessage(tgId, text, { parse_mode: 'Markdown' });
      } catch (err) {
        botLog.error(`Failed to send Telegram notification to ${tgId}`, err.message);
      }
    }
  }

  hasPendingOtp(tgId) {
    for (const [key, item] of this.pendingOtps.entries()) {
      if (String(item.tgId) === String(tgId)) {
        return item;
      }
    }
    return null;
  }

  getPendingList() {
    const list = [];
    for (const [key, item] of this.pendingOtps.entries()) {
      const elapsed = Math.floor((Date.now() - item.createdAt) / 1000);
      const remaining = Math.max(0, item.codeLeftSec - elapsed);
      list.push({
        key,
        ...item,
        remainingSec: remaining
      });
    }
    return list;
  }

  clearOtp(minerType, tgId, label) {
    const key = `${minerType}_${tgId}_${label}`;
    this.pendingOtps.delete(key);
  }
}

module.exports = new OTPManager();
