// leafws.js — minimal RFC 6455 WebSocket client over TLS (wss://), zero dependencies
// Just enough for the leafearn.site game socket: binary frames, ping/pong, close.
'use strict';

const tls = require('tls');
const crypto = require('crypto');

class MiniWS {
  constructor(url, protocols = []) {
    this.url = new URL(url);
    this.protocols = protocols;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    this.onopen = null;
    this._buf = Buffer.alloc(0);
    this._fragments = [];
    this._fragOp = 0;
    this.readyState = 0; // 0 connecting, 1 open, 3 closed
  }

  connect(timeoutMs = 10000) {
    return new Promise((resolve, reject) => {
      const key = crypto.randomBytes(16).toString('base64');
      const sock = tls.connect({
        host: this.url.hostname,
        port: 443,
        servername: this.url.hostname,
        rejectUnauthorized: true,
      }, () => {
        const protoHdr = this.protocols.length ? `Sec-WebSocket-Protocol: ${this.protocols.join(', ')}\r\n` : '';
        sock.write(
          `GET ${this.url.pathname}${this.url.search} HTTP/1.1\r\n` +
          `Host: ${this.url.hostname}\r\n` +
          `Upgrade: websocket\r\n` +
          `Connection: Upgrade\r\n` +
          `Sec-WebSocket-Key: ${key}\r\n` +
          `Sec-WebSocket-Version: 13\r\n` +
          protoHdr +
          `\r\n`
        );
      });
      this.sock = sock;
      const timer = setTimeout(() => { sock.destroy(); reject(new Error('socket timeout')); }, timeoutMs);

      let handshook = false;
      sock.on('data', (chunk) => {
        if (!handshook) {
          this._buf = Buffer.concat([this._buf, chunk]);
          const idx = this._buf.indexOf('\r\n\r\n');
          if (idx < 0) return;
          const head = this._buf.slice(0, idx).toString('utf8');
          this._buf = this._buf.slice(idx + 4);
          if (!/101/.test(head.split('\r\n')[0])) {
            clearTimeout(timer); sock.destroy();
            return reject(new Error('ws handshake failed: ' + head.split('\r\n')[0]));
          }
          handshook = true;
          this.readyState = 1;
          clearTimeout(timer);
          resolve();
          this._drain();
          if (this.onopen) this.onopen();
        } else {
          this._buf = Buffer.concat([this._buf, chunk]);
          this._drain();
        }
      });
      sock.on('error', (e) => { clearTimeout(timer); this.onerror && this.onerror(e); reject(e); });
      sock.on('close', () => { this.readyState = 3; this.onclose && this.onclose(); });
    });
  }

  _drain() {
    while (true) {
      if (this._buf.length < 2) return;
      const b0 = this._buf[0], b1 = this._buf[1];
      const fin = (b0 & 0x80) !== 0;
      const opcode = b0 & 0x0f;
      const masked = (b1 & 0x80) !== 0;
      let len = b1 & 0x7f;
      let off = 2;
      if (len === 126) {
        if (this._buf.length < 4) return;
        len = this._buf.readUInt16BE(2); off = 4;
      } else if (len === 127) {
        if (this._buf.length < 10) return;
        const big = this._buf.readBigUInt64BE(2);
        len = Number(big); off = 10;
      }
      let maskKey = null;
      if (masked) {
        if (this._buf.length < off + 4) return;
        maskKey = this._buf.slice(off, off + 4); off += 4;
      }
      if (this._buf.length < off + len) return;
      let payload = this._buf.slice(off, off + len);
      this._buf = this._buf.slice(off + len);
      if (maskKey) {
        const un = Buffer.allocUnsafe(len);
        for (let i = 0; i < len; i++) un[i] = payload[i] ^ maskKey[i & 3];
        payload = un;
      }
      if (opcode === 0x8) { this.close(); return; }
      if (opcode === 0x9) { this._sendFrame(0xA, payload); continue; }
      if (opcode === 0xA) continue;
      if (opcode === 0x0) { // continuation
        this._fragments.push(payload);
        if (fin) {
          const full = Buffer.concat(this._fragments);
          this._fragments = [];
          if (this.onmessage) this.onmessage({ data: full });
        }
        continue;
      }
      if (!fin) { this._fragOp = opcode; this._fragments = [payload]; continue; }
      if (this.onmessage) this.onmessage({ data: payload });
    }
  }

  _sendFrame(opcode, payload) {
    if (!this.sock || this.readyState !== 1) return;
    const len = payload.length;
    const mask = crypto.randomBytes(4);
    let header;
    if (len < 126) {
      header = Buffer.from([0x80 | opcode, 0x80 | len]);
    } else if (len < 65536) {
      header = Buffer.alloc(4);
      header[0] = 0x80 | opcode; header[1] = 0x80 | 126;
      header.writeUInt16BE(len, 2);
    } else {
      header = Buffer.alloc(10);
      header[0] = 0x80 | opcode; header[1] = 0x80 | 127;
      header.writeBigUInt64BE(BigInt(len), 2);
    }
    const masked = Buffer.allocUnsafe(len);
    for (let i = 0; i < len; i++) masked[i] = payload[i] ^ mask[i & 3];
    this.sock.write(Buffer.concat([header, mask, masked]));
  }

  send(buf) { this._sendFrame(0x2, Buffer.isBuffer(buf) ? buf : Buffer.from(buf)); }
  close() {
    if (this.sock && this.readyState === 1) { try { this._sendFrame(0x8, Buffer.alloc(0)); } catch {} }
    this.readyState = 3;
    if (this.sock) { try { this.sock.destroy(); } catch {} }
  }
}

module.exports = { MiniWS };
