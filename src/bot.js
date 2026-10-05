const { Bot, InlineKeyboard } = require('grammy');
const config = require('./config');
const db = require('./db');
const proxyManager = require('./services/proxyManager');
const scheduler = require('./services/scheduler');
const otpManager = require('./services/otpNotifier');
const forceJoin = require('./services/forceJoin');
const LeafMiner = require('./miners/leaf');
const { extractInitData, sanitizeMarkdown } = require('./utils/extractors');
const { botLog } = require('./logger');

const bot = new Bot(config.BOT_TOKEN || 'dummy_token');
const userStates = new Map();

function isAdmin(tgId) {
  return config.ADMIN_IDS.includes(Number(tgId));
}

// Global Error Handler
bot.catch((err) => {
  botLog.error(`Telegram Bot Error: ${err.message}`);
});

// Force Join Gate Helper
async function checkForceJoinGate(ctx) {
  if (!ctx.from) return true;
  const missing = await forceJoin.getMissingChannels(bot, ctx.from.id);
  if (!missing || missing.length === 0) return true;

  const keyboard = [];
  missing.forEach(ch => {
    keyboard.push([{ text: `📢 Join ${ch.title}`, url: forceJoin.getChannelUrl(ch.id) }]);
  });
  keyboard.push([{ text: `✅ I've Joined — Verify Access`, callback_data: 'forcejoin_verify', style: 'success' }]);

  const names = missing.map(m => `  • *${sanitizeMarkdown(m.title)}*`).join('\n');
  const gateText = `🔒 *Channel Membership Required*\n\n` +
                   `To access All-Mining Pro bot and its automation engine, you must join our official channels:\n\n` +
                   `${names}\n\n` +
                   `After joining, tap the *Verify Access* button below.`;

  if (ctx.callbackQuery) {
    try {
      await ctx.answerCallbackQuery({ text: '❌ Please join all channels first!', show_alert: true });
      await ctx.editMessageText(gateText, { parse_mode: 'Markdown', reply_markup: { inline_keyboard: keyboard } });
    } catch (e) {
      await ctx.reply(gateText, { parse_mode: 'Markdown', reply_markup: { inline_keyboard: keyboard } });
    }
  } else {
    await ctx.reply(gateText, { parse_mode: 'Markdown', reply_markup: { inline_keyboard: keyboard } });
  }

  return false;
}

// User Context & Force Join Middleware
bot.use(async (ctx, next) => {
  if (ctx.from) {
    try {
      await db.ensureUser(ctx.from.id, ctx.from.username, ctx.from.first_name);
    } catch (e) {}
  }

  // Allow verify callback always
  if (ctx.callbackQuery && ctx.callbackQuery.data === 'forcejoin_verify') {
    return await next();
  }

  // If force join check fails, stop propagation
  const allowed = await checkForceJoinGate(ctx);
  if (!allowed) return;

  return await next();
});

// Force Join Verify Callback
bot.callbackQuery('forcejoin_verify', async (ctx) => {
  forceJoin.clearUserCache(ctx.from.id);
  const missing = await forceJoin.getMissingChannels(bot, ctx.from.id);
  if (missing.length > 0) {
    await ctx.answerCallbackQuery({ text: '❌ You still have not joined all channels!', show_alert: true });
    return await checkForceJoinGate(ctx);
  }

  await ctx.answerCallbackQuery({ text: '🎉 Verified successfully!' });
  const text = `🎉 *Verified & Access Granted!*\n\n` +
               `Welcome to All-Mining Pro. Tap below to launch your mining hub!`;
  await ctx.editMessageText(text, {
    parse_mode: 'Markdown',
    reply_markup: getMainMenu(ctx.from.id)
  });
});

/**
 * Modern Telegram Bot API 2026 Colorful Buttons Generator:
 * Supports style: "primary" (blue glass), "success" (green glass), "danger" (red glass)
 */
function getMainMenu(userId) {
  const webAppUrl = `${config.CLOUDFLARE_DOMAIN}?tgId=${userId}`;

  const keyboard = [
    [
      { text: '🚀 Open Mining WebApp', web_app: { url: webAppUrl }, style: 'primary' }
    ],
    [
      { text: '🌿 Leaf Miner', callback_data: 'menu_leaf', style: 'success' },
      { text: '⛏️ ATF Miner', callback_data: 'menu_atf', style: 'primary' }
    ],
    [
      { text: '💎 MRG Miner', callback_data: 'menu_mrg', style: 'primary' },
      { text: '🤖 AI Lab', callback_data: 'menu_ailab', style: 'primary' }
    ],
    [
      { text: '📊 Dashboard', callback_data: 'menu_dashboard', style: 'success' },
      { text: 'ℹ️ Help', callback_data: 'menu_help' }
    ]
  ];

  // STRICT SECURITY: Only super admin IDs get the admin panel button
  if (isAdmin(userId)) {
    keyboard.push([
      { text: '🛡️ Admin Command Center', callback_data: 'menu_admin', style: 'danger' }
    ]);
  }

  return { inline_keyboard: keyboard };
}

// /start
bot.command('start', async (ctx) => {
  const name = ctx.from?.first_name || 'Miner';
  const text = `👋 *Welcome ${sanitizeMarkdown(name)} to All-Mining Pro (Enterprise Edition)!*\n\n` +
               `⚡ *Automated Multi-Mining Hub:*\n` +
               `• *Leaf Miner:* Auto-Mine, SOCKS5 Proxy, Safety OTP Support\n` +
               `• *ATF Miner:* 24/7 Auto Claim, Safe Math Solver, Boost\n` +
               `• *MRG Miner:* Auto Claim, Team Commission, Daily Bonus\n` +
               `• *AI Lab:* Keep-Alive Heartbeat\n\n` +
               `🔗 *Official Force Refer Links:*\n` +
               `🌿 Leaf: [Join Leaf Earn Bot](${config.LEAF_REF_LINK})\n` +
               `⛏️ ATF: [Join ATF Miner](${config.ATF_REF_LINK})\n` +
               `💎 MRG: [Join MRG Miner](${config.MRG_REF_LINK})\n\n` +
               `📱 Tap the colorful *Open Mining WebApp* button below to manage everything visually!`;

  await ctx.reply(text, {
    parse_mode: 'Markdown',
    reply_markup: getMainMenu(ctx.from.id),
    disable_web_page_preview: true
  });
});

// Dashboard in chat
bot.callbackQuery('menu_dashboard', async (ctx) => {
  await ctx.answerCallbackQuery();
  const leafAccs = await db.getAccounts('leaf', ctx.from.id);
  const atfAccs = await db.getAccounts('atf', ctx.from.id);
  const mrgAccs = await db.getAccounts('mrg', ctx.from.id);
  const ailabAccs = await db.getAccounts('ailab', ctx.from.id);

  let text = `📊 *Your Mining Dashboard*\n\n` +
             `👤 User ID: \`${ctx.from.id}\`\n` +
             `🌿 Leaf Accounts: ${leafAccs.length}\n` +
             `⛏️ ATF Accounts: ${atfAccs.length}\n` +
             `💎 MRG Accounts: ${mrgAccs.length}\n` +
             `🤖 AI Lab Accounts: ${ailabAccs.length}\n\n` +
             `🚀 *Total Connected Accounts:* ${leafAccs.length + atfAccs.length + mrgAccs.length + ailabAccs.length}\n` +
             `🛡️ *Anti-Ban Protection:* ${config.USE_PROXY ? '✅ Active (Sticky IP)' : '❌ Disabled'}\n`;

  const replyMarkup = {
    inline_keyboard: [
      [{ text: '🔙 Back to Main Menu', callback_data: 'menu_main' }]
    ]
  };

  await ctx.editMessageText(text, { parse_mode: 'Markdown', reply_markup: replyMarkup });
});

// Admin Command Center (Strict Auth Check)
bot.callbackQuery('menu_admin', async (ctx) => {
  await ctx.answerCallbackQuery();
  if (!isAdmin(ctx.from.id)) {
    return await ctx.reply('⛔ Access Denied: Unauthorized admin command.');
  }

  const allUsers = await db.getAllUsers();
  const allAccounts = await db.getAllAccountsGlobal();
  const proxyStatus = proxyManager.getStatus();
  const schedStats = scheduler.getLiveStats();

  let text = `🛡️ *Super Admin Command Center*\n\n` +
             `👥 Users: ${allUsers.length}\n` +
             `⚡ Total Accounts: ${allAccounts.total} (Leaf: ${(allAccounts.leaf || []).length}, ATF: ${allAccounts.atf.length}, MRG: ${allAccounts.mrg.length})\n\n` +
             `🌐 *Anti-Ban Proxies:* ${proxyStatus.healthyCount} Healthy & Active\n` +
             `⚙️ *Scheduler Claims:* ${schedStats.successfulClaims} successful claims\n` +
             `🌐 *Server Port:* ${config.WEB_PORT} (Allocated: ${config.SERVER_IP_PORT})\n` +
             `☁️ *Cloudflare Domain:* ${config.CLOUDFLARE_DOMAIN}`;

  const replyMarkup = {
    inline_keyboard: [
      [
        { text: '🔄 Refresh Proxy Pool', callback_data: 'admin_refresh_proxies', style: 'primary' },
        { text: '⚡ Trigger Immediate Cycle', callback_data: 'admin_trigger_cycle', style: 'success' }
      ],
      [
        { text: '🔙 Back to Main Menu', callback_data: 'menu_main' }
      ]
    ]
  };

  await ctx.editMessageText(text, { parse_mode: 'Markdown', reply_markup: replyMarkup });
});

bot.callbackQuery('admin_refresh_proxies', async (ctx) => {
  if (!isAdmin(ctx.from.id)) return await ctx.answerCallbackQuery({ text: '⛔ Unauthorized', show_alert: true });
  await ctx.answerCallbackQuery({ text: 'Starting proxy validation...' });
  proxyManager.refreshProxies();
  await ctx.reply('🔄 Proxy scraper and validation triggered in background!');
});

bot.callbackQuery('admin_trigger_cycle', async (ctx) => {
  if (!isAdmin(ctx.from.id)) return await ctx.answerCallbackQuery({ text: '⛔ Unauthorized', show_alert: true });
  await ctx.answerCallbackQuery({ text: 'Executing mining cycle...' });
  scheduler.runCycle();
  await ctx.reply('⚡ Mining cycle triggered manually for all accounts!');
});

// Miner Submenus (leaf, atf, mrg, ailab)
['leaf', 'atf', 'mrg', 'ailab'].forEach((type) => {
  bot.callbackQuery(`menu_${type}`, async (ctx) => {
    await ctx.answerCallbackQuery();
    const title = type === 'leaf' ? '🌿 Leaf Miner' : `${type.toUpperCase()} Miner`;
    const replyMarkup = {
      inline_keyboard: [
        [
          { text: `➕ Add ${type.toUpperCase()} Account`, callback_data: `add_${type}`, style: 'success' },
          { text: `📋 View My Accounts`, callback_data: `list_${type}`, style: 'primary' }
        ],
        [
          { text: '🔙 Back to Menu', callback_data: 'menu_main' }
        ]
      ]
    };
    await ctx.editMessageText(`⛏️ *${title} Management Menu*\nChoose an action:`, {
      parse_mode: 'Markdown',
      reply_markup: replyMarkup
    });
  });

  bot.callbackQuery(`add_${type}`, async (ctx) => {
    await ctx.answerCallbackQuery();
    userStates.set(ctx.from.id, { step: 'awaiting_initdata', type });
    await ctx.reply(
      `👉 Send your *${type.toUpperCase()}* WebApp URL or \`initData\` query string.\n\n` +
      `_Tip: Open the Telegram Mini App, copy the URL containing \`#tgWebAppData=...\` or query string._`,
      { parse_mode: 'Markdown' }
    );
  });

  bot.callbackQuery(`list_${type}`, async (ctx) => {
    await ctx.answerCallbackQuery();
    const accs = await db.getAccounts(type, ctx.from.id);
    if (!accs.length) {
      return await ctx.reply(`❌ No ${type.toUpperCase()} accounts found.`);
    }

    let msg = `📋 *Your ${type.toUpperCase()} Accounts:*\n\n`;
    const keyboard = [];
    accs.forEach((a, i) => {
      msg += `${i + 1}. *${sanitizeMarkdown(a.label)}*\n` +
             `   • Status: ${a.active !== false ? '🟢 Mining Active' : '⏸️ Paused'}\n` +
             `   • Anti-Ban Proxy: \`${proxyManager.getStickyProxy(`${type}_${a.tgId}_${a.label}`) || 'Direct'}\`\n\n`;
      keyboard.push([{ text: `🗑 Delete ${a.label}`, callback_data: `del_${type}_${a.label}`, style: 'danger' }]);
    });
    keyboard.push([{ text: '🔙 Back', callback_data: `menu_${type}` }]);

    await ctx.reply(msg, { parse_mode: 'Markdown', reply_markup: { inline_keyboard: keyboard } });
  });
});

// Delete Callback (Strict User Isolation: can only delete caller's own accounts)
bot.callbackQuery(/^del_(leaf|atf|mrg|ailab)_(.+)$/, async (ctx) => {
  const type = ctx.match[1];
  const label = ctx.match[2];
  await db.deleteAccount(type, ctx.from.id, label);
  await ctx.answerCallbackQuery({ text: `Account ${label} deleted!` });
  await ctx.reply(`🗑 Account *${sanitizeMarkdown(label)}* removed from ${type.toUpperCase()}.`, { parse_mode: 'Markdown' });
});

bot.callbackQuery('menu_main', async (ctx) => {
  await ctx.answerCallbackQuery();
  await ctx.editMessageText('📱 *Main Menu*', {
    parse_mode: 'Markdown',
    reply_markup: getMainMenu(ctx.from.id)
  });
});

// Message Listener (Handles OTP verification + Add Account conversation)
bot.on('message:text', async (ctx) => {
  const text = ctx.message.text.trim();

  // 1. Check if user is submitting a 4-digit OTP code for a pending Leaf Safety Check
  const pendingOtp = otpManager.hasPendingOtp(ctx.from.id);
  if (pendingOtp && /^\d{4,8}$/.test(text)) {
    await ctx.reply(`⏳ Submitting Safety Code \`${text}\` for account *${pendingOtp.label}*...`, { parse_mode: 'Markdown' });
    try {
      const proxy = proxyManager.getStickyProxy(`${pendingOtp.minerType}_${pendingOtp.tgId}_${pendingOtp.label}`);
      const client = new LeafMiner(pendingOtp, proxy);
      const res = await client.verifySafetyCheck(text);
      if (res && res.ok) {
        otpManager.clearOtp(pendingOtp.minerType, pendingOtp.tgId, pendingOtp.label);
        return await ctx.reply(`🎉 *Success!* Safety Check verified successfully! Leaf Miner resumed automatically.`, { parse_mode: 'Markdown' });
      } else {
        return await ctx.reply(`❌ Invalid code or verification failed. Please check @LeafEarnBot for new code.`);
      }
    } catch (err) {
      return await ctx.reply(`❌ Error verifying OTP: ${err.message}`);
    }
  }

  // 2. Add Account Conversation flow
  const state = userStates.get(ctx.from.id);
  if (!state) return;

  if (state.step === 'awaiting_initdata') {
    const initData = extractInitData(text);
    if (!initData) {
      return await ctx.reply('❌ Invalid format! Please send a valid WebApp query URL or initData containing `hash=`.');
    }

    state.initData = initData;
    state.step = 'awaiting_label';
    return await ctx.reply('✅ Valid data verified!\nNow send a short unique label for this account (e.g. `main`, `phone2`):');
  }

  if (state.step === 'awaiting_label') {
    const label = text.replace(/[^a-zA-Z0-9_-]/g, '');
    if (!label) {
      return await ctx.reply('❌ Invalid label. Please use letters, numbers, or underscore only.');
    }

    // Allocate sticky proxy
    const assignedProxy = proxyManager.getStickyProxy(`${state.type}_${ctx.from.id}_${label}`);

    await db.saveAccount(state.type, {
      tgId: ctx.from.id,
      label,
      initData: state.initData,
      active: true,
      proxy: assignedProxy
    });

    userStates.delete(ctx.from.id);
    await ctx.reply(
      `🎉 Account *${sanitizeMarkdown(label)}* linked successfully to *${state.type.toUpperCase()}*!\n` +
      `🛡️ Anti-Ban Dedicated Proxy: \`${assignedProxy || 'Default Pool'}\`\n` +
      `⚡ Auto-mining & Auto-claims are now enabled for this account.`,
      { parse_mode: 'Markdown', reply_markup: getMainMenu(ctx.from.id) }
    );
  }
});

module.exports = bot;
