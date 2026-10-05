// autopilot.js — পূর্ণ অটোপাইলট: প্রতিটা কাজ সার্ভারের আসল রিসেট-টাইম ধরে চালায়
//   mine  → mineTick-এর nextCheckSec (HEART ট্যাপ ~৪০ মিনিট পরপর)
//   spin  → SpinStatus.next_spin_ms
//   games → GameStatus.next_slot_at_ms (রোলিং ২৪ঘণ্টা, প্রতি গেমে ৬ স্লট)
//   ads   → Task.next_reset_at_ms (ADSGRAM/MONETAG ১২ঘণ্টা রিসেট) + QuickStatus.next_at_ms + ADEXIUM বিড রিট্রাই
//   task  → মিশন প্রতি ৬ ঘণ্টায় একবার চেক (#2 BIO/#11 ইউজার-অ্যাকশনের পর অটো ক্লেম)
'use strict';

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const JOBS = ['mine', 'spin', 'ads', 'gv', 'games', 'task'];

async function spinDueAt(api, id) {
  const r = await api.spinStatus(id);
  if (!r.ok) return Date.now() + 30 * 60e3;
  if (r.data.can_spin) return Date.now();
  return Date.now() + Number(r.data.next_spin_ms || 30 * 60e3) + 20e3;
}

async function nextGamesAt(api, id, games) {
  const now = Date.now();
  let best = Infinity;
  for (const g of games) {
    const r = await api.runStatus(id, g);
    if (!r.ok) continue;
    const used = r.data.slots_used || 0, cap = r.data.slots_cap || 0;
    const nx = Number(r.data.next_slot_at_ms || 0);
    if (cap && used < cap && (!nx || nx <= now)) return now + 90e3; // ফ্রি স্লট আছে
    if (nx) best = Math.min(best, nx);
  }
  return best === Infinity ? now + 3600e3 : best + 20e3;
}

async function nextAdsAt(api, id) {
  const now = Date.now();
  let best = Infinity;
  const ts = await api.tasks(id);
  for (const t of (ts.ok && ts.data.tasks) || []) {
    if (!['ADSGRAM', 'MONETAG', 'ADEXIUM', 'TOWER', 'LINK'].includes(t.type) || t.completed) continue;
    const reset = Number(t.next_reset_at_ms || 0);
    const open = (t.views_used || 0) < (t.max_views || 0);
    if (t.locked && reset) best = Math.min(best, reset + 15e3);
    else if (!t.locked && open) best = Math.min(best, now + 20 * 60e3); // ফিল নেই → পরে রিট্রাই
  }
  const qs = await api.quickStatus(id, []);
  if (qs.ok) {
    const nq = Number(qs.data.next_at_ms || 0);
    if (nq > now) best = Math.min(best, nq + 15e3);
    else if (qs.data.has_task) best = Math.min(best, now + 60 * 60e3);
  }
  return best === Infinity ? now + 2 * 3600e3 : clamp(best, now + 5 * 60e3, now + 12 * 3600e3);
}

// ── GIVEAWAY_V1: 🎁 Telegram Premium giveaway-এর পরের সুযোগ কখন ──
async function nextGvAt(api, id) {
  const st = await api.giveawayStatus(id).catch(() => null);
  if (!st || !st.ok || !st.data.has_event) return Date.now() + 6 * 3600e3;
  const now = Date.now();
  const until = Math.max(Number(st.data.break_until_ms || 0), Number(st.data.cooldown_until_ms || 0));
  if (until > now) return until + 15e3;     // break/cooldown শেষ হলে
  return now + 90e3;                        // এখনই খেলা যাচ্ছে → একটু পরে আরেক ব্যাচ
}

async function autopilot(d, s) {
  const { api, loadAccounts, ensureAuth, mineTick, flowSpin, flowGames, flowAdcrack, flowTask, flowGiveaway, log, ok, err, info, fmtMs, sleep, PLAYERS } = d;
  const games = (s.gamesList || Object.keys(PLAYERS)).filter((g) => PLAYERS[g]);
  const due = new Map();
  const get = (k) => due.get(k) || 0;
  log('system', info('🤖 AUTOPILOT চালু — mine · spin · ads(১২ঘ রিসেট) · quick · games(সব স্লট) · claims · missions — Ctrl+C = বন্ধ'), true);

  while (true) {
    const accs = loadAccounts();
    if (!accs.length) { log('system', err('কোনো enabled অ্যাকাউন্ট নেই'), true); return; }
    for (const acc of accs) {
      if (!acc.initData || acc.initData.startsWith('PASTE_')) continue;
      const id = acc.initData;
      const K = (j) => acc.name + ':' + j;
      try {
        if (!(await ensureAuth(acc))) {
          log(acc.name, err('auth fail — initData মেয়াদোত্তীর্ণ? নতুন লিংক দাও (tmp_url.txt → node tmp_newinit.js)'));
          for (const j of JOBS) due.set(K(j), Date.now() + 15 * 60e3);
          continue;
        }
        // SAFETY_GATE_V1 — সার্ভার safety_check_required দিলে কোড ভেরিফাই না হওয়া পর্যন্ত সব কাজ থামাও (৫ মিনিট পরপর চেক)
        const L = require('./leafapi');
        const uid = String(acc.tgId || (() => { try { return JSON.parse(new URLSearchParams(id).get('user') || '{}').id; } catch { return ''; } })());
        if ((L.readSafety()[uid] || {}).required) {
          const st = await api.safetyStatus(id);
          if (st.ok && st.data.passed) { L.clearSafety(uid); log(acc.name, ok('🛡 Safety Check পাস — কাজ আবার চালু')); }
          else {
            log(acc.name, err('🛡 Safety Check বাকি → Telegram-এ @LeafEarnBot-এর কোড দেখে Safety Console-এ দিন (বা ফোনে Leaf অ্যাপে কোড দিন)'));
            if (!global.__safetyNotifyAt || Date.now() - global.__safetyNotifyAt > 10 * 60e3) {
              global.__safetyNotifyAt = Date.now();
              try { require('./leafapi').notifyTelegram('🛡 <b>Leaf: Safety কোড দরকার</b>\nঅটোপাইলট আটকে আছে — @LeafEarnBot-এর ৪-ডিজিট কোডটা Safety Console-এ দিন, বট নিজেই চলবে।').catch(() => {}); } catch {}
            }
            for (const j of JOBS) due.set(K(j), Date.now() + 5 * 60e3);
            continue;
          }
        }
        if (get(K('mine')) <= Date.now()) {
          const r = await mineTick(acc, s);
          due.set(K('mine'), Date.now() + 1000 * clamp((r && r.nextCheckSec) || 600, 45, 3 * 3600));
        }
        if (get(K('spin')) <= Date.now()) {
          if ((await spinDueAt(api, id)) <= Date.now()) await flowSpin(acc, s);
          due.set(K('spin'), await spinDueAt(api, id));
        }
        if (get(K('ads')) <= Date.now()) {
          await flowAdcrack(acc, s);
          due.set(K('ads'), await nextAdsAt(api, id));
        }
        if (flowGiveaway && get(K('gv')) <= Date.now() && !(s.giveaway && s.giveaway.enabled === false)) {
          const gvr = await flowGiveaway(acc, s);           // 🎁 Premium giveaway — ads → points
          // অ্যাড হলেই দ্রুত আবার; না হলে ৩০ মিনিট পরে (নাহলে লুপ আটকে থাকে)
          due.set(K('gv'), Date.now() + (gvr && gvr.ads > 0 ? 90e3 : 30 * 60e3));
        }
        if (get(K('games')) <= Date.now()) {
          // GAMES_BUDGET_V1: এক লুপে অল্প গেম — তারপর mine/ads আবার চেক (মাইন-ট্যাপ দেরি হয় না)
          await flowGames(acc, { ...s, _gameBudget: Number(s.gamesPerLoop || 3) });
          due.set(K('games'), Math.max(Date.now() + 30e3, await nextGamesAt(api, id, games)));
        }
        if (get(K('task')) <= Date.now()) {
          await flowTask(acc, s);
          due.set(K('task'), Date.now() + 6 * 3600e3);
        }
      } catch (e) {
        log(acc.name, err('autopilot: ' + e.message));
        for (const j of JOBS) if (get(K(j)) <= Date.now()) due.set(K(j), Date.now() + 5 * 60e3);
      }
      const sched = JOBS.map((j) => j + ' ' + fmtMs(Math.max(0, get(K(j)) - Date.now()))).join(' · ');
      log(acc.name, info('⏱ পরের কাজ → ' + sched));
    }
    const nextAt = due.size ? Math.min(...due.values()) : Date.now() + 60e3;
    const wait = clamp(nextAt - Date.now(), 30e3, 15 * 60e3) + Math.floor(Math.random() * 15e3);
    log('system', ok('autopilot ঘুম ' + fmtMs(wait)), true);
    await sleep(wait);
  }
}

module.exports = { autopilot, nextAdsAt, nextGamesAt, spinDueAt, nextGvAt };
