// leafapi.js — LeafEarn gRPC-web client
// Handles: tone.wasm discovery + x-app-rev / x-view-hint signing (replicated from the
// official frontend), protobuf framing, and typed rpc() calls. Zero dependencies.
'use strict';

const https = require('https');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const proto = require('./leafproto');

const HOST = 'leafearn.site';
const ORIGIN = 'https://' + HOST;
const UA = 'Mozilla/5.0 (Linux; Android 13; LeafMine/1.0)';
const CACHE_DIR = path.join(__dirname, '..', 'config');
const WASM_FILE = path.join(CACHE_DIR, 'tone.wasm');
const META_FILE = path.join(CACHE_DIR, 'tone.meta.json');

const GRPC_CODES = {
  1: 'CANCELLED', 2: 'UNKNOWN', 3: 'INVALID_ARGUMENT', 4: 'DEADLINE_EXCEEDED',
  5: 'NOT_FOUND', 6: 'ALREADY_EXISTS', 7: 'PERMISSION_DENIED', 8: 'RESOURCE_EXHAUSTED',
  9: 'FAILED_PRECONDITION', 10: 'ABORTED', 11: 'OUT_OF_RANGE', 12: 'UNIMPLEMENTED',
  13: 'INTERNAL', 14: 'UNAVAILABLE', 15: 'DATA_LOSS', 16: 'UNAUTHENTICATED',
};

// ── tiny https helper ──────────────────────────────────────────────
function request(method, urlPath, headers, body) {
  return new Promise((resolve, reject) => {
    const req = https.request({
      method, hostname: HOST, path: urlPath, headers, timeout: 25000,
    }, (res) => {
      const bufs = [];
      res.on('data', (c) => bufs.push(c));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(bufs) }));
    });
    req.on('error', reject);
    req.on('timeout', () => req.destroy(new Error('timeout')));
    if (body) req.write(body);
    req.end();
  });
}

// ── frontend signer algorithms (reversed from bundle) ───────────────
function patternFor(s) {
  const t = [];
  for (let n = 0; n < s.length; n++) t.push((s.charCodeAt(s.length - 1 - n) + 3 * n) & 255);
  return t;
}
function mixTone(arr, s) {
  return arr.map((v, n) => v ^ s.charCodeAt((7 * n) % s.length));
}
function envelope(arr) {
  return Uint8Array.from(arr, (_, n) => arr[(n + 11) % arr.length]);
}
const sha256hex = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const hmacHex = (key, msg) => crypto.createHmac('sha256', key).update(msg).digest('hex');

// ── tone.wasm discovery (frontend deploys rotate /fx/tone-<hash>.wasm) ──
async function discoverToneUrl() {
  const home = await request('GET', '/', { 'user-agent': UA, accept: 'text/html' });
  if (home.status !== 200) throw new Error('frontend fetch failed: HTTP ' + home.status);
  const html = home.body.toString('utf8');
  const chunks = [...new Set([...html.matchAll(/\/_next\/static\/chunks\/[^"']+\.js/g)].map((m) => m[0]))];
  for (const c of chunks) {
    try {
      const js = await request('GET', c, { 'user-agent': UA });
      const m = js.body.toString('latin1').match(/\/fx\/tone-[a-f0-9]+\.wasm/);
      if (m) return m[0];
    } catch { /* keep scanning */ }
  }
  throw new Error('tone.wasm URL not found in frontend bundle');
}

let signerPromise = null;
function loadSigner(force) {
  if (signerPromise && !force) return signerPromise;
  signerPromise = (async () => {
    if (force || !fs.existsSync(WASM_FILE)) {
      const url = await discoverToneUrl();
      const res = await request('GET', url, { 'user-agent': UA });
      if (res.status !== 200) throw new Error('tone.wasm download failed: HTTP ' + res.status);
      fs.mkdirSync(CACHE_DIR, { recursive: true });
      fs.writeFileSync(WASM_FILE, res.body);
      fs.writeFileSync(META_FILE, JSON.stringify({ url, fetchedAt: new Date().toISOString() }, null, 2));
    }
    const { instance } = await WebAssembly.instantiate(fs.readFileSync(WASM_FILE));
    const w = instance.exports;
    if (typeof w.tone !== 'function') throw new Error('bad tone.wasm (missing exports)');
    const toneStr = (seed) => String.fromCharCode(...Array.from({ length: 32 }, (_, r) => w.tone(seed, r)));
    const s = Number(w.ease()) % 5;
    const key = envelope(mixTone(patternFor(toneStr(s)), toneStr((s + 2) % 5)));
    const rev = w.grain();
    return {
      key, rev,
      sign(serviceMethod, reqBytes, initData) {
        const nonce = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
        const a = `${serviceMethod}|${nonce}|${sha256hex(reqBytes)}|${sha256hex(Buffer.from(initData, 'utf8'))}`;
        return {
          'x-app-rev': String(rev),
          'x-view-hint': `${nonce}.${hmacHex(key, Buffer.from(a, 'utf8'))}`,
        };
      },
    };
  })().catch((e) => { signerPromise = null; throw e; });
  return signerPromise;
}

// ── gRPC-web framing ───────────────────────────────────────────────
function frame(payload) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(payload.length, 0);
  return Buffer.concat([Buffer.from([0]), len, payload]);
}

function parseFrames(buf) {
  let data = null, trailers = {}, headerGrpc = null;
  let off = 0;
  while (off + 5 <= buf.length) {
    const flag = buf[off];
    const len = buf.readUInt32BE(off + 1);
    const payload = buf.slice(off + 5, off + 5 + len);
    off += 5 + len;
    if (flag === 0) {
      if (!data) data = payload;
    } else if (flag & 0x80) {
      for (const line of payload.toString('utf8').split('\r\n')) {
        const i = line.indexOf(':');
        if (i > 0) trailers[line.slice(0, i).trim().toLowerCase()] = line.slice(i + 1).trim();
      }
    }
  }
  return { data, trailers, headerGrpc };
}

// ── typed RPC ──────────────────────────────────────────────────────
// rpc(acc.initData, 'leaf.v1.MineService', 'Status', 'leaf.v1.MineStatusRequest', {}, 'leaf.v1.MineStatusResponse')
async function rpc(initData, service, method, reqMsg, body, resMsg) {
  const sign = await loadSigner();
  const serviceMethod = `${service}/${method}`;
  const attempt = async () => {
    const reqBytes = proto.encode(reqMsg, body || {});
    const payload = frame(reqBytes);
    const sig = sign.sign(serviceMethod, reqBytes, initData);
    const res = await request('POST', '/' + serviceMethod, {
      'content-type': 'application/grpc-web+proto',
      'x-grpc-web': '1',
      accept: 'application/grpc-web+proto',
      'user-agent': UA,
      origin: ORIGIN,
      referer: ORIGIN + '/',
      'x-init-data': initData,
      ...sig,
      'content-length': payload.length,
    }, payload);
    const { data, trailers } = parseFrames(res.body);
    const statusHdr = trailers['grpc-status'] ?? (res.headers['grpc-status'] || '0');
    const msgRaw = trailers['grpc-message'] ?? res.headers['grpc-message'] ?? '';
    const message = decodeURIComponent(msgRaw.replace(/\+/g, '%20'));
    if (String(statusHdr) !== '0') {
      return { ok: false, grpcStatus: Number(statusHdr), code: GRPC_CODES[Number(statusHdr)] || 'UNKNOWN', message };
    }
    if (res.status !== 200) return { ok: false, code: 'HTTP_' + res.status, message: 'HTTP ' + res.status };
    return { ok: true, data: data && resMsg ? proto.decode(resMsg, data) : {} };
  };
  let r = await attempt();
  // frontend treats this specific message as "stale app rev → reload"
  if (!r.ok && /close and reopen/i.test(r.message || '')) {
    try { fs.unlinkSync(WASM_FILE); } catch {} try { fs.unlinkSync(META_FILE); } catch {}
    await loadSigner(true);
    r = await attempt();
  }
  // SAFETY_V1: server-side anti-bot gate → every RPC fails with this exact message until the
  // 4-digit Telegram code is verified (frontend: waitForSafetyCheck() interceptor → modal)
  if (!r.ok && r.message === SAFETY_REQUIRED) {
    r.safety = true;
    try { onSafety(initData, serviceMethod); } catch {}
    // SAFETY_WAIT_V2 (2026-09-29): Leaf এখন প্রতি কয়েক মিনিটে এই গেট দেয়। SAFETY_WAIT=1 দিলে
    // বট নিজে থেকে অপেক্ষা করে — আপনি ফোনে/Telegram-এ কোড দিয়ে verify করলেই কাজ আবার শুরু হবে।
    if (process.env.SAFETY_WAIT === '1' && !inSafetyWait) {
      const passed = await waitForSafety(initData, serviceMethod);
      if (passed) return attempt();
    }
  }
  return r;
}

// ── SAFETY_NOTIFY_V1: ঐচ্ছিক Telegram নোটিফিকেশন ──
// আপনার নিজের বট (BotFather থেকে) দিয়ে কোড-দরকার-মেসেজ পাঠায়। env:
//   TELEGRAM_BOT_TOKEN=123456:ABC...   TELEGRAM_CHAT_ID=1692540458
// কোড পাঠানো/পড়া হয় না — শুধু "কোড দরকার" বলে জানায় (নিরাপদ)।
async function notifyTelegram(text) {
  const token = process.env.TELEGRAM_BOT_TOKEN || '';
  const chat = process.env.TELEGRAM_CHAT_ID || '';
  if (!token || !chat) return false;
  try {
    const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ chat_id: chat, text, parse_mode: 'HTML', disable_web_page_preview: true }),
      signal: AbortSignal.timeout(15000),
    });
    return r.ok;
  } catch { return false; }
}

// ── SAFETY_WAIT_V2: কোড ভেরিফাই হওয়া পর্যন্ত অপেক্ষা (কোনো ডেডলক ছাড়া) ──
let inSafetyWait = false;
async function waitForSafety(initData, where) {
  const maxMin = Math.max(1, Number(process.env.SAFETY_WAIT_MIN || 30));
  const deadline = Date.now() + maxMin * 60000;
  inSafetyWait = true;
  try {
    console.log('\n\x1b[45m\x1b[1m  ⏳ SAFETY CODE দরকার  \x1b[0m');
    console.log('\x1b[33m⚠\x1b[0m সার্ভার "' + where + '" আটকে দিয়েছে। Telegram-এ @LeafEarnBot-এর মেসেজে ৪-ডিজিট কোড এসেছে' +
      ' (অথবা ফোনে Leaf অ্যাপ খুলে কোড দিন)। বট ' + maxMin + ' মিনিট অপেক্ষা করবে…\n');
    notifyTelegram('🛡 <b>Leaf: Safety কোড দরকার</b>\n' + where + ' আটকে গেছে।\n@LeafEarnBot-এর মেসেজে আসা ৪-ডিজিট কোডটা Safety Console-এ দিন — বট নিজেই আবার চালু হবে।\n(অথবা ফোনে Leaf অ্যাপে কোড দিন)').catch(() => {});
    let last = '';
    while (Date.now() < deadline) {
      const st = await rpc(initData, 'leaf.v1.AuthService', 'SafetyStatus', 'leaf.v1.SafetyStatusRequest', {}, 'leaf.v1.SafetyState').catch(() => null);
      if (st && st.ok && st.data.passed) {
        console.log('\x1b[32m✔\x1b[0m safety ✓ passed — কাজ আবার শুরু হচ্ছে\n');
        return true;
      }
      if (st && st.ok && !(st.data.code_left_sec > 0)) {
        try { await rpc(initData, 'leaf.v1.AuthService', 'SendSafetyCheck', 'leaf.v1.SendSafetyCheckRequest', {}, 'leaf.v1.SafetyState'); } catch {}
      }
      const left = st && st.ok ? (st.data.code_left_sec || 0) : 0;
      const tag = left > 0 ? `কোডের মেয়াদ ${left}s বাকি` : 'নতুন কোড চাওয়া হলো';
      if (tag !== last) { console.log('\x1b[36mℹ\x1b[0m ' + tag + ' — অপেক্ষা করছি…'); last = tag; }
      await new Promise((r2) => setTimeout(r2, 15000));
    }
    console.log('\x1b[31m✘\x1b[0m ' + maxMin + ' মিনিটেও কোড আসেনি — এই ফ্লো বন্ধ (আবার চালালে চলবে)\n');
    return false;
  } finally { inSafetyWait = false; }
}

// ── Safety-check bookkeeping (config/safety.json) ──────────────────
const SAFETY_REQUIRED = 'safety_check_required';
const SAFETY_FILE = path.join(CACHE_DIR, 'safety.json');
const safetyHooks = [];
function readSafety() { try { return JSON.parse(fs.readFileSync(SAFETY_FILE, 'utf8')); } catch { return {}; } }
function writeSafety(o) { try { fs.writeFileSync(SAFETY_FILE, JSON.stringify(o, null, 2)); } catch {} }
function onSafety(initData, where) {
  let uid = '';
  try { uid = String(JSON.parse(new URLSearchParams(initData).get('user') || '{}').id || ''); } catch {}
  const st = readSafety();
  const cur = st[uid] || {};
  if (!cur.required) { cur.required = true; cur.firstSeenAt = new Date().toISOString(); }
  cur.lastSeenAt = new Date().toISOString(); cur.where = where;
  st[uid] = cur; writeSafety(st);
  for (const h of safetyHooks) { try { h(uid, where); } catch {} }
}
function onSafetyRequired(fn) { safetyHooks.push(fn); }
function clearSafety(uid) { const st = readSafety(); delete st[String(uid)]; writeSafety(st); }

// ── convenience API surface ────────────────────────────────────────
const api = {
  health: () => rpc('', 'leaf.v1.HealthService', 'Check', 'leaf.v1.CheckRequest', {}, 'leaf.v1.CheckResponse'),
  init: (id, startParam) => rpc(id, 'leaf.v1.AuthService', 'Init', 'leaf.v1.InitRequest', { start_param: startParam || '' }, 'leaf.v1.InitResponse'),
  sync: (id) => rpc(id, 'leaf.v1.AuthService', 'Sync', 'leaf.v1.SyncRequest', {}, 'leaf.v1.SyncResponse'),
  membership: (id) => rpc(id, 'leaf.v1.AuthService', 'Membership', 'leaf.v1.MembershipRequest', {}, 'leaf.v1.MembershipResponse'),
  mineStatus: (id) => rpc(id, 'leaf.v1.MineService', 'Status', 'leaf.v1.MineStatusRequest', {}, 'leaf.v1.MineStatusResponse'),
  minePick: (id, gift) => rpc(id, 'leaf.v1.MineService', 'Pick', 'leaf.v1.PickRequest', { gift }, 'leaf.v1.MineStatusResponse'),
  mineDo: (id, ads) => rpc(id, 'leaf.v1.MineService', 'Mine', 'leaf.v1.MineRequest', ads, 'leaf.v1.MineStatusResponse'),
  mineClaim: (id) => rpc(id, 'leaf.v1.MineService', 'Claim', 'leaf.v1.ClaimRequest', {}, 'leaf.v1.MineStatusResponse'),
  tasks: (id) => rpc(id, 'leaf.v1.ReadService', 'Tasks', 'leaf.v1.TasksRequest', {}, 'leaf.v1.TasksResponse'),
  completeTask: (id, taskId) => rpc(id, 'leaf.v1.TaskService', 'Complete', 'leaf.v1.CompleteTaskRequest', { task_id: taskId }, 'leaf.v1.CompleteTaskResponse'),
  adViewStatus: (id, taskId) => rpc(id, 'leaf.v1.TaskService', 'AdViewStatus', 'leaf.v1.AdViewStatusRequest', { task_id: taskId }, 'leaf.v1.AdViewStatusResponse'),
  startAdView: (id, taskId) => rpc(id, 'leaf.v1.TaskService', 'StartAdView', 'leaf.v1.StartAdViewRequest', { task_id: taskId }, 'leaf.v1.StartAdViewResponse'),
  completeAdView: (id, body) => rpc(id, 'leaf.v1.TaskService', 'CompleteAdView', 'leaf.v1.CompleteAdViewRequest', body, 'leaf.v1.CompleteAdViewResponse'),
  spinStatus: (id) => rpc(id, 'leaf.v1.SpinService', 'Status', 'leaf.v1.SpinStatusRequest', {}, 'leaf.v1.SpinStatusResponse'),
  spin: (id, ads) => rpc(id, 'leaf.v1.SpinService', 'Spin', 'leaf.v1.SpinRequest', ads, 'leaf.v1.SpinResponse'),
  activity: (id, take) => rpc(id, 'leaf.v1.ReadService', 'Activity', 'leaf.v1.ActivityRequest', { take: take || 10 }, 'leaf.v1.ActivityResponse'),
  // games (RunService / ClaimService)
  runOpen: (id, game, mode) => rpc(id, 'leaf.v1.RunService', 'OpenRun', 'leaf.v1.OpenRunRequest', { game, mode: mode || '' }, 'leaf.v1.OpenRunResponse'),
  runStatus: (id, game) => rpc(id, 'leaf.v1.RunService', 'GameStatus', 'leaf.v1.GameStatusRequest', { game }, 'leaf.v1.GameStatusResponse'),
  claimPending: (id, game) => rpc(id, 'leaf.v1.ClaimService', 'PendingClaim', 'leaf.v1.PendingClaimRequest', { game }, 'leaf.v1.PendingClaimResponse'),
  claimsPending: (id) => rpc(id, 'leaf.v1.ClaimService', 'PendingClaims', 'leaf.v1.PendingClaimsRequest', {}, 'leaf.v1.PendingClaimsResponse'),
  claimStart: (id, token) => rpc(id, 'leaf.v1.ClaimService', 'StartClaim', 'leaf.v1.StartClaimRequest', { token }, 'leaf.v1.StartClaimResponse'),
  claimRun: (id, body) => rpc(id, 'leaf.v1.ClaimService', 'ClaimRun', 'leaf.v1.ClaimRunRequest', body, 'leaf.v1.ClaimRunResponse'),
  // quick-tasks (QuickTaskService)
  quickStatus: (id, exclude) => rpc(id, 'leaf.v1.QuickTaskService', 'Status', 'leaf.v1.QuickStatusRequest', { exclude: exclude || [] }, 'leaf.v1.QuickStatusResponse'),
  quickOffer: (id, type) => rpc(id, 'leaf.v1.QuickTaskService', 'Offer', 'leaf.v1.QuickOfferRequest', { type: type || '' }, 'leaf.v1.QuickOfferResponse'),
  quickClaim: (id, type, refId) => rpc(id, 'leaf.v1.QuickTaskService', 'Claim', 'leaf.v1.QuickClaimRequest', { type: type || '', ref_id: refId || '' }, 'leaf.v1.QuickClaimResponse'),
  // read extras
  topInviters: (id) => rpc(id, 'leaf.v1.ReadService', 'TopInviters', 'leaf.v1.TopInvitersRequest', {}, 'leaf.v1.TopInvitersResponse'),
  myReferrals: (id) => rpc(id, 'leaf.v1.ReadService', 'MyReferrals', 'leaf.v1.MyReferralsRequest', {}, 'leaf.v1.MyReferralsResponse'),
  // wallet
  walletOptions: (id) => rpc(id, 'leaf.v1.WalletService', 'Options', 'leaf.v1.WalletOptionsRequest', {}, 'leaf.v1.WalletOptionsResponse'),
  walletHistory: (id, take) => rpc(id, 'leaf.v1.WalletService', 'History', 'leaf.v1.WithdrawHistoryRequest', { take: take || 10 }, 'leaf.v1.WithdrawHistoryResponse'),
  prepareInviteShare: (id) => rpc(id, 'leaf.v1.WalletService', 'PrepareInviteShare', 'leaf.v1.PrepareInviteShareRequest', {}, 'leaf.v1.PrepareShareResponse'),
  // redeem codes
  redeemValidate: (id, code) => rpc(id, 'leaf.v1.RedeemService', 'Validate', 'leaf.v1.ValidateRedeemRequest', { code }, 'leaf.v1.ValidateRedeemResponse'),
  redeemStartAdGate: (id, code) => rpc(id, 'leaf.v1.RedeemService', 'StartAdGate', 'leaf.v1.StartAdGateRequest', { code }, 'leaf.v1.StartAdGateResponse'),
  redeemClaim: (id, body) => rpc(id, 'leaf.v1.RedeemService', 'Claim', 'leaf.v1.ClaimRedeemRequest', body, 'leaf.v1.ClaimRedeemResponse'),
  // GIVEAWAY_V1 — 🎁 Telegram Premium giveaway (নতুন ফিচার): অ্যাড দেখলে points → বেশি chance
  giveawayStatus: (id) => rpc(id, 'leaf.v1.GiveawayService', 'Status', 'leaf.v1.GiveawayStatusRequest', {}, 'leaf.v1.GiveawayStatus'),
  giveawayStartAd: (id) => rpc(id, 'leaf.v1.GiveawayService', 'StartAd', 'leaf.v1.GiveawayStartAdRequest', {}, 'leaf.v1.GiveawayStartAdResponse'),
  giveawayCompleteAd: (id, body) => rpc(id, 'leaf.v1.GiveawayService', 'CompleteAd', 'leaf.v1.GiveawayCompleteAdRequest', body, 'leaf.v1.GiveawayCompleteAdResponse'),
  giveawayLeaderboard: (id) => rpc(id, 'leaf.v1.GiveawayService', 'Leaderboard', 'leaf.v1.GiveawayLeaderboardRequest', {}, 'leaf.v1.GiveawayLeaderboardResponse'),
  giveawayBuy: (id, kind) => rpc(id, 'leaf.v1.GiveawayService', 'Buy', 'leaf.v1.GiveawayBuyRequest', { kind }, 'leaf.v1.GiveawayBuyResponse'),
  // SAFETY_V1 — Quick Safety Check (anti-bot, 4-digit code from @LeafEarnBot) + Boost event (2X)
  safetyStatus: (id) => rpc(id, 'leaf.v1.AuthService', 'SafetyStatus', 'leaf.v1.SafetyStatusRequest', {}, 'leaf.v1.SafetyState'),
  sendSafetyCheck: (id) => rpc(id, 'leaf.v1.AuthService', 'SendSafetyCheck', 'leaf.v1.SendSafetyCheckRequest', {}, 'leaf.v1.SafetyState'),
  verifySafetyCheck: (id, code) => rpc(id, 'leaf.v1.AuthService', 'VerifySafetyCheck', 'leaf.v1.VerifySafetyCheckRequest', { code: String(code) }, 'leaf.v1.VerifySafetyCheckResponse'),
  boost: (id) => rpc(id, 'leaf.v1.ReadService', 'Boost', 'leaf.v1.BoostRequest', {}, 'leaf.v1.BoostState'),
};

module.exports = { api, rpc, loadSigner, waitForSafety, notifyTelegram, GRPC_CODES, SAFETY_REQUIRED, onSafetyRequired, readSafety, clearSafety };
