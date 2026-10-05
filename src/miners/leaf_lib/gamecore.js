// gamecore.js — LeafEarn game auto-players
// Protocol reversed from the official frontend (play.proto + game engines):
//  - SHOOTER / BLOCK_BREAKER: seeded spawn plans (mulberry32) → kill(id)/wave events
//  - SNAKE: kill(collected counter) events
//  - TIC_TAC_TOE: move(cell 0..8), server plays AI, minimax here
//  - WORD_SEARCH: deal contains the solution (placedJson) → kill(wordIndex)
'use strict';

const proto = require('./leafproto');
const { MiniWS } = require('./leafws');

// ── exact frontend PRNG + spawn generators ─────────────────────────
function mulberry32(e) {
  let t = e >>> 0;
  return function () {
    let e = (t = (t + 0x6d2b79f5) >>> 0);
    e = Math.imul(e ^ (e >>> 15), 1 | e);
    e ^= e + Math.imul(e ^ (e >>> 7), 61 | e);
    return ((e ^ (e >>> 14)) >>> 0) / 0x100000000;
  };
}

const ENEMIES = [
  { kind: 'basic', score: 40, minWave: 1 },
  { kind: 'fast', score: 60, minWave: 1 },
  { kind: 'tank', score: 180, minWave: 3 },
  { kind: 'zigzag', score: 80, minWave: 6 },
  { kind: 'splitter', score: 120, minWave: 6 },
  { kind: 'stealth', score: 100, minWave: 9 },
  { kind: 'bomber', score: 140, minWave: 9 },
];

function waveBaseSec(wave) {
  let t = 2.5;
  for (let s = 1; s < wave; s++) t += Math.max(3, 9 - s);
  return t;
}

function buildWave(seed, wave) {
  const a = mulberry32(seed);
  const l = ENEMIES.filter((e) => wave >= e.minWave);
  const r = waveBaseSec(wave);
  const n = 1000 * wave;
  const o = [];
  let h = 0;
  const d = Math.min(6, 3 + Math.floor(wave / 2));
  for (let i = 0; i < d; i++) {
    const e = l[Math.floor(a() * l.length)];
    o.push({ id: n + h++, kind: e.kind, wave, at: +(r + 2 * a()).toFixed(2), score: e.score });
  }
  const c = 2 + Math.floor(3 * a());
  for (let i = 0; i < c; i++) {
    const e = l[Math.floor(a() * l.length)];
    o.push({ id: n + h++, kind: e.kind, wave, at: +(r + 2 + 6 * a()).toFixed(2), score: e.score });
  }
  return o.sort((e, t) => e.at - t.at);
}

const SHADES = { R: 1, P: 1, O: 1, Y: 1, G: 1, L: 1, C: 1, B: 1, V: 1, M: 1, W: 1, K: 1 };
const SHAPES = [
  ['.......GGG.', '.....GGGGG.', '...GGGGLGG.', '..GGGGLGGG.', '.GGGGLGGGG.', '.GGGLGGGG..', '..GLGGGG...', '.L.........'],
  ['..RRR.RRR..', '.RppRRRRRR.', '.RpRrrrrRR.', '.RrrrrrrrR.', '..RrrrrrR..', '...RrrrR...', '....RrR....', '.....R.....'],
  ['...yyyyy...', '..yyyyyyy..', '.yyKyyyKyy.', '.yyKyyyKyy.', '.yyyyyyyyy.', '.yKyyyyyKy.', '..yKKKKKy..', '...yyyyy...'],
  ['..C.....C..', '...C...C...', '..CcccccC..', '.CcWcccWcC.', 'CcccccccccC', 'C.CcccccC.C', 'C.C.....C.C', '...CC.CC...'],
  ['...BBBBB...', '..BWWbWWB..', '.BWbbbbbWB.', 'BBBBBBBBBBB', '.BbbWbWbbB.', '..BbbWbbB..', '...BbbbB...', '....BbB....', '.....B.....'],
  ['Y....Y....Y', 'YY..YYY..YY', 'YYY.YyY.YYY', 'YyyYyyyYyyY', 'YRyyyByyyRY', 'YyyyyyyyyyY', '.YYYYYYYYY.'],
  ['.....P.....', '....PPP....', '....PWP....', 'PPPPpWpPPPP', '.PppWWWppP.', '..PppWppP..', '..PpP.PpP..', '.PpP...PpP.', '.PP.....PP.'],
  ['...MMMMM...', '..MmmmmmM..', '.MmWWmmWWM.', '.MmWKmmWKM.', '.MmmmmmmmM.', '.MmmmmmmmM.', '.MmmmmmmmM.', '.M.Mm.mM.M.'],
  ['......OOOO.', '.....OooO..', '....OooO...', '...OooO....', '..OOOYYOOO.', '.....OooO..', '....OooO...', '...OoO.....', '..OO.......', '.O.........'],
  ['.YYYYYYYYY.', 'YYyyyyyyyYY', 'Y.YyyyyyY.Y', 'Y.YyyWyyY.Y', '.YYyyyyyYY.', '..YyyyyyY..', '....YyY....', '.....Y.....', '...YYYYY...', '..OOOOOOO..'],
];

function tierFor(e) {
  return e === 1 ? { maxHp: 1, rows: 3 }
    : e <= 3 ? { maxHp: 2, rows: 4 }
    : e <= 5 ? { maxHp: 3, rows: 5 }
    : e <= 7 ? { maxHp: 4, rows: 6 }
    : { maxHp: 5, rows: 7 + Math.floor((e - 8) / 2) };
}

function buildLevel(seed, level) {
  const n = mulberry32(seed);
  const { maxHp } = tierFor(level);
  const c = SHAPES[Math.min(SHAPES.length, Math.max(1, level)) - 1];
  const flip = n() < 0.5;
  const blocks = [];
  let u = 0;
  const f = 1000 * level;
  const p = 10 * level * maxHp;
  for (let e = 0; e < c.length; e++) {
    const row = flip ? [...c[e]].reverse().join('') : c[e];
    for (let s = 0; s < 11; s++) {
      const ch = row[s] ?? '.';
      if (ch === '.') continue;
      const up = ch.toUpperCase();
      if (!SHADES[up]) continue;
      const hp = ch === up ? maxHp : Math.max(1, maxHp - 1);
      blocks.push({ id: f + u++, row: e, col: s, hp, maxHp, score: p });
    }
  }
  return { level, blocks, rows: c.length, maxHp };
}

// ── GameSocket (play.proto over MiniWS) ────────────────────────────
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const b64url = (s) => Buffer.from(s, 'utf8').toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

class GameSocket {
  constructor(api, initData, opts) {
    this.api = api;
    this.initData = initData;
    this.opts = opts;
    this.ws = null;
    this.token = '';
    this.slotsLeft = 0;
    this.stake = 0;
    this.adBlockId = '';
    this._waiters = [];
    this._settle = null;
    this._settleData = null;
    this._error = null;
  }

  async connect() {
    // server rejects empty mode with "Something went wrong" — always send "normal"
    const mode = this.opts.mode || 'normal';
    const r = await this.api.runOpen(this.initData, this.opts.game, mode);
    if (!r.ok) throw new Error(r.message || 'openRun failed');
    this.token = r.data.token || '';
    const url = `wss://leafearn.site/ws/v1/game?token=${encodeURIComponent(this.token)}`;
    const ws = new MiniWS(url, ['leaf.play.v1', b64url(this.initData)]);
    this.ws = ws;
    ws.onmessage = (ev) => this._onEvent(ev.data);
    // register ready waiter BEFORE connecting — 'ready' can arrive immediately
    const readyP = new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('ready timeout')), 10000);
      this._waiters.push({
        match: (e) => e.kind === 'ready' || e.kind === 'error',
        fn: (e) => {
          clearTimeout(t);
          if (e.kind === 'error') reject(new Error(e.error.message || 'play error'));
          else {
            this.token = e.ready.token || this.token;
            this.slotsLeft = e.ready.slots_left || 0;
            this.stake = e.ready.stake || 0;
            this.adBlockId = e.ready.ad_block_id || '';
            resolve();
          }
        },
      });
    });
    await ws.connect(12000);
    await readyP;
    return { token: this.token, slotsLeft: this.slotsLeft };
  }

  _onEvent(buf) {
    let ev;
    try { ev = proto.decode('leaf.v1.ServerEvent', buf); } catch (e) { this._decodeErr = e.message; return; }
    const keys = Object.keys(ev).filter((k) => ev[k] !== undefined && ev[k] !== null);
    if (!keys.length) return;
    const kind = keys.find((k) => typeof ev[k] === 'object') || keys[0];
    const e = { [kind]: ev[kind], kind };
    if (kind === 'settled') {
      this._settleData = e;
      if (this._settle) { const s = this._settle; this._settle = null; s.resolve(e); }
    }
    if (kind === 'error') this._error = e.error;
    const remaining = [];
    for (const w of this._waiters) {
      if (w.match(e)) w.fn(e); else remaining.push(w);
    }
    this._waiters = remaining;
    if (this.opts.onEvent) this.opts.onEvent(e);
  }

  wait(match, timeoutMs = 30000) {
    return new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('wait timeout')), timeoutMs);
      this._waiters.push({ match, fn: (e) => { clearTimeout(t); resolve(e); } });
    });
  }

  _emit(field, value) {
    if (!this.ws) return;
    this.ws.send(proto.encode('leaf.v1.ClientEvent', { [field]: value }));
  }

  kill(id) { this._emit('kill', { id }); }
  powerup(id) { this._emit('powerup', { id }); }
  wave(w) { this._emit('wave', { wave: w }); }
  move(cell) { this._emit('move', { cell }); }
  pause() { this._emit('pause', {}); }
  resume() { this._emit('resume', {}); }
  adContinue(shown, clicked) { this._emit('ad_continue', { ads_shown: shown, ads_clicked: clicked }); }

  end(reason) {
    return new Promise((resolve) => {
      if (this._settleData) return resolve(this._settleData);
      this._settle = { resolve };
      this._emit('end', { reason: reason || 'death' });
      setTimeout(() => { if (this._settle) { const s = this._settle; this._settle = null; s.resolve(null); } }, 10000);
    });
  }

  close() { if (this.ws) { this.ws.close(); this.ws = null; } }
}

// ── TIC_TAC_TOE — minimax ──────────────────────────────────────────
const WINS = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];

function tttWinner(b) {
  for (const [x, y, z] of WINS) if (b[x] && b[x] === b[y] && b[x] === b[z]) return b[x];
  return b.every((c) => c) ? 'draw' : null;
}

function tttMinimax(b, me, turn, depth) {
  const w = tttWinner(b);
  if (w === me) return 10 - depth;
  if (w && w !== 'draw') return depth - 10;
  if (w === 'draw') return 0;
  let best = turn === me ? -Infinity : Infinity;
  for (let i = 0; i < 9; i++) {
    if (b[i]) continue;
    b[i] = turn;
    const score = tttMinimax(b, me, turn === 'O' ? 'X' : 'O', depth + 1);
    b[i] = null;
    best = turn === me ? Math.max(best, score) : Math.min(best, score);
  }
  return best;
}

function tttBestMove(b, me) {
  let best = -Infinity, moves = [];
  for (let i = 0; i < 9; i++) {
    if (b[i]) continue;
    b[i] = me;
    const score = tttMinimax(b, me, me === 'O' ? 'X' : 'O', 1);
    b[i] = null;
    if (score > best) { best = score; moves = [i]; }
    else if (score === best) moves.push(i);
  }
  return moves[Math.floor(Math.random() * moves.length)];
}

async function playTicTacToe(api, initData, log) {
  const sock = new GameSocket(api, initData, { game: 'TIC_TAC_TOE' });
  const first = new Promise((resolve) => { sock._firstBoard = resolve; });
  const origOn = sock.opts.onEvent;
  sock.opts.onEvent = (e) => {
    if (e.kind === 'board') {
      if (sock._firstBoard) { const f = sock._firstBoard; sock._firstBoard = null; f(e.board); }
    }
    if (origOn) origOn(e);
  };
  await sock.connect();
  const initBoard = await first;
  let board = [...initBoard.board].map((c) => (c === '-' ? null : c));
  let myMark = null, result = '', over = false, moves = 0;
  while (!over && moves < 9) {
    if (myMark) {
      const mv = tttBestMove(board, myMark);
      if (mv === undefined) break;
      await sleep(700 + Math.random() * 1800);
      sock.move(mv);
    } else {
      // first move: random corner-ish, then detect our mark
      const free = board.map((c, i) => (c ? -1 : i)).filter((i) => i >= 0);
      const mv = free[Math.floor(Math.random() * free.length)];
      await sleep(700 + Math.random() * 1200);
      sock.move(mv);
    }
    const ev = await sock.wait((e) => e.kind === 'board' || e.kind === 'settled', 20000);
    if (ev.kind === 'settled') break;
    board = [...ev.board.board].map((c) => (c === '-' ? null : c));
    result = ev.board.result || '';
    over = !!ev.board.over;
    if (!myMark) {
      // whichever mark occupies more cells is ours (we moved first)
      const x = board.filter((c) => c === 'X').length;
      const o = board.filter((c) => c === 'O').length;
      myMark = x > o ? 'X' : 'O';
    }
    moves++;
  }
  const settled = over ? await new Promise((resolve) => {
    if (sock._settleData) return resolve(sock._settleData);
    sock._settle = { resolve };
    setTimeout(() => resolve(null), 12000);
  }) : await sock.end('death');
  sock.close();
  return { settled: (settled && settled.settled) || null, token: sock.token, result, moves, mark: myMark };
}

// ── WORD_SEARCH — solution is in the deal ──────────────────────────
// WS_MODE_PATCHED — frontend sends mode EASY|MEDIUM|HARD (DIFF table: 120/260/500 leaf). "normal" = unpaid → reward 0
async function playWordSearch(api, initData, log, s) {
  const mode = String((s && s.wsMode) || process.env.WS_MODE || "HARD").toUpperCase();
  const sock = new GameSocket(api, initData, { game: "WORD_SEARCH", mode });
  const dealP = new Promise((resolve) => { sock._deal = resolve; });
  const origOn = sock.opts.onEvent;
  sock.opts.onEvent = (e) => {
    if (e.kind === "deal" && sock._deal) { const d = sock._deal; sock._deal = null; d(e.deal); }
    if (origOn) origOn(e);
  };
  await sock.connect();
  const deal = await Promise.race([dealP, sleep(15000).then(() => null)]);
  if (!deal) { sock.close(); throw new Error("WS: no deal within 15s (mode " + mode + ")"); }
  const placed = JSON.parse(deal.placed_json || "{}");
  const words = deal.words || [];
  // human-ish: longer words take longer to spot; shuffle order a bit
  const order = words.map((w, i) => i).sort(() => Math.random() - 0.5);
  await sleep(2000 + Math.random() * 2000);
  for (const i of order) {
    const w = String(words[i] || "");
    await sleep(1800 + w.length * 450 + Math.random() * 2600);
    sock.kill(i); // frontend: kill(words.indexOf(word))
  }
  await sleep(1200 + Math.random() * 1500);
  const settled = await sock.end("done");
  sock.close();
  return { settled: (settled && settled.settled) || null, token: sock.token, words: words.length, placed: Object.keys(placed).length, mode };
}

// ── SNAKE — sequential eat counters ────────────────────────────────
async function playSnake(api, initData, log, s) {
  const sock = new GameSocket(api, initData, { game: 'SNAKE', mode: 'normal' });
  await sock.connect();
  const target = (s.snakeEatsMin || 8) + Math.floor(Math.random() * ((s.snakeEatsMax || 14) - (s.snakeEatsMin || 8) + 1));
  for (let i = 1; i <= target; i++) {
    await sleep(2200 + Math.random() * 3200);
    sock.kill(i); // frontend: onEat(collected) → kill(counter)
  }
  await sleep(800 + Math.random() * 1200);
  const settled = await sock.end('death');
  sock.close();
  return { settled: (settled && settled.settled) || null, token: sock.token, eats: target };
}

// ── SHOOTER — replay the seeded spawn plan ─────────────────────────
async function playShooter(api, initData, log, s) {
  const sock = new GameSocket(api, initData, { game: 'SHOOTER' });
  const t0 = Date.now();
  let wavesSeen = 0;
  const timers = [];
  const pendingByWave = new Map();
  sock.opts.onEvent = (e) => {
    if (e.kind !== 'wave_seed') return;
    const { wave, seed } = e.wave_seed;
    wavesSeen = wave;
    const plan = buildWave(Number(seed) >>> 0, wave);
    pendingByWave.set(wave, plan.length);
    for (const u of plan) {
      const at = u.at * 1000 - (Date.now() - t0) + 400 + Math.random() * 1100;
      timers.push(setTimeout(() => {
        sock.kill(u.id);
        const left = (pendingByWave.get(wave) || 1) - 1;
        pendingByWave.set(wave, left);
        if (left <= 0) setTimeout(() => sock.wave(wave), 600 + Math.random() * 900);
      }, Math.max(250, at)));
    }
  };
  await sock.connect();
  const targetWaves = s.shooterWaves || 6;
  // wait until target wave completed (or hard cap 6 min)
  const deadline = Date.now() + 360000;
  while (wavesSeen < targetWaves && Date.now() < deadline) await sleep(2000);
  // let scheduled kills of the last wave land
  await sleep(9000);
  for (const t of timers) clearTimeout(t);
  const settled = await sock.end('death');
  sock.close();
  return { settled: (settled && settled.settled) || null, token: sock.token, waves: wavesSeen };
}

// ── BLOCK_BREAKER — replay seeded level plans ──────────────────────
async function playBlockBreaker(api, initData, log, s) {
  const sock = new GameSocket(api, initData, { game: 'BLOCK_BREAKER' });
  let levelSeen = 0;
  const chain = [];
  sock.opts.onEvent = (e) => {
    if (e.kind !== 'wave_seed') return;
    const { wave: level, seed } = e.wave_seed;
    levelSeen = Math.max(levelSeen, level);
    chain.push((async () => {
      const plan = buildLevel(Number(seed) >>> 0, level);
      for (const b of plan.blocks) {
        await sleep(550 + Math.random() * 950);
        sock.kill(b.id);
      }
      await sleep(800 + Math.random() * 900);
      sock.wave(level);
    })());
  };
  await sock.connect();
  const maxLevel = s.bbMaxLevel || 10;
  const deadline = Date.now() + 600000;
  while (levelSeen < maxLevel && Date.now() < deadline) await sleep(2500);
  await Promise.allSettled(chain);
  const victory = levelSeen >= 10;
  const settled = await sock.end(victory ? 'victory' : 'death');
  sock.close();
  return { settled: (settled && settled.settled) || null, token: sock.token, levels: levelSeen, victory };
}

// ── dispatcher ─────────────────────────────────────────────────────
const PLAYERS = {
  TIC_TAC_TOE: { fn: playTicTacToe, label: 'Tic-Tac-Toe' },
  WORD_SEARCH: { fn: playWordSearch, label: 'Word Search' },
  SNAKE: { fn: playSnake, label: 'Snake' },
  SHOOTER: { fn: playShooter, label: 'Leaf Shooter' },
  BLOCK_BREAKER: { fn: playBlockBreaker, label: 'Block Breaker' },
};

async function playGame(gameId, api, initData, log, s) {
  const p = PLAYERS[gameId];
  if (!p) throw new Error('unknown game ' + gameId);
  return p.fn(api, initData, log, s);
}

module.exports = { playGame, PLAYERS, buildWave, buildLevel, mulberry32 };
