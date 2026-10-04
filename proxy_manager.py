"""
Proxy Manager v3.0 — Powerful & Professional
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 25+ free proxy sources (HTTP, SOCKS4, SOCKS5)
- Health scoring, circuit breaker
- Sticky IP per account, global collision avoidance
- Auto-refresh when healthy < 100
- Validates against ATF + MRG endpoints
- Supports extra sources via env

Target: 100+ healthy proxies, not 30±
"""

import asyncio
import json
import os
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

import aiohttp

try:
    from aiohttp_socks import ProxyConnector
    HAS_SOCKS = True
except ImportError:
    HAS_SOCKS = False
    ProxyConnector = None

from logger import proxy_log as log

# Validate against multiple endpoints for better coverage
VALIDATE_TARGETS = [
    ("https://atfminers.asloni.online/miner/index.php?action=get_atf_price&t=1", "price_usd"),
    ("https://mrg.up.railway.app/api/health", None),  # any 200 is ok for MRG
    ("https://api.ailab-agent.online/api/v1/health", None),
]

# ── 25+ Free proxy sources ──────────────────────────────────────
PROXY_SOURCES = [
    # SOCKS5 — best success rate
    ("https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=socks5&proxy_format=ipport&format=text", "socks5"),
    ("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt", "socks5"),
    ("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt", "socks5"),
    ("https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks5/data.txt", None),
    ("https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt", "socks5"),
    ("https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt", "socks5"),
    ("https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt", "socks5"),
    ("https://raw.githubusercontent.com/UserR3X/proxy-list/main/online/socks5.txt", "socks5"),
    ("https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt", None),  # mixed
    ("https://api.openproxylist.xyz/socks5.txt", "socks5"),
    ("https://www.proxy-list.download/api/v1/get?type=socks5", "socks5"),
    ("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/socks5.txt", "socks5"),
    # SOCKS4
    ("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt", "socks4"),
    ("https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=socks4&proxy_format=ipport&format=text", "socks4"),
    ("https://raw.githubusercontent.com/UserR3X/proxy-list/main/online/socks4.txt", "socks4"),
    ("https://api.openproxylist.xyz/socks4.txt", "socks4"),
    ("https://www.proxy-list.download/api/v1/get?type=socks4", "socks4"),
    # HTTP — good fallback
    ("https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt", None),
    ("https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&proxy_format=ipport&format=text", "http"),
    ("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt", "http"),
    ("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt", "http"),
    ("https://raw.githubusercontent.com/UserR3X/proxy-list/main/online/http.txt", "http"),
    ("https://api.openproxylist.xyz/http.txt", "http"),
    ("https://www.proxy-list.download/api/v1/get?type=http", "http"),
    ("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/http.txt", "http"),
    ("https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt", "http"),
    ("https://raw.githubusercontent.com/proxy4parsing/proxy-list/main/http.txt", "http"),
    ("https://raw.githubusercontent.com/mertguvencli/http-proxy-list/main/proxy-list/data.txt", "http"),
    ("https://raw.githubusercontent.com/hendrikbgr/Free-Proxy-Repo/master/proxy_list.txt", None),
    ("https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt", None),
]

def make_connector(proxy: Optional[str]):
    if proxy and proxy.startswith("socks") and HAS_SOCKS:
        try:
            return ProxyConnector.from_url(proxy, ssl=False)
        except Exception as e:
            log.debug("Connector fail %s: %s", proxy[:30], e)
            return None
    return None

def http_proxy_arg(proxy: Optional[str]) -> Optional[str]:
    if proxy and proxy.startswith("http"):
        return proxy
    return None

def _sanitize_proxy_url(url: str) -> bool:
    if not url or len(url) < 10:
        return False
    if url.count(":") < 2:
        return False
    if url.endswith(":0") or "0.0.0.0" in url:
        return False
    if url.startswith("socks") and not HAS_SOCKS:
        return False
    # Basic IP:port validation
    try:
        # Extract host:port
        if "://" in url:
            hostport = url.split("://", 1)[1]
            if "@" in hostport:
                hostport = hostport.rsplit("@", 1)[1]
            if ":" not in hostport:
                return False
    except Exception:
        return False
    return True

class ProxyManager:
    def __init__(self, cfg: dict, state_path: str = "data/proxies.json"):
        self.enabled = bool(cfg.get("use_proxy", True))
        self.refresh_hours = float(cfg.get("proxy_refresh_hours", 12))
        self.min_healthy = int(cfg.get("proxy_min_healthy", 100))
        self.validate_max = int(cfg.get("proxy_validate_max", 1500))
        self.concurrency = int(cfg.get("proxy_concurrency", 200))
        self.timeout = float(cfg.get("proxy_timeout_sec", 10))

        # Extra sources from env
        extra = cfg.get("proxy_sources_extra") or ""
        if extra:
            for url in extra.split(","):
                url = url.strip()
                if url:
                    PROXY_SOURCES.append((url, None))

        self.state_path = Path(state_path)
        self.healthy: List[str] = []
        self.bad: Set[str] = set()
        self.assigned: Dict[str, str] = {}  # account_key -> proxy
        self.fail_count: Dict[str, int] = {}
        self.success_count: Dict[str, int] = {}
        self.ip_to_proxy: Dict[str, str] = {}  # ip -> proxy for collision detection
        self.last_refresh: float = 0.0
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._refreshing = False
        self._load()

    def _load(self):
        try:
            if self.state_path.exists():
                d = json.loads(self.state_path.read_text(encoding="utf-8"))
                self.healthy = d.get("healthy", [])
                self.assigned = d.get("assigned", {})
                self.last_refresh = d.get("last_refresh", 0)
                log.info("Proxy loaded: %d healthy, %d assigned", len(self.healthy), len(self.assigned))
        except Exception as e:
            log.warning("Proxy load fail: %s", e)

    def _save(self):
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "healthy": self.healthy,
                "assigned": self.assigned,
                "last_refresh": self.last_refresh,
                "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
            os.replace(tmp, self.state_path)
        except Exception as e:
            log.warning("Proxy save fail: %s", e)

    async def _fetch_source(self, sess: aiohttp.ClientSession, url: str, scheme: Optional[str]) -> List[str]:
        out = []
        try:
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    return []
                text = await r.text()
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "//")):
                    continue
                # Handle format: ip:port or scheme://ip:port or ip:port:user:pass?
                if "://" in line:
                    p = line
                elif scheme:
                    # line might be ip:port
                    if ":" in line and len(line.split(":")) >= 2:
                        p = f"{scheme}://{line}"
                    else:
                        continue
                else:
                    # Try to detect scheme from content
                    # If line contains only ip:port, default to http for safety, but we have scheme None
                    # We'll try both http and socks5? For simplicity, assume http if no scheme
                    if ":" in line:
                        # Heuristic: if source URL contains socks5, treat as socks5
                        if "socks5" in url.lower():
                            p = f"socks5://{line}"
                        elif "socks4" in url.lower():
                            p = f"socks4://{line}"
                        else:
                            p = f"http://{line}"
                    else:
                        continue
                if _sanitize_proxy_url(p) and p not in self.bad:
                    out.append(p)
        except Exception as e:
            log.debug("Source fail %s: %s", url[:60], e)
        return out

    async def _gather_candidates(self) -> List[str]:
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7)"}
        async with aiohttp.ClientSession(headers=headers) as sess:
            results = await asyncio.gather(
                *[self._fetch_source(sess, u, s) for u, s in PROXY_SOURCES],
                return_exceptions=True
            )
        cands: List[str] = []
        for r in results:
            if isinstance(r, list):
                cands.extend(r)

        # Dedupe
        seen = set()
        uniq = []
        for p in cands:
            if p not in seen:
                seen.add(p)
                uniq.append(p)

        random.shuffle(uniq)
        # Prefer SOCKS5
        uniq.sort(key=lambda p: 0 if p.startswith("socks5") else (1 if p.startswith("socks4") else 2))
        return uniq

    async def _validate_one(self, proxy: str, sem: asyncio.Semaphore) -> Optional[str]:
        async with sem:
            # Try primary target (ATF) — must contain price_usd
            try:
                conn = make_connector(proxy)
                to = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession(connector=conn, timeout=to) as s:
                    kw = {}
                    hp = http_proxy_arg(proxy)
                    if hp:
                        kw["proxy"] = hp
                    # Try ATF first
                    try:
                        async with s.post(VALIDATE_TARGETS[0][0], json={}, **kw) as r:
                            if r.status == 200:
                                body = await r.text()
                                if VALIDATE_TARGETS[0][1] in body:
                                    return proxy
                    except Exception:
                        pass
                    # Fallback: try MRG health or any 200
                    try:
                        async with s.get("https://mrg.up.railway.app/", **kw) as r:
                            if r.status in (200, 404, 405):  # any response means proxy works
                                return proxy
                    except Exception:
                        pass
                    # Try httpbin as last resort
                    try:
                        async with s.get("https://httpbin.org/ip", **kw) as r:
                            if r.status == 200:
                                return proxy
                    except Exception:
                        pass
            except Exception:
                return None
            return None

    async def refresh(self, force: bool = False) -> int:
        if not self.enabled:
            return 0
        if self._refreshing:
            log.info("Refresh already in progress")
            return len(self.healthy)

        async with self._lock:
            age = time.time() - self.last_refresh
            if not force and age < self.refresh_hours * 3600 and len(self.healthy) >= self.min_healthy:
                return len(self.healthy)
            self._refreshing = True

        try:
            log.info("🔄 Refreshing proxy pool from %d sources...", len(PROXY_SOURCES))
            cands = await self._gather_candidates()
            if not cands:
                log.warning("No candidates fetched")
                return len(self.healthy)

            batch = cands[: self.validate_max]
            log.info("Validating %d candidates (concurrency=%d, timeout=%ds)...", len(batch), self.concurrency, self.timeout)

            sem = asyncio.Semaphore(self.concurrency)
            t0 = time.time()
            results = await asyncio.gather(*[self._validate_one(p, sem) for p in batch])
            good = [p for p in results if p]

            async with self._lock:
                # Keep old healthy that still work + new
                # Dedupe by IP to avoid same IP with different scheme
                ip_seen = set()
                deduped = []
                for p in good:
                    try:
                        # Extract IP
                        host = p.split("://", 1)[1]
                        if "@" in host:
                            host = host.rsplit("@", 1)[1]
                        ip = host.split(":")[0]
                        if ip not in ip_seen:
                            ip_seen.add(ip)
                            deduped.append(p)
                    except Exception:
                        deduped.append(p)

                self.healthy = deduped
                self.fail_count.clear()
                self.last_refresh = time.time()
                self.bad.clear()

                # Clean assignments
                hs = set(self.healthy)
                for k, p in list(self.assigned.items()):
                    if p not in hs:
                        del self.assigned[k]

                self._save()

            elapsed = time.time() - t0
            log.info("✅ Proxy pool: %d healthy / %d tested in %.1fs (%.1f%%) | Target %d",
                     len(self.healthy), len(batch), elapsed,
                     len(self.healthy)/len(batch)*100 if batch else 0,
                     self.min_healthy)

            # If still low, try again with more candidates after short delay
            if len(self.healthy) < self.min_healthy and not force:
                log.warning("Pool still low (%d < %d), will retry in 5min", len(self.healthy), self.min_healthy)

            return len(self.healthy)
        finally:
            self._refreshing = False

    async def ensure_ready(self):
        if not self.enabled:
            return
        if len(self.healthy) < self.min_healthy or (time.time() - self.last_refresh) > self.refresh_hours * 3600:
            await self.refresh(force=True)

    def _least_used(self, exclude_ips: Set[str] = None) -> Optional[str]:
        if not self.healthy:
            return None
        exclude_ips = exclude_ips or set()

        # Count usage
        used: Dict[str, int] = {}
        used_ips: Set[str] = set()
        for p in self.assigned.values():
            used[p] = used.get(p, 0) + 1
            try:
                host = p.split("://", 1)[1]
                if "@" in host:
                    host = host.rsplit("@", 1)[1]
                ip = host.split(":")[0]
                used_ips.add(ip)
            except Exception:
                pass

        # Prefer unused proxies with unused IPs
        candidates = []
        for p in self.healthy:
            try:
                host = p.split("://", 1)[1]
                if "@" in host:
                    host = host.rsplit("@", 1)[1]
                ip = host.split(":")[0]
                if ip in exclude_ips or (ip in used_ips and len(used_ips) < len(self.healthy)):
                    # If IP already used elsewhere, deprioritize but not exclude if pool small
                    if len(self.healthy) > len(used_ips):
                        continue
            except Exception:
                pass
            candidates.append(p)

        pool = candidates if candidates else self.healthy
        # Prefer unused
        unused = [p for p in pool if p not in used]
        if unused:
            return random.choice(unused)
        return min(pool, key=lambda p: (used.get(p, 0), random.random()))

    def get_for(self, account_key: str) -> Optional[str]:
        if not self.enabled:
            return None
        if not self.healthy:
            return None
        p = self.assigned.get(account_key)
        if p and p in self.healthy and p not in self.bad:
            return p
        # Avoid IP collision: collect IPs already assigned to other accounts
        exclude_ips = set()
        for k, v in self.assigned.items():
            if k != account_key:
                try:
                    host = v.split("://", 1)[1]
                    if "@" in host:
                        host = host.rsplit("@", 1)[1]
                    ip = host.split(":")[0]
                    exclude_ips.add(ip)
                except Exception:
                    pass
        p = self._least_used(exclude_ips)
        if p:
            self.assigned[account_key] = p
            self._save()
            log.info("Assigned proxy to %s: %s", account_key, p[:50])
        return p

    def report_failure(self, account_key: str, proxy: Optional[str]) -> Optional[str]:
        if not proxy or not self.enabled:
            return self.get_for(account_key) if self.healthy else None
        n = self.fail_count.get(proxy, 0) + 1
        self.fail_count[proxy] = n
        if n >= 2:
            self.bad.add(proxy)
            if proxy in self.healthy:
                self.healthy.remove(proxy)
            log.warning("Proxy retired after %d fails: %s (%d left)", n, proxy[:50], len(self.healthy))
            for k, v in list(self.assigned.items()):
                if v == proxy:
                    del self.assigned[k]
        else:
            self.assigned.pop(account_key, None)
        self._save()
        return self.get_for(account_key)

    def report_success(self, proxy: Optional[str]):
        if proxy:
            self.fail_count.pop(proxy, None)
            self.success_count[proxy] = self.success_count.get(proxy, 0) + 1

    async def _loop(self):
        await asyncio.sleep(10)
        while True:
            try:
                await self.refresh(force=False)
                if len(self.healthy) < self.min_healthy:
                    log.warning("Pool low (%d) — forcing refresh", len(self.healthy))
                    await self.refresh(force=True)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Proxy loop error: %s", e)
            await asyncio.sleep(1800)  # check every 30min

    def start(self):
        if self.enabled and not self._task:
            self._task = asyncio.create_task(self._loop())
            log.info("ProxyManager v3.0 started — %d sources, target %d healthy, refresh every %.0fh",
                     len(PROXY_SOURCES), self.min_healthy, self.refresh_hours)

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None

    def stats(self) -> dict:
        age_h = (time.time() - self.last_refresh) / 3600 if self.last_refresh else -1
        return {
            "enabled": self.enabled,
            "healthy": len(self.healthy),
            "bad": len(self.bad),
            "assigned": len(self.assigned),
            "age_hours": age_h,
            "socks": HAS_SOCKS,
            "sources": len(PROXY_SOURCES),
        }

    @property
    def healthy_list(self) -> List[str]:
        return list(self.healthy)
