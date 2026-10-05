const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const https = require('https');
const config = require('../config');
const { createLogger } = require('../logger');

const log = createLogger('CLOUDFLARE');

class CloudflaredManager {
  constructor() {
    this.binDir = path.join(__dirname, '../../bin');
    this.binPath = path.join(this.binDir, process.platform === 'win32' ? 'cloudflared.exe' : 'cloudflared');
    this.process = null;
  }

  getDownloadUrl() {
    const arch = process.arch;
    const platform = process.platform;

    if (platform === 'linux') {
      if (arch === 'x64') {
        return 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64';
      } else if (arch === 'arm64') {
        return 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64';
      }
    }
    return 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64';
  }

  downloadBinary(url, dest) {
    return new Promise((resolve, reject) => {
      const follow = (curUrl) => {
        https.get(curUrl, (res) => {
          if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
            return follow(res.headers.location);
          }
          if (res.statusCode !== 200) {
            return reject(new Error(`HTTP ${res.statusCode}`));
          }
          const fileStream = fs.createWriteStream(dest);
          res.pipe(fileStream);
          fileStream.on('finish', () => {
            fileStream.close(() => {
              try { fs.chmodSync(dest, 0o755); } catch (e) {}
              resolve();
            });
          });
        }).on('error', (err) => {
          fs.unlink(dest, () => {});
          reject(err);
        });
      };
      follow(url);
    });
  }

  async ensureBinary() {
    if (!fs.existsSync(this.binDir)) {
      fs.mkdirSync(this.binDir, { recursive: true });
    }

    if (fs.existsSync(this.binPath)) {
      try { fs.chmodSync(this.binPath, 0o755); } catch (e) {}
      return true;
    }

    log.info('⬇️ Auto-downloading cloudflared binary...');
    const url = this.getDownloadUrl();
    await this.downloadBinary(url, this.binPath);
    log.info('✅ cloudflared binary ready!');
    return true;
  }

  async start() {
    const token = config.CLOUDFLARE_TUNNEL_TOKEN?.trim();
    if (!token) return;

    try {
      await this.ensureBinary();
      log.info(`🚀 Starting Cloudflare Tunnel -> Forwarding to http://127.0.0.1:${config.WEB_PORT}...`);

      this.process = spawn(this.binPath, ['tunnel', 'run', '--token', token], {
        stdio: ['ignore', 'pipe', 'pipe']
      });

      this.process.stdout.on('data', (d) => {
        const line = d.toString().trim();
        if (line) log.info(`[tunnel] ${line}`);
      });

      this.process.stderr.on('data', (d) => {
        const line = d.toString().trim();
        if (line && (line.includes('Connected to') || line.includes('Registered tunnel') || line.includes('INF Connection'))) {
          log.info(`[tunnel] ✅ ${line}`);
        } else if (line && line.includes('ERR')) {
          log.warn(`[tunnel] ${line}`);
        }
      });

      this.process.on('close', (code) => {
        log.warn(`Cloudflare tunnel closed (code ${code})`);
      });
    } catch (err) {
      log.error('Cloudflare tunnel error', err.message);
    }
  }

  stop() {
    if (this.process) {
      try { this.process.kill(); } catch (e) {}
    }
  }
}

module.exports = new CloudflaredManager();
