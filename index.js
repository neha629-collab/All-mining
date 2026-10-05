require('dotenv').config?.();
const config = require('./src/config');
const db = require('./src/db');
const bot = require('./src/bot');
const proxyManager = require('./src/services/proxyManager');
const scheduler = require('./src/services/scheduler');
const otpManager = require('./src/services/otpNotifier');
const cloudflared = require('./src/services/cloudflared');
const { createWebServer } = require('./src/web/server');
const { log } = require('./src/logger');

async function bootstrap() {
  log.info('===========================================================');
  log.info('🚀 Launching All-Mining Pro (Enterprise Edition)');
  log.info('===========================================================');

  // 1. Connect MongoDB / Local JSON fallback
  await db.connect();

  // 2. Initialize Proxy Engine
  await proxyManager.init();

  // 3. Connect bot instance to OTP Manager
  otpManager.setBot(bot);

  // 4. Start Mining Scheduler
  scheduler.start();

  // 5. Start Web Control Panel on Jexactyl port (passes bot instance for Broadcast API)
  const webApp = createWebServer(bot);
  const server = webApp.listen(config.WEB_PORT, config.WEB_HOST, () => {
    log.info(`🌐 Web Dashboard & OTP Portal listening on http://${config.WEB_HOST}:${config.WEB_PORT}`);
  });

  // 6. Start Cloudflare Tunnel
  if (config.CLOUDFLARE_TUNNEL_TOKEN) {
    cloudflared.start().catch((err) => {
      log.error('Cloudflare tunnel error', err);
    });
  }

  // 7. Start Telegram Bot Polling
  if (config.BOT_TOKEN && config.BOT_TOKEN !== 'dummy_token') {
    bot.start({
      onStart: (botInfo) => {
        log.info(`🤖 Telegram Bot @${botInfo.username} started successfully!`);
      }
    });
  }

  // Graceful Shutdown
  const shutdown = async () => {
    log.info('Gracefully shutting down services...');
    cloudflared.stop();
    scheduler.stop();
    server.close();
    process.exit(0);
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

bootstrap().catch((err) => {
  log.error('Fatal startup error during bootstrap', err);
  process.exit(1);
});
