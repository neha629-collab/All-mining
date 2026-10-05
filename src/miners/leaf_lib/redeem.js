// redeem.js — প্রোমো কোড রিডিম (চ্যানেলে যে কোড দেয়)
// frontend (2c_5by4_-vv43.js ex()): validate(code) → startAdGate(code) → showAdsgramAd(providerRef) → claim{code, adToken, adsShown, adsClicked, adsOffered}
'use strict';
const { doAdShow, creditNote } = require('./adsgram');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const ERRORS = {
  ad_gate_failed: "Ad didn't complete — try again.",
  no_ad: 'No ad available right now',
};

async function redeemCode(api, initData, code) {
  const c = String(code || '').trim().toUpperCase();
  if (!c) return { ok: false, message: 'Enter a code first.' };
  const v = await api.redeemValidate(initData, c);
  if (!v.ok) return { ok: false, stage: 'validate', message: v.message };
  const g = await api.redeemStartAdGate(initData, c);
  if (!g.ok) return { ok: false, stage: 'adgate', message: ERRORS[g.message] || g.message };
  let show = await doAdShow(initData, g.data.provider_ref);
  if (!show.ok) { await sleep(3000); show = await doAdShow(initData, g.data.provider_ref); }
  if (!show.ok) return { ok: false, stage: 'show', message: show.noFill ? 'no ad fill' : 'show failed' };
  await sleep(2500);
  let last;
  for (let k = 0; k < 3; k++) {
    last = await api.redeemClaim(initData, { code: c, ad_token: g.data.token, ads_shown: 1, ads_clicked: 1, ads_offered: Math.max(1, show.offered || 1) });
    if (last.ok) return { ok: true, reward: Number(last.data.reward), balance: Number(last.data.balance), note: creditNote(last.data), expected: Number(v.data.reward || 0) };
    if (!/went wrong|unavailable|timeout/i.test(last.message || '')) break;
    await sleep(3000);
  }
  return { ok: false, stage: 'claim', message: ERRORS[last.message] || last.message };
}

module.exports = { redeemCode };
