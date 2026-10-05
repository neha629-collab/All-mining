// leafproto.js — minimal protobuf codec (proto3) driven by lib/leafschema.json
// Schema generated from leafearn.site embedded leaf/v1/*.proto descriptors.
// Zero dependencies — pure Node.js.
'use strict';

const SCHEMA = require('./leafschema.json');

// wire type per proto type
const WIRE = {
  double: 1, fixed64: 6, sfixed64: 16,
  float: 2, fixed32: 7, sfixed32: 15,
  string: 2, bytes: 2, message: 2, group: 2,
}; // default 0 = varint (int32/int64/uint32/uint64/sint/bool/enum)

function toBig(v) {
  if (typeof v === 'bigint') return v;
  if (typeof v === 'boolean') return v ? 1n : 0n;
  return BigInt(v);
}

function encodeVarint(n) {
  let v = toBig(n);
  const out = [];
  do {
    const b = Number(v & 0x7fn);
    v >>= 7n;
    out.push(v ? b | 0x80 : b);
  } while (v);
  return Buffer.from(out);
}

function decodeVarint(buf, pos) {
  let result = 0n, shift = 0n, b;
  do {
    b = buf[pos++];
    if (pos > buf.length) throw new Error('premature EOF in varint');
    result |= BigInt(b & 0x7f) << shift;
    shift += 7n;
  } while (b & 0x80);
  return [result, pos];
}

function varintToJs(v, type) {
  if (type === 'bool') return v !== 0n;
  if (v <= BigInt(Number.MAX_SAFE_INTEGER) && v >= BigInt(-Number.MAX_SAFE_INTEGER)) return Number(v);
  return v.toString(); // big int64 as string
}

function msgDefs(name) {
  const defs = SCHEMA.schema[name];
  if (!defs) throw new Error('unknown message type: ' + name);
  return defs;
}

function lookupField(defs, key) {
  if (defs[key]) return [key, defs[key]];
  // accept lowerCamelCase too (protobuf-es localName style): adsShown → ads_shown
  const snake = key.replace(/[A-Z]/g, (c) => '_' + c.toLowerCase());
  if (defs[snake]) return [snake, defs[snake]];
  return [null, null];
}

function encode(msgName, obj) {
  const defs = msgDefs(msgName);
  const chunks = [];
  for (const [k, v] of Object.entries(obj || {})) {
    if (v === undefined || v === null) continue;
    const [name, f] = lookupField(defs, k);
    if (!f) continue;
    const wt = WIRE[f.type] ?? 0;
    const values = f.repeated && Array.isArray(v) ? v : [v];
    for (const item of values) {
      const tag = encodeVarint((f.number << 3) | wt);
      if (wt === 0) {
        chunks.push(tag, encodeVarint(f.type === 'bool' ? (item ? 1 : 0) : item));
      } else if (wt === 2) {
        let buf;
        if (f.type === 'string') buf = Buffer.from(String(item), 'utf8');
        else if (f.type === 'bytes') buf = Buffer.isBuffer(item) ? item : Buffer.from(item);
        else if (f.type === 'message') buf = encode((f.type_name || '').replace(/^\./, ''), item);
        else buf = Buffer.from(String(item));
        chunks.push(tag, encodeVarint(buf.length), buf);
      } else if (wt === 5) {
        const b = Buffer.alloc(4);
        if (f.type === 'float') b.writeFloatLE(Number(item), 0); else b.writeUInt32LE(Number(item) >>> 0, 0);
        chunks.push(tag, b);
      } else if (wt === 1) {
        const b = Buffer.alloc(8);
        if (f.type === 'double') b.writeDoubleLE(Number(item), 0); else b.writeBigUInt64LE(toBig(item), 0);
        chunks.push(tag, b);
      }
    }
  }
  return Buffer.concat(chunks);
}

function defaultFor(type) {
  if (type === 'bool') return false;
  if (type === 'string') return '';
  return 0;
}

function decode(msgName, buf) {
  const defs = msgDefs(msgName);
  const out = {};
  const byNum = {};
  for (const [n, f] of Object.entries(defs)) {
    byNum[f.number] = [n, f];
    // proto3 omits zero values on the wire — pre-fill defaults so consumers
    // always see mined=0, has_cycle=false, tasks=[], etc.
    out[n] = f.repeated ? [] : (f.type === 'message' ? undefined : defaultFor(f.type));
  }
  let pos = 0;
  while (pos < buf.length) {
    let tag; [tag, pos] = decodeVarint(buf, pos);
    const num = Number(tag >> 3n), wire = Number(tag & 7n);
    const entry = byNum[num];
    const fname = entry ? entry[0] : null;
    const f = entry ? entry[1] : null;
    const put = (val) => {
      if (!fname) return;
      if (f.repeated) out[fname].push(val); else out[fname] = val;
    };
    if (wire === 0) {
      let v; [v, pos] = decodeVarint(buf, pos);
      put(varintToJs(v, f ? f.type : 'int64'));
    } else if (wire === 2) {
      let len; [len, pos] = decodeVarint(buf, pos);
      const slice = buf.slice(pos, pos + Number(len));
      pos += Number(len);
      if (!f) continue;
      if (f.type === 'string') put(slice.toString('utf8'));
      else if (f.type === 'bytes') put(slice);
      else if (f.type === 'message') put(decode((f.type_name || '').replace(/^\./, ''), slice));
      else put(slice);
    } else if (wire === 5) {
      const v = buf.readUInt32LE(pos); pos += 4;
      put(f && f.type === 'float' ? buf.readFloatLE(pos - 4) : v);
    } else if (wire === 1) {
      const v = buf.readBigUInt64LE(pos); pos += 8;
      put(f && f.type === 'double' ? buf.readDoubleLE(pos - 8) : varintToJs(v, f ? f.type : 'int64'));
    } else {
      throw new Error('unsupported wire type ' + wire);
    }
  }
  return out;
}

module.exports = { encode, decode, SCHEMA };
