// adsgram.js — CRACKED Adsgram ad-show simulator (sad.min.js 2.2.5 ফুল রিভার্সড) + ADEXIUM অটো-ট্রাই
// জিতের ফর্মুলা: startAdView(লিফ) → doAdShow(এখানে) → completeAdView{ads_clicked:1, ad_id:showRecord}
// ফ্রন্টএন্ড (3uf4p4jqwdu2c.js): /event?type=Show আর type=Click-এর record= গুনে {shown, clicked} বানায় —
// সার্ভার credited < base দেয় যদি clicked < shown (nudgeEarnMore) → তাই "ট্যাপ" (click বিকন) বাধ্যতামূলক।
'use strict';
const crypto = require('crypto');

const HMAC_KEY_STR = 'qK8FwLlQdPDlAXzvMJIdZJsvFtXIQBea'; // sad.min.js থেকে ডিকোডড
const UA = 'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.230 Mobile Safari/537.36';
const DEFAULT_BLOCK = '48006';
const ADX_WID_DEFAULT = '46ed9346-3a71-48d8-b7d2-6da0accbc5f7'; // task #6 provider_ref

function dataCheckString(initData) {
  const params = new URLSearchParams(initData);
  const exclude = new Set(['hash', 'signature']);
  const parts = [];
  for (const [k, v] of params) if (!exclude.has(k)) parts.push(k + '=' + v);
  parts.sort(new Intl.Collator('en').compare);
  return Buffer.from(parts.join('\n'), 'utf8').toString('base64') // \n জয়েন — এটাই আসল!
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function rotatedKey() {
  const hour = Math.floor(Math.floor(Date.now() / 1000) / 3600);
  return Buffer.from([...HMAC_KEY_STR].map((c, i) => c.charCodeAt(0) ^ ((hour + i) % 256)));
}
function sign(params) {
  return crypto.createHmac('sha256', rotatedKey()).update(params.toString()).digest('hex');
}
// sad.min.js qt(): blockId-এর 'int-'/'task-' প্রিফিক্স কেটে /adv-এ শুধু সংখ্যা যায় (int-50008 → 50008)
const normBlock = (v) => String(v || '').replace(/^(int-|task-)/, '');
const isBlockId = (v) => /^\d{3,8}$/.test(normBlock(v));

// সাইনড /adv — রেকর্ড-ব্লবসহ ট্র্যাকিং URL দেয়
async function adv(initData, blockId = DEFAULT_BLOCK) {
  const iu = new URLSearchParams(initData);
  const user = JSON.parse(iu.get('user') || '{}');
  const q = new URLSearchParams();
  q.set('envType', 'telegram');
  q.set('blockId', isBlockId(blockId) ? normBlock(blockId) : DEFAULT_BLOCK);
  q.set('platform', 'Linux armv81');
  q.set('language', user.language_code || 'en');
  q.set('top_domain', 'leafearn.site');
  q.set('signature', iu.get('signature') || '');
  q.set('data_check_string', dataCheckString(initData));
  q.set('sdk_version', '2.2.5');
  q.set('tg_id', String(user.id));
  q.set('tg_platform', 'android');
  q.set('tma_version', '9.6');
  q.set('request_id', crypto.randomBytes(12).toString('hex'));
  q.set('raw', sign(q));
  const res = await fetch('https://api.adsgram.ai/adv?' + q.toString(), {
    method: 'GET', cache: 'no-cache',
    headers: { origin: 'https://leafearn.site', referer: 'https://leafearn.site/', 'user-agent': UA },
    signal: AbortSignal.timeout(20000),
  });
  return res.json();
}

async function fire(url) {
  if (!url) return 0;
  try { return (await fetch(url, { cache: 'no-cache', headers: { referer: 'https://leafearn.site/', 'user-agent': UA }, signal: AbortSignal.timeout(15000) })).status; }
  catch { return 0; }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// এক অ্যাড "দেখা" — render→show→(ওয়াচ)→click(=ট্যাপ)→reward→return; show/click রেকর্ড ফেরত দেয়
async function doAdShow(initData, blockId) {
  let a;
  try { a = await adv(initData, blockId); } catch (e) { return { ok: false, noFill: false, error: e.message }; }
  const b = a && a.banners && a.banners[0];
  if (!b) return { ok: false, noFill: true };
  const T = {};
  for (const t of (b.banner.trackings || [])) T[t.name] = t.value;
  const showRec = T.show ? new URL(T.show).searchParams.get('record') : '';
  const clickRec = T.click ? new URL(T.click).searchParams.get('record') : '';
  await fire(T.render); await sleep(1000);
  await fire(T.show); await sleep(7000);   // "দেখার" সময়
  await fire(T.click); await fire(T.reward); await sleep(600); // click = ট্যাপ
  await fire(T.return);
  return { ok: true, showRec, clickRec, offered: (a.banners || []).length };
}

// ক্রেডিট ফুল কিনা (frontend nudgeEarnMore-এর উল্টো শর্ত)
function creditNote(d) {
  if (!d) return '';
  const full = Number(d.reward) >= Number(d.base || 0) && Number(d.ads_clicked || 0) >= Number(d.ads_shown || 0);
  return ' (base ' + d.base + ', div ' + d.divisor + ', tap ' + d.ads_clicked + '/' + d.ads_shown + ' → ' + (full ? 'FULL ✓' : 'PARTIAL ✗') + ')';
}

// একটা অ্যাড-ভিউ ক্লেম: startAdView → শো → completeAdView (জিতের ফর্মুলা)
async function completeOneView(api, initData, taskId, log) {
  const sv = await api.startAdView(initData, String(taskId));
  if (!sv.ok) return { ok: false, message: sv.message };
  const show = await doAdShow(initData);
  if (!show.ok) return { ok: false, message: show.noFill ? 'No available ad' : 'show failed' };
  await sleep(3000);
  const cv = await api.completeAdView(initData, {
    token: sv.data.token,
    ads_shown: 1,
    ads_clicked: 1,          // ← বাধ্যতামূলক (ট্যাপ)!
    ad_id: show.showRec,     // ← show রেকর্ড ব্লব!
    ads_offered: 1,
  });
  if (cv.ok && log) log('  ✅ +' + cv.data.reward + creditNote(cv.data) + ' bal=' + cv.data.balance);
  return cv;
}

async function simulateAdView(initData, blockId, opts = {}) {
  const r = await doAdShow(initData, blockId);
  if (!r.ok) return { ok: false, detail: r.noFill ? 'no fill' : 'show failed', fired: [] };
  const fired = ['render', 'show', 'click', 'reward', 'return'];
  return { ok: true, fired, showRec: r.showRec, clickRec: r.clickRec, shown: 1, clicked: opts.clicked ? 1 : 0, offered: 1 };
}

// ── ADEXIUM (tgads) — ADX_FULLBODY_V2 ──
// উইজেট v1.81 (adexium-widget.min.js): body = {...user(getUser: from:'window'), adFormat, motivated, version, af, afV2}
// ফিল না এলে Leaf-এর আসল ইউজারও "No ad" পায়। ডেটাসেন্টার IP-তে ফিল আসে না; ঐচ্ছিক ADX_PROXY (যেমন WARP http proxy) দিয়ে বিড/ইভেন্ট পাঠানো যায়।
const { execFile } = require('child_process');
const ADX_UA = 'Mozilla/5.0 (Linux; Android 13; SM-S918B Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.230 Mobile Safari/537.36 Telegram-Android/11.2.3';

function adxBody(initData, wid) {
  const iu = new URLSearchParams(initData);
  const u = JSON.parse(iu.get('user') || '{}');
  return {
    wid: wid || ADX_WID_DEFAULT, adFormat: 'interstitial', tz: 3,
    language: u.language_code || 'en', isPremium: u.is_premium || false,
    lastName: u.last_name || '', username: u.username || '', firstName: u.first_name || '',
    telegramId: Number(u.id), platform: 'android', serialized: JSON.stringify(u), from: 'window',
    initData, tonConnected: false, motivated: false, version: 1.81, af: 0, afV2: 0,
  };
}

// একই রুটে (প্রক্সি থাকলে প্রক্সি) সব adexium রিকোয়েস্ট — ইম্প্রেশন/ক্লিকের IP বিডের সাথে মেলে
function adxHttp(url, { method = 'GET', body = null } = {}) {
  const proxy = process.env.ADX_PROXY || '';
  if (!proxy) {
    return fetch(url, { method, body, headers: { origin: 'https://leafearn.site', referer: 'https://leafearn.site/', 'user-agent': ADX_UA }, redirect: 'manual', signal: AbortSignal.timeout(15000) })
      .then(async (r) => ({ status: r.status, body: await r.text() })).catch(() => ({ status: 0, body: '' }));
  }
  return new Promise((resolve) => {
    const args = ['-s', '-m', '20', '-x', proxy, '-X', method, url, '-H', 'origin: https://leafearn.site', '-H', 'referer: https://leafearn.site/', '-H', 'user-agent: ' + ADX_UA, '-w', '\n__S__%{http_code}'];
    if (body !== null) args.push('-H', 'content-type: text/plain;charset=UTF-8', '--data-binary', body);
    execFile('curl', args, { maxBuffer: 8 << 20 }, (e, out) => {
      const t = String(out || ''); const k = t.lastIndexOf('\n__S__');
      resolve({ body: k >= 0 ? t.slice(0, k) : t, status: Number(k >= 0 ? t.slice(k + 6) : 0) });
    });
  });
}

async function adexiumBid(initData, wid, tries = 1) {
  for (let i = 0; i < tries; i++) {
    if (i) await sleep(2500);
    const r = await adxHttp('https://bid.tgads.live/bid-request', { method: 'POST', body: JSON.stringify(adxBody(initData, wid)) });
    try { const j = JSON.parse(r.body); if (Array.isArray(j) && j.length) return j[0]; } catch {}
  }
  return null;
}

// উইজেটের ট্যাপ-সিকোয়েন্স: displayAd → fetch(notificationUrl) → (ট্যাপ) instantView ? fetch(clickNotificationUrl) : open(clickUrl) → complete
async function adexiumTap(ad) {
  await adxHttp(ad.notificationUrl);
  await sleep(5000 + Math.random() * 3000);
  if (ad.instantView && ad.clickNotificationUrl) await adxHttp(ad.clickNotificationUrl);
  if (ad.clickUrl && !String(ad.clickUrl).startsWith('https://t.me/')) await adxHttp(ad.clickUrl);
  await sleep(4000);
}

// ADX_FALLBACK_V1 (frontend 2026-09-27, 2jjgy57ppwg0r.js): showAdexiumAd() ফিল না দিলে
//   "adexium no fill → adsgram interstitial": showAdsgramAd("int-50008") →
//   completeAdView{token, adsShown:max(1,shown), adsClicked, adsOffered, adId:"", adsgramFallback:true}
const ADX_FALLBACK_BLOCK = 'int-50008';
async function adexiumFallbackView(api, initData, taskId) {
  const sv = await api.startAdView(initData, String(taskId));
  if (!sv.ok) return { ok: false, message: 'startAdView: ' + sv.message };
  let show = await doAdShow(initData, ADX_FALLBACK_BLOCK);
  if (!show.ok) { await sleep(4000); show = await doAdShow(initData, ADX_FALLBACK_BLOCK); }
  if (!show.ok) return { ok: false, noFill: true, message: 'adsgram interstitial (int-50008) no fill' };
  await sleep(2500);
  const cv = await api.completeAdView(initData, {
    token: sv.data.token, ads_shown: 1, ads_clicked: 1, ads_offered: Math.max(1, show.offered || 1),
    ad_id: '', adsgram_fallback: true,
  });
  if (cv.ok) return { ok: true, reward: cv.data.reward, data: cv.data, via: 'adsgram-fallback' };
  return { ok: false, message: cv.message };
}

async function adexiumView(api, initData) {
  const ts = await api.tasks(initData);
  const t = ((ts.ok && ts.data.tasks) || []).find((x) => x.type === 'ADEXIUM' && !x.completed && !x.locked && (x.views_used || 0) < (x.max_views || 0));
  if (!t) return { ok: false, skip: true, message: 'no open ADEXIUM task' };
  // ঐচ্ছিক: আসল Adexium বিড (ডিফল্ট বন্ধ — ডেটাসেন্টার IP-তে ফিল আসে না, আর ফিল এলেও Leaf ভেরিফাই করে না)
  if (process.env.ADX_TRY_BID === '1') {
    const ad = await adexiumBid(initData, ADX_WID_DEFAULT, Number(process.env.ADX_TRIES || 1));
    if (ad) {
      const sv = await api.startAdView(initData, String(t.id));
      if (sv.ok) {
        await adexiumTap(ad);
        const cv = await api.completeAdView(initData, { token: sv.data.token, ads_shown: 1, ads_clicked: 1, ad_id: String(ad.id ?? ''), ads_offered: 0 });
        if (cv.ok) return { ok: true, reward: cv.data.reward, data: cv.data, via: 'adexium' };
      }
    }
  }
  // ফ্রন্টএন্ডের নিজস্ব ফলব্যাক — Adsgram interstitial দিয়ে ADEXIUM টাস্ক ক্রেডিট
  return adexiumFallbackView(api, initData, t.id);
}

module.exports = { adv, doAdShow, completeOneView, dataCheckString, simulateAdView, adexiumBid, adexiumView, adexiumFallbackView, adexiumTap, adxBody, creditNote, isBlockId, normBlock };
