"""
Professional Database v4.0 — MongoDB + JSON Fallback
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- MongoDB primary if MONGO_URL set, else JSON fallback
- ATF, AI Lab, MRG support
- Per-user per-platform slot limits
- Atomic writes, thread-safe
- Collections: atf_accounts, ailab_accounts, mrg_accounts, generic_accounts, slots
"""

import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

import config as cfg

DATA_DIR = cfg.DATA_DIR
ACCS_FILE = DATA_DIR / "accounts.json"
AILAB_FILE = DATA_DIR / "ailab.json"
SLOTS_FILE = DATA_DIR / "slots.json"
BACKUP_DIR = DATA_DIR / "backups"
MINERS_DIR = DATA_DIR / "miners"
MINERS_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

_lock = threading.RLock()

# ── MongoDB Setup ────────────────────────────────────────────────
_mongo_client = None
_mongo_db = None
_mongo_enabled = False

def _init_mongo():
    global _mongo_client, _mongo_db, _mongo_enabled
    if _mongo_client is not None:
        return _mongo_enabled
    if not cfg.MONGO_URL:
        _mongo_enabled = False
        return False
    try:
        from pymongo import MongoClient
        # Short timeout for init
        _mongo_client = MongoClient(cfg.MONGO_URL, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
        # Test connection
        _mongo_client.admin.command('ping')
        _mongo_db = _mongo_client[cfg.MONGO_DB_NAME]
        _mongo_enabled = True
        # Ensure indexes
        try:
            _mongo_db["atf_accounts"].create_index([("owner_id", 1), ("label", 1)], unique=True, background=True)
            _mongo_db["ailab_accounts"].create_index([("owner_id", 1), ("label", 1)], unique=True, background=True)
            _mongo_db["mrg_accounts"].create_index([("owner_id", 1), ("label", 1)], unique=True, background=True)
            _mongo_db["generic_accounts"].create_index([("owner_id", 1), ("miner_id", 1), ("label", 1)], unique=True, background=True)
            _mongo_db["slots"].create_index([("owner_id", 1)], unique=True, background=True)
            _mongo_db["user_settings"].create_index([("owner_id", 1)], unique=True, background=True)
        except Exception:
            pass
        print(f"✅ MongoDB connected: {cfg.mongo_info()}")
        return True
    except Exception as e:
        print(f"⚠️ MongoDB connection failed, fallback to JSON: {e}")
        _mongo_client = None
        _mongo_db = None
        _mongo_enabled = False
        return False

def _mongo_ok() -> bool:
    if not cfg.MONGO_URL:
        return False
    if _mongo_client is None:
        return _init_mongo()
    return _mongo_enabled

def _col(name: str):
    if not _mongo_ok():
        return None
    return _mongo_db[name]

# ── JSON Fallback Helpers ────────────────────────────────────────
def _ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    MINERS_DIR.mkdir(exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)
    for p in [ACCS_FILE, AILAB_FILE, SLOTS_FILE]:
        if not p.exists():
            p.write_text("{}", encoding="utf-8")

def _atomic_write(path: Path, data: Dict):
    _ensure_dirs()
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise

def _load_json(path: Path) -> Dict:
    _ensure_dirs()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except json.JSONDecodeError:
        backup_path = BACKUP_DIR / f"{path.stem}_corrupt_{int(time.time())}.json"
        try:
            shutil.copy(path, backup_path)
        except Exception:
            pass
        return {}
    except Exception:
        return {}

# ══════════════════════════════════════════════════════════════
#  Slot System v4.0 — MongoDB + JSON
# ══════════════════════════════════════════════════════════════

def get_default_slots() -> Dict[str, int]:
    return {
        "atf": cfg.DEFAULT_SLOT_ATF,
        "ailab": cfg.DEFAULT_SLOT_AILAB,
        "mrg": cfg.DEFAULT_SLOT_MRG,
        "max_total": cfg.DEFAULT_MAX_TOTAL,
    }

def get_user_slots(owner_id: int) -> Dict[str, int]:
    # Mongo
    if _mongo_ok():
        try:
            col = _col("slots")
            doc = col.find_one({"owner_id": int(owner_id)})
            if not doc:
                return get_default_slots()
            defaults = get_default_slots()
            for k in defaults.keys():
                if k in doc:
                    defaults[k] = int(doc[k])
            return defaults
        except Exception as e:
            print(f"get_user_slots mongo error: {e}, fallback JSON")
    # JSON fallback
    with _lock:
        data = _load_json(SLOTS_FILE)
        user_slots = data.get(str(owner_id))
        if not user_slots:
            return get_default_slots()
        defaults = get_default_slots()
        defaults.update(user_slots)
        return defaults

def set_user_slot(owner_id: int, miner_id: str, count: int) -> bool:
    miner_id = miner_id.lower()
    if miner_id not in ("atf", "ailab", "mrg", "max_total"):
        return False
    count = max(0, min(int(count), cfg.ABSOLUTE_MAX_SLOT_PER_PLATFORM))
    if _mongo_ok():
        try:
            col = _col("slots")
            existing = col.find_one({"owner_id": int(owner_id)}) or get_default_slots()
            # Merge
            new_doc = {
                "owner_id": int(owner_id),
                "atf": int(existing.get("atf", cfg.DEFAULT_SLOT_ATF)),
                "ailab": int(existing.get("ailab", cfg.DEFAULT_SLOT_AILAB)),
                "mrg": int(existing.get("mrg", cfg.DEFAULT_SLOT_MRG)),
                "max_total": int(existing.get("max_total", cfg.DEFAULT_MAX_TOTAL)),
                "updated_at": time.time(),
            }
            new_doc[miner_id] = count
            if miner_id != "max_total":
                total_slots = new_doc.get("atf",1) + new_doc.get("ailab",1) + new_doc.get("mrg",1)
                new_doc["max_total"] = max(new_doc.get("max_total", total_slots), total_slots)
            col.update_one({"owner_id": int(owner_id)}, {"$set": new_doc}, upsert=True)
            return True
        except Exception as e:
            print(f"set_user_slot mongo error: {e}")
            # fallback to JSON
    with _lock:
        data = _load_json(SLOTS_FILE)
        key = str(owner_id)
        if key not in data:
            data[key] = get_default_slots()
        data[key][miner_id] = count
        if miner_id != "max_total":
            total_slots = data[key].get("atf",1) + data[key].get("ailab",1) + data[key].get("mrg",1)
            data[key]["max_total"] = max(data[key].get("max_total", total_slots), total_slots)
        _atomic_write(SLOTS_FILE, data)
    return True

def get_user_slot(owner_id: int, miner_id: str) -> int:
    slots = get_user_slots(owner_id)
    return slots.get(miner_id.lower(), 1)

def can_add_account(owner_id: int, miner_id: str) -> tuple[bool, str, int, int]:
    miner_id = miner_id.lower()
    allowed = get_user_slot(owner_id, miner_id)
    # current counts
    if miner_id == "atf":
        current = len(get_accounts(owner_id))
    elif miner_id == "ailab":
        current = len(ai_get_accounts(owner_id))
    elif miner_id == "mrg":
        current = len(mrg_get_accounts(owner_id))
    else:
        current = len(generic_get_accounts(owner_id, miner_id))

    if current >= allowed:
        return False, f"Slot full: {current}/{allowed}", current, allowed

    total_allowed = get_user_slot(owner_id, "max_total")
    total_current = len(get_accounts(owner_id)) + len(ai_get_accounts(owner_id)) + len(mrg_get_accounts(owner_id))
    # Include generic miners in total?
    for mid in list_all_miner_types():
        if mid not in ("atf", "ailab", "mrg"):
            total_current += len(generic_get_accounts(owner_id, mid))

    if total_current >= total_allowed and total_allowed > 0:
        return False, f"Total slot full: {total_current}/{total_allowed}", current, allowed

    return True, "OK", current, allowed

def get_all_slots() -> Dict[str, Dict]:
    if _mongo_ok():
        try:
            col = _col("slots")
            out = {}
            for doc in col.find({}):
                oid = doc.get("owner_id")
                if oid is None:
                    continue
                out[str(oid)] = {
                    "atf": int(doc.get("atf", cfg.DEFAULT_SLOT_ATF)),
                    "ailab": int(doc.get("ailab", cfg.DEFAULT_SLOT_AILAB)),
                    "mrg": int(doc.get("mrg", cfg.DEFAULT_SLOT_MRG)),
                    "max_total": int(doc.get("max_total", cfg.DEFAULT_MAX_TOTAL)),
                }
            return out
        except Exception as e:
            print(f"get_all_slots mongo error: {e}")
    with _lock:
        return _load_json(SLOTS_FILE)

def set_user_slots_bulk(owner_id: int, slots: Dict[str, int]) -> bool:
    if _mongo_ok():
        try:
            col = _col("slots")
            doc = col.find_one({"owner_id": int(owner_id)}) or get_default_slots()
            new_doc = {
                "owner_id": int(owner_id),
                "atf": int(doc.get("atf", cfg.DEFAULT_SLOT_ATF)),
                "ailab": int(doc.get("ailab", cfg.DEFAULT_SLOT_AILAB)),
                "mrg": int(doc.get("mrg", cfg.DEFAULT_SLOT_MRG)),
                "max_total": int(doc.get("max_total", cfg.DEFAULT_MAX_TOTAL)),
                "updated_at": time.time(),
            }
            for k, v in slots.items():
                if k in ("atf", "ailab", "mrg", "max_total"):
                    new_doc[k] = max(0, min(int(v), cfg.ABSOLUTE_MAX_SLOT_PER_PLATFORM))
            col.update_one({"owner_id": int(owner_id)}, {"$set": new_doc}, upsert=True)
            return True
        except Exception as e:
            print(f"set_user_slots_bulk mongo error: {e}")
    with _lock:
        data = _load_json(SLOTS_FILE)
        key = str(owner_id)
        if key not in data:
            data[key] = get_default_slots()
        for k, v in slots.items():
            if k in ("atf", "ailab", "mrg", "max_total"):
                data[key][k] = max(0, min(int(v), cfg.ABSOLUTE_MAX_SLOT_PER_PLATFORM))
        _atomic_write(SLOTS_FILE, data)
    return True

# ══════════════════════════════════════════════════════════════
#  ATF Accounts — MongoDB + JSON
# ══════════════════════════════════════════════════════════════

def get_accounts(owner_id: int) -> List[Dict]:
    if _mongo_ok():
        try:
            col = _col("atf_accounts")
            docs = list(col.find({"owner_id": int(owner_id)}))
            # Convert ObjectId etc
            out = []
            for d in docs:
                d.pop("_id", None)
                out.append(d)
            return out
        except Exception as e:
            print(f"get_accounts mongo error: {e}")
    with _lock:
        data = _load_json(ACCS_FILE)
        return list(data.get(str(owner_id), []))

def add_account(owner_id: int, label: str, init_data: str,
                tg_id: int, username: str = "", device_id: str = "") -> bool:
    if _mongo_ok():
        try:
            col = _col("atf_accounts")
            doc = {
                "owner_id": int(owner_id),
                "label": str(label),
                "init_data": str(init_data),
                "tg_id": int(tg_id) if tg_id else 0,
                "username": str(username or ""),
                "device_id": str(device_id or f"dev-{tg_id}"),
                "enabled": True,
                "added_at": time.time(),
                "updated_at": time.time(),
                "miner_type": "atf",
            }
            col.update_one(
                {"owner_id": int(owner_id), "label": str(label)},
                {"$set": doc},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"add_account mongo error: {e}")
    with _lock:
        data = _load_json(ACCS_FILE)
        key = str(owner_id)
        accs = data.get(key, [])
        accs = [a for a in accs if a.get("label") != label]
        accs.append({
            "label": label,
            "init_data": init_data,
            "tg_id": tg_id,
            "username": username,
            "device_id": device_id or f"dev-{tg_id}",
            "enabled": True,
            "added_at": time.time(),
            "miner_type": "atf",
        })
        data[key] = accs
        _atomic_write(ACCS_FILE, data)
    return True

def remove_account(owner_id: int, label: str) -> bool:
    if _mongo_ok():
        try:
            col = _col("atf_accounts")
            res = col.delete_one({"owner_id": int(owner_id), "label": str(label)})
            return res.deleted_count > 0
        except Exception as e:
            print(f"remove_account mongo error: {e}")
    with _lock:
        data = _load_json(ACCS_FILE)
        key = str(owner_id)
        accs = data.get(key, [])
        new = [a for a in accs if a.get("label") != label]
        if len(new) == len(accs):
            return False
        data[key] = new
        if not data[key]:
            del data[key]
        _atomic_write(ACCS_FILE, data)
    return True

def update_account(owner_id: int, label: str, **fields) -> bool:
    if _mongo_ok():
        try:
            col = _col("atf_accounts")
            fields["updated_at"] = time.time()
            res = col.update_one(
                {"owner_id": int(owner_id), "label": str(label)},
                {"$set": fields}
            )
            return res.matched_count > 0
        except Exception as e:
            print(f"update_account mongo error: {e}")
    with _lock:
        data = _load_json(ACCS_FILE)
        key = str(owner_id)
        for acc in data.get(key, []):
            if acc.get("label") == label:
                acc.update(fields)
                acc["updated_at"] = time.time()
                _atomic_write(ACCS_FILE, data)
                return True
    return False

def get_all_enabled() -> List[Dict]:
    if _mongo_ok():
        try:
            col = _col("atf_accounts")
            docs = list(col.find({"enabled": True}))
            out = []
            for d in docs:
                owner_id = d.get("owner_id")
                d.pop("_id", None)
                d["owner_id"] = int(owner_id)
                out.append(d)
            return out
        except Exception as e:
            print(f"get_all_enabled mongo error: {e}")
    with _lock:
        data = _load_json(ACCS_FILE)
    result = []
    for owner_id, accs in data.items():
        try:
            oid = int(owner_id)
        except ValueError:
            continue
        for acc in accs:
            if acc.get("enabled", True):
                result.append({**acc, "owner_id": oid})
    return result

def get_all_users() -> List[int]:
    if _mongo_ok():
        try:
            users = set()
            for coll_name in ["atf_accounts", "ailab_accounts", "mrg_accounts", "generic_accounts", "slots", "user_settings"]:
                col = _col(coll_name)
                for oid in col.distinct("owner_id"):
                    try:
                        users.add(int(oid))
                    except Exception:
                        continue
            return list(users)
        except Exception as e:
            print(f"get_all_users mongo error: {e}")
    users = set()
    with _lock:
        for path in [ACCS_FILE, AILAB_FILE, SLOTS_FILE]:
            data = _load_json(path)
            for k in data.keys():
                try:
                    users.add(int(k))
                except ValueError:
                    continue
        for f in MINERS_DIR.glob("*.json"):
            data = _load_json(f)
            for k in data.keys():
                try:
                    users.add(int(k))
                except ValueError:
                    continue
    return list(users)

def global_stats() -> Dict:
    if _mongo_ok():
        try:
            col = _col("atf_accounts")
            total = col.count_documents({})
            enabled = col.count_documents({"enabled": True})
            users = len(col.distinct("owner_id"))
            return {"users": users, "accounts": total, "enabled": enabled, "disabled": total-enabled}
        except Exception as e:
            print(f"global_stats mongo error: {e}")
    with _lock:
        data = _load_json(ACCS_FILE)
    users = len(data)
    total = enabled = 0
    for accs in data.values():
        total += len(accs)
        enabled += sum(1 for a in accs if a.get("enabled", True))
    return {"users": users, "accounts": total, "enabled": enabled, "disabled": total-enabled}

def all_accounts_flat() -> List[Dict]:
    if _mongo_ok():
        try:
            col = _col("atf_accounts")
            docs = list(col.find({}))
            out = []
            for d in docs:
                owner_id = d.get("owner_id")
                d.pop("_id", None)
                d["owner_id"] = int(owner_id)
                out.append(d)
            return out
        except Exception as e:
            print(f"all_accounts_flat mongo error: {e}")
    with _lock:
        data = _load_json(ACCS_FILE)
    out = []
    for owner_id, accs in data.items():
        try:
            oid = int(owner_id)
        except ValueError:
            continue
        for a in accs:
            out.append({**a, "owner_id": oid})
    return out

def set_enabled_all(enabled: bool) -> int:
    if _mongo_ok():
        try:
            col = _col("atf_accounts")
            res = col.update_many({}, {"$set": {"enabled": bool(enabled), "updated_at": time.time()}})
            return res.modified_count
        except Exception as e:
            print(f"set_enabled_all mongo error: {e}")
    with _lock:
        data = _load_json(ACCS_FILE)
        n = 0
        for accs in data.values():
            for a in accs:
                if a.get("enabled", True) != enabled:
                    a["enabled"] = enabled
                    n += 1
        _atomic_write(ACCS_FILE, data)
    return n

def purge_user(owner_id: int) -> int:
    n = 0
    if _mongo_ok():
        try:
            for coll_name in ["atf_accounts", "ailab_accounts", "mrg_accounts", "generic_accounts", "slots", "user_settings"]:
                col = _col(coll_name)
                res = col.delete_many({"owner_id": int(owner_id)})
                n += res.deleted_count
            return n
        except Exception as e:
            print(f"purge_user mongo error: {e}")
    with _lock:
        data = _load_json(ACCS_FILE)
        key = str(owner_id)
        n += len(data.get(key, []))
        if key in data:
            del data[key]
            _atomic_write(ACCS_FILE, data)
        ai_data = _load_json(AILAB_FILE)
        n += len(ai_data.get(key, []))
        if key in ai_data:
            del ai_data[key]
            _atomic_write(AILAB_FILE, ai_data)
        slot_data = _load_json(SLOTS_FILE)
        if key in slot_data:
            del slot_data[key]
            _atomic_write(SLOTS_FILE, slot_data)
        for f in MINERS_DIR.glob("*.json"):
            gdata = _load_json(f)
            n += len(gdata.get(key, []))
            if key in gdata:
                del gdata[key]
                _atomic_write(f, gdata)
    return n

# ══════════════════════════════════════════════════════════════
#  AI Lab
# ══════════════════════════════════════════════════════════════

def ai_get_accounts(owner_id: int) -> List[Dict]:
    if _mongo_ok():
        try:
            col = _col("ailab_accounts")
            docs = list(col.find({"owner_id": int(owner_id)}))
            out = []
            for d in docs:
                d.pop("_id", None)
                out.append(d)
            return out
        except Exception as e:
            print(f"ai_get_accounts mongo error: {e}")
    with _lock:
        data = _load_json(AILAB_FILE)
        return list(data.get(str(owner_id), []))

def ai_add_account(owner_id: int, label: str, init_data: str, session: str = "") -> bool:
    if _mongo_ok():
        try:
            col = _col("ailab_accounts")
            doc = {
                "owner_id": int(owner_id),
                "label": str(label),
                "init_data": str(init_data),
                "session": str(session or ""),
                "enabled": True,
                "added_at": time.time(),
                "updated_at": time.time(),
                "last_ok": 0,
                "dead": False,
                "miner_type": "ailab",
            }
            col.update_one(
                {"owner_id": int(owner_id), "label": str(label)},
                {"$set": doc},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"ai_add_account mongo error: {e}")
    with _lock:
        data = _load_json(AILAB_FILE)
        key = str(owner_id)
        accs = [a for a in data.get(key, []) if a.get("label") != label]
        accs.append({
            "label": label,
            "init_data": init_data,
            "session": session,
            "enabled": True,
            "added_at": time.time(),
            "last_ok": 0,
            "dead": False,
            "miner_type": "ailab",
        })
        data[key] = accs
        _atomic_write(AILAB_FILE, data)
    return True

def ai_remove_account(owner_id: int, label: str) -> bool:
    if _mongo_ok():
        try:
            col = _col("ailab_accounts")
            res = col.delete_one({"owner_id": int(owner_id), "label": str(label)})
            return res.deleted_count > 0
        except Exception as e:
            print(f"ai_remove_account mongo error: {e}")
    with _lock:
        data = _load_json(AILAB_FILE)
        key = str(owner_id)
        accs = data.get(key, [])
        new = [a for a in accs if a.get("label") != label]
        if len(new) == len(accs):
            return False
        data[key] = new
        if not data[key]:
            del data[key]
        _atomic_write(AILAB_FILE, data)
    return True

def ai_update(owner_id: int, label: str, **fields) -> bool:
    if _mongo_ok():
        try:
            col = _col("ailab_accounts")
            fields["updated_at"] = time.time()
            res = col.update_one(
                {"owner_id": int(owner_id), "label": str(label)},
                {"$set": fields}
            )
            return res.matched_count > 0
        except Exception as e:
            print(f"ai_update mongo error: {e}")
    with _lock:
        data = _load_json(AILAB_FILE)
        key = str(owner_id)
        for a in data.get(key, []):
            if a.get("label") == label:
                a.update(fields)
                a["updated_at"] = time.time()
                _atomic_write(AILAB_FILE, data)
                return True
    return False

def ai_all_enabled() -> List[Dict]:
    if _mongo_ok():
        try:
            col = _col("ailab_accounts")
            docs = list(col.find({"enabled": True, "dead": {"$ne": True}}))
            out = []
            for d in docs:
                d.pop("_id", None)
                d["owner_id"] = int(d.get("owner_id"))
                out.append(d)
            return out
        except Exception as e:
            print(f"ai_all_enabled mongo error: {e}")
    with _lock:
        data = _load_json(AILAB_FILE)
    out = []
    for owner_id, accs in data.items():
        try:
            oid = int(owner_id)
        except ValueError:
            continue
        for a in accs:
            if a.get("enabled", True) and not a.get("dead", False):
                out.append({**a, "owner_id": oid})
    return out

def ai_all_flat() -> List[Dict]:
    if _mongo_ok():
        try:
            col = _col("ailab_accounts")
            docs = list(col.find({}))
            out = []
            for d in docs:
                d.pop("_id", None)
                d["owner_id"] = int(d.get("owner_id"))
                out.append(d)
            return out
        except Exception as e:
            print(f"ai_all_flat mongo error: {e}")
    with _lock:
        data = _load_json(AILAB_FILE)
    out = []
    for owner_id, accs in data.items():
        try:
            oid = int(owner_id)
        except ValueError:
            continue
        for a in accs:
            out.append({**a, "owner_id": oid})
    return out

def ai_stats() -> Dict:
    if _mongo_ok():
        try:
            col = _col("ailab_accounts")
            total = col.count_documents({})
            enabled = col.count_documents({"enabled": True, "dead": {"$ne": True}})
            dead = col.count_documents({"dead": True})
            users = len(col.distinct("owner_id"))
            return {"users": users, "accounts": total, "enabled": enabled, "dead": dead}
        except Exception as e:
            print(f"ai_stats mongo error: {e}")
    with _lock:
        data = _load_json(AILAB_FILE)
    total = enabled = dead = 0
    for accs in data.values():
        total += len(accs)
        enabled += sum(1 for a in accs if a.get("enabled", True) and not a.get("dead"))
        dead += sum(1 for a in accs if a.get("dead"))
    return {"users": len(data), "accounts": total, "enabled": enabled, "dead": dead}

# ══════════════════════════════════════════════════════════════
#  Generic Miner Support — MongoDB + JSON
# ══════════════════════════════════════════════════════════════

def generic_get_file(miner_id: str) -> Path:
    return MINERS_DIR / f"{miner_id}.json"

def generic_get_accounts(owner_id: int, miner_id: str) -> List[Dict]:
    miner_id = miner_id.lower()
    if _mongo_ok():
        try:
            if miner_id == "mrg":
                col = _col("mrg_accounts")
                docs = list(col.find({"owner_id": int(owner_id)}))
                out = []
                for d in docs:
                    d.pop("_id", None)
                    out.append(d)
                return out
            else:
                col = _col("generic_accounts")
                docs = list(col.find({"owner_id": int(owner_id), "miner_id": miner_id}))
                out = []
                for d in docs:
                    d.pop("_id", None)
                    out.append(d)
                return out
        except Exception as e:
            print(f"generic_get_accounts mongo error: {e}")
    # JSON fallback
    if miner_id == "mrg":
        path = generic_get_file("mrg")
    else:
        path = generic_get_file(miner_id)
    with _lock:
        data = _load_json(path)
        return list(data.get(str(owner_id), []))

def generic_add_account(owner_id: int, miner_id: str, label: str, init_data: str, extra: Dict = None) -> bool:
    miner_id = miner_id.lower()
    if _mongo_ok():
        try:
            if miner_id == "mrg":
                col = _col("mrg_accounts")
                doc = {
                    "owner_id": int(owner_id),
                    "label": str(label),
                    "init_data": str(init_data),
                    "enabled": True,
                    "added_at": time.time(),
                    "updated_at": time.time(),
                    "miner_type": "mrg",
                    "last_ok": time.time(),
                    "dead": False,
                    **(extra or {})
                }
                col.update_one(
                    {"owner_id": int(owner_id), "label": str(label)},
                    {"$set": doc},
                    upsert=True
                )
            else:
                col = _col("generic_accounts")
                doc = {
                    "owner_id": int(owner_id),
                    "miner_id": miner_id,
                    "label": str(label),
                    "init_data": str(init_data),
                    "enabled": True,
                    "added_at": time.time(),
                    "updated_at": time.time(),
                    "miner_type": miner_id,
                    **(extra or {})
                }
                col.update_one(
                    {"owner_id": int(owner_id), "miner_id": miner_id, "label": str(label)},
                    {"$set": doc},
                    upsert=True
                )
            return True
        except Exception as e:
            print(f"generic_add_account mongo error: {e}")
    path = generic_get_file(miner_id)
    with _lock:
        data = _load_json(path)
        key = str(owner_id)
        accs = [a for a in data.get(key, []) if a.get("label") != label]
        acc = {
            "label": label,
            "init_data": init_data,
            "enabled": True,
            "added_at": time.time(),
            "miner_type": miner_id,
            **(extra or {})
        }
        accs.append(acc)
        data[key] = accs
        _atomic_write(path, data)
    return True

def generic_remove_account(owner_id: int, miner_id: str, label: str) -> bool:
    miner_id = miner_id.lower()
    if _mongo_ok():
        try:
            if miner_id == "mrg":
                col = _col("mrg_accounts")
                res = col.delete_one({"owner_id": int(owner_id), "label": str(label)})
                return res.deleted_count > 0
            else:
                col = _col("generic_accounts")
                res = col.delete_one({"owner_id": int(owner_id), "miner_id": miner_id, "label": str(label)})
                return res.deleted_count > 0
        except Exception as e:
            print(f"generic_remove_account mongo error: {e}")
    path = generic_get_file(miner_id)
    with _lock:
        data = _load_json(path)
        key = str(owner_id)
        accs = data.get(key, [])
        new = [a for a in accs if a.get("label") != label]
        if len(new) == len(accs):
            return False
        data[key] = new
        if not data[key]:
            del data[key]
        _atomic_write(path, data)
    return True

def generic_update(owner_id: int, miner_id: str, label: str, **fields) -> bool:
    miner_id = miner_id.lower()
    if _mongo_ok():
        try:
            fields["updated_at"] = time.time()
            if miner_id == "mrg":
                col = _col("mrg_accounts")
                res = col.update_one(
                    {"owner_id": int(owner_id), "label": str(label)},
                    {"$set": fields}
                )
                return res.matched_count > 0
            else:
                col = _col("generic_accounts")
                res = col.update_one(
                    {"owner_id": int(owner_id), "miner_id": miner_id, "label": str(label)},
                    {"$set": fields}
                )
                return res.matched_count > 0
        except Exception as e:
            print(f"generic_update mongo error: {e}")
    path = generic_get_file(miner_id)
    with _lock:
        data = _load_json(path)
        key = str(owner_id)
        for a in data.get(key, []):
            if a.get("label") == label:
                a.update(fields)
                _atomic_write(path, data)
                return True
    return False

def list_all_miner_types() -> List[str]:
    if _mongo_ok():
        try:
            col = _col("generic_accounts")
            types = col.distinct("miner_id")
            base = ["atf", "ailab", "mrg"]
            for t in types:
                if t not in base:
                    base.append(t)
            return base
        except Exception:
            pass
    _ensure_dirs()
    types = ["atf", "ailab", "mrg"]
    for f in MINERS_DIR.glob("*.json"):
        mid = f.stem
        if mid not in types:
            types.append(mid)
    return types

# MRG wrappers
def mrg_get_accounts(owner_id: int) -> List[Dict]:
    return generic_get_accounts(owner_id, "mrg")

def mrg_add_account(owner_id: int, label: str, init_data: str, extra: Dict = None) -> bool:
    return generic_add_account(owner_id, "mrg", label, init_data, extra)

def mrg_remove_account(owner_id: int, label: str) -> bool:
    return generic_remove_account(owner_id, "mrg", label)

def mrg_update(owner_id: int, label: str, **fields) -> bool:
    return generic_update(owner_id, "mrg", label, **fields)

def mrg_all_enabled() -> List[Dict]:
    if _mongo_ok():
        try:
            col = _col("mrg_accounts")
            docs = list(col.find({"enabled": True, "dead": {"$ne": True}}))
            out = []
            for d in docs:
                d.pop("_id", None)
                d["owner_id"] = int(d.get("owner_id"))
                out.append(d)
            return out
        except Exception as e:
            print(f"mrg_all_enabled mongo error: {e}")
    path = generic_get_file("mrg")
    with _lock:
        data = _load_json(path)
    out = []
    for owner_id, accs in data.items():
        try:
            oid = int(owner_id)
        except ValueError:
            continue
        for a in accs:
            if a.get("enabled", True) and not a.get("dead", False):
                out.append({**a, "owner_id": oid})
    return out

def mrg_all_flat() -> List[Dict]:
    if _mongo_ok():
        try:
            col = _col("mrg_accounts")
            docs = list(col.find({}))
            out = []
            for d in docs:
                d.pop("_id", None)
                d["owner_id"] = int(d.get("owner_id"))
                out.append(d)
            return out
        except Exception as e:
            print(f"mrg_all_flat mongo error: {e}")
    path = generic_get_file("mrg")
    with _lock:
        data = _load_json(path)
    out = []
    for owner_id, accs in data.items():
        try:
            oid = int(owner_id)
        except ValueError:
            continue
        for a in accs:
            out.append({**a, "owner_id": oid})
    return out

def mrg_stats() -> Dict:
    if _mongo_ok():
        try:
            col = _col("mrg_accounts")
            total = col.count_documents({})
            enabled = col.count_documents({"enabled": True, "dead": {"$ne": True}})
            dead = col.count_documents({"dead": True})
            users = len(col.distinct("owner_id"))
            return {"users": users, "accounts": total, "enabled": enabled, "dead": dead}
        except Exception as e:
            print(f"mrg_stats mongo error: {e}")
    path = generic_get_file("mrg")
    with _lock:
        data = _load_json(path)
    total = enabled = dead = 0
    for accs in data.values():
        total += len(accs)
        enabled += sum(1 for a in accs if a.get("enabled", True) and not a.get("dead", False))
        dead += sum(1 for a in accs if a.get("dead", False))
    return {"users": len(data), "accounts": total, "enabled": enabled, "dead": dead}

# ── Export ───────────────────────────────────────────────────────
def export_user_data(owner_id: int) -> Dict:
    if _mongo_ok():
        try:
            atf = list(_col("atf_accounts").find({"owner_id": int(owner_id)}))
            ailab = list(_col("ailab_accounts").find({"owner_id": int(owner_id)}))
            mrg = list(_col("mrg_accounts").find({"owner_id": int(owner_id)}))
            generic = {}
            for doc in _col("generic_accounts").find({"owner_id": int(owner_id)}):
                mid = doc.get("miner_id", "unknown")
                generic.setdefault(mid, []).append(doc)
            slots = _col("slots").find_one({"owner_id": int(owner_id)}) or get_default_slots()
            # clean _id
            for lst in [atf, ailab, mrg]:
                for d in lst:
                    d.pop("_id", None)
            for mid in generic:
                for d in generic[mid]:
                    d.pop("_id", None)
            if "_id" in slots:
                slots.pop("_id")
            return {
                "owner_id": owner_id,
                "exported_at": time.time(),
                "slots": slots,
                "atf": atf,
                "ailab": ailab,
                "generic": generic,
                "mrg_accounts": mrg,
                "mongo": True,
            }
        except Exception as e:
            print(f"export_user_data mongo error: {e}")
    with _lock:
        atf = _load_json(ACCS_FILE).get(str(owner_id), [])
        ailab = _load_json(AILAB_FILE).get(str(owner_id), [])
        slots = _load_json(SLOTS_FILE).get(str(owner_id), get_default_slots())
    generic = {}
    for miner_id in list_all_miner_types():
        if miner_id in ("atf", "ailab"):
            continue
        generic[miner_id] = generic_get_accounts(owner_id, miner_id)
    return {
        "owner_id": owner_id,
        "exported_at": time.time(),
        "slots": slots,
        "atf": atf,
        "ailab": ailab,
        "generic": generic,
        "mongo": False,
    }

def create_full_backup() -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"backup_{ts}.json"
    if _mongo_ok():
        try:
            atf = list(_col("atf_accounts").find({}))
            ailab = list(_col("ailab_accounts").find({}))
            mrg = list(_col("mrg_accounts").find({}))
            generic = list(_col("generic_accounts").find({}))
            slots = list(_col("slots").find({}))
            for lst in [atf, ailab, mrg, generic, slots]:
                for d in lst:
                    d.pop("_id", None)
            data = {"timestamp": ts, "atf": atf, "ailab": ailab, "mrg": mrg, "generic": generic, "slots": slots, "mongo": True}
            _atomic_write(backup_file, data)
            return backup_file
        except Exception as e:
            print(f"create_full_backup mongo error: {e}")
    with _lock:
        atf = _load_json(ACCS_FILE)
        ailab = _load_json(AILAB_FILE)
        slots = _load_json(SLOTS_FILE)
        generic = {}
        for f in MINERS_DIR.glob("*.json"):
            generic[f.stem] = _load_json(f)
    data = {"timestamp": ts, "atf": atf, "ailab": ailab, "slots": slots, "generic": generic, "mongo": False}
    _atomic_write(backup_file, data)
    return backup_file


# ── User Language v5.0 ──────────────────────────────────────────
def get_user_lang(owner_id: int) -> str:
    default = getattr(cfg, 'DEFAULT_LANG', 'en')
    if _mongo_ok():
        try:
            col = _col("user_settings")
            doc = col.find_one({"owner_id": int(owner_id)})
            if doc and doc.get("lang"):
                return doc["lang"]
            return default
        except Exception:
            return default
    # JSON fallback - use slots file for lang
    with _lock:
        # Try user_settings.json
        us_file = DATA_DIR / "user_settings.json"
        data = _load_json(us_file)
        user = data.get(str(owner_id))
        if user and user.get("lang"):
            return user["lang"]
    return default

def set_user_lang(owner_id: int, lang: str) -> bool:
    lang = lang.lower()
    if lang not in ("en", "bn"):
        lang = "en"
    if _mongo_ok():
        try:
            col = _col("user_settings")
            col.update_one(
                {"owner_id": int(owner_id)},
                {"$set": {"owner_id": int(owner_id), "lang": lang, "updated_at": time.time()}},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"set_user_lang mongo error: {e}")
    with _lock:
        us_file = DATA_DIR / "user_settings.json"
        data = _load_json(us_file)
        key = str(owner_id)
        if key not in data:
            data[key] = {}
        data[key]["lang"] = lang
        data[key]["updated_at"] = time.time()
        _atomic_write(us_file, data)
    return True

def mongo_status() -> Dict:

    if not cfg.MONGO_URL:
        return {"enabled": False, "reason": "No MONGO_URL set — using JSON"}
    ok = _mongo_ok()
    if not ok:
        return {"enabled": False, "reason": "MongoDB connection failed — using JSON fallback", "url": cfg.MONGO_URL[:30]+"..."}
    try:
        col = _col("atf_accounts")
        atf_count = col.count_documents({})
        ailab_count = _col("ailab_accounts").count_documents({})
        mrg_count = _col("mrg_accounts").count_documents({})
        slots_count = _col("slots").count_documents({})
        return {
            "enabled": True,
            "db": cfg.MONGO_DB_NAME,
            "atf": atf_count,
            "ailab": ailab_count,
            "mrg": mrg_count,
            "slots": slots_count,
            "info": cfg.mongo_info(),
        }
    except Exception as e:
        return {"enabled": False, "reason": f"MongoDB error: {e}"}
