#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
点播站体检：API 延迟 + 真实视频分片下载速度

对每个采集站：
  1) ?ac=list           -> 分类树耗时
  2) ?ac=videolist&pg=1 -> 列表耗时（首页加载体验）
  3) 取一条片子的播放地址 -> 解析 m3u8 -> 真实下载一个 TS 分片测速
输出 vod_report.json
"""
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "okhttp/3.15.0"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def get(url, timeout=12, want_json=False):
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    ms = int((time.time() - t0) * 1000)
    if want_json:
        return json.loads(raw.decode("utf-8", "ignore")), ms
    return raw, ms


def pick_m3u8(play_url):
    """vod_play_url 形如 '第1集$http://x/1.m3u8#第2集$http://x/2.m3u8'"""
    if not play_url:
        return None
    for ep in play_url.split("#"):
        if "$" in ep:
            u = ep.split("$", 1)[1].strip()
        else:
            u = ep.strip()
        if u.startswith("http") and (".m3u8" in u or "/index" in u):
            return u
    return None


def measure_segment(m3u8_url, budget=6.0, max_bytes=3 * 1024 * 1024):
    """下载真实分片，返回 (kbps, ttfb_ms, bytes)"""
    raw, pms = get(m3u8_url, timeout=10)
    text = raw.decode("utf-8", "ignore")
    if "#EXTM3U" not in text:
        return 0, 0, 0, pms
    base = m3u8_url
    # master -> 选最高带宽
    if "#EXT-X-STREAM-INF" in text:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        best, bw = None, -1
        for i, l in enumerate(lines):
            if l.startswith("#EXT-X-STREAM-INF"):
                m = re.search(r"BANDWIDTH=(\d+)", l)
                b = int(m.group(1)) if m else 0
                for nxt in lines[i + 1:]:
                    if not nxt.startswith("#"):
                        if b > bw:
                            bw, best = b, urllib.parse.urljoin(base, nxt)
                        break
        if best:
            base = best
            raw, p2 = get(base, timeout=10)
            text = raw.decode("utf-8", "ignore")
            pms += p2
    segs = [urllib.parse.urljoin(base, l.strip()) for l in text.splitlines()
            if l.strip() and not l.strip().startswith("#")]
    if not segs:
        return 0, 0, 0, pms
    seg = segs[len(segs) // 2]
    t0 = time.time()
    n = 0
    ttfb = 0
    req = urllib.request.Request(seg, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10, context=CTX) as r:
        ttfb = int((time.time() - t0) * 1000)
        while True:
            buf = r.read(64 * 1024)
            if not buf:
                break
            n += len(buf)
            el = time.time() - t0
            if n >= max_bytes or el >= budget:
                break
    total = time.time() - t0
    kbps = n * 8 / total / 1000 if total > 0 else 0
    return round(kbps, 1), ttfb, n, pms


def check_site(site):
    name = site.get("name", "?")
    api = site.get("api", "")
    r = {"name": name, "api": api, "key": site.get("key"),
         "list_ms": None, "vlist_ms": None, "total": 0,
         "vod_kbps": 0, "vod_ttfb": 0, "seg_bytes": 0, "err": ""}
    try:
        d, ms = get(api + "?ac=list", want_json=True)
        r["list_ms"] = ms
        classes = d.get("class") or []
        if not classes:
            r["err"] = "无分类"
            return r
        # 列表首页耗时（App 首页加载就是这个）
        d2, ms2 = get(api + "?ac=videolist&pg=1", want_json=True)
        r["vlist_ms"] = ms2
        lst = d2.get("list") or []
        r["total"] = int(d2.get("total") or 0)
        if not lst:
            r["err"] = "列表空"
            return r
        # 取有播放地址的片子，测真实视频速度
        target = None
        for v in lst[:12]:
            pu = v.get("vod_play_url") or ""
            m = pick_m3u8(pu)
            if m:
                target = m
                break
        if not target:
            r["err"] = "无m3u8(可能是网页播放)"
            return r
        kbps, ttfb, nbytes, pms = measure_segment(target)
        r.update(vod_kbps=kbps, vod_ttfb=ttfb, seg_bytes=nbytes)
        if nbytes == 0:
            r["err"] = "分片失败"
    except Exception as e:
        r["err"] = type(e).__name__
    return r


def main():
    cfg = json.load(open(os.path.join(ROOT, "tvbox_clean.json"), encoding="utf-8"))
    sites = cfg.get("sites", [])
    # 额外候选站（社区常见、可尝试）
    extra = [
        {"key": "lzzy", "name": "量子", "api": "https://cj.lziapi.com/api.php/provide/vod/"},
        {"key": "wujin", "name": "无尽", "api": "https://api.wujinapi.me/api.php/provide/vod/"},
        {"key": "ikun", "name": "ikun", "api": "https://ikunzyapi.com/api.php/provide/vod/"},
        {"key": "360zy", "name": "360", "api": "https://360zy.com/api.php/provide/vod/"},
        {"key": "hhzy2", "name": "火狐2", "api": "https://hhzyapi.com/api.php/provide/vod/"},
        {"key": "jisu", "name": "极速", "api": "https://jszyapi.com/api.php/provide/vod/"},
        {"key": "subo", "name": "速播", "api": "https://subocaiji.com/api.php/provide/vod/"},
        {"key": "mdzy", "name": "魔都", "api": "https://caiji.moduapi.cc/api.php/provide/vod/"},
    ]
    have = {s.get("api") for s in sites}
    for e in extra:
        if e["api"] not in have:
            sites.append(e)
    print(f"待测站点: {len(sites)}")

    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(check_site, sites):
            results.append(r)
            print(f"  {r['name']:<8} list={r['list_ms']}ms vlist={r['vlist_ms']}ms "
                  f"total={r['total']:<7} 视频={r['vod_kbps']:<8}kbps ttfb={r['vod_ttfb']}ms "
                  f"{'ERR:'+r['err'] if r['err'] else ''}", flush=True)

    os.makedirs(os.path.join(ROOT, "_probe"), exist_ok=True)
    json.dump(results, open(os.path.join(ROOT, "_probe", "vod_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    good = [r for r in results if r["vod_kbps"] >= 800]
    good.sort(key=lambda x: (-x["vod_kbps"], x["list_ms"] or 9999))
    print(f"\n===== 结论 =====")
    print(f"可用(视频≥800kbps): {len(good)}/{len(results)}")
    for r in good:
        print(f"  {r['name']:<8} 视频{r['vod_kbps']:>8}kbps  API {r['list_ms']:>4}ms  片源{r['total']}")


if __name__ == "__main__":
    main()
