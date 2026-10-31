#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐条实测直播流是否可播，输出可用流清单。

用法: python tools/probe_streams.py [--all]
默认只探测「央视/卫视」类频道（省时间）；--all 探测全部。
结果写入 _probe/working.json： {频道名: [{url, group, ms}]}
"""
import glob
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_probe")
os.makedirs(OUT, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

CORE_KW = ["央视", "CCTV", "卫视", "CETV", "中国教育"]
UA = "okhttp/3.15"


def collect(all_channels=False):
    # 候选来源：pool.m3u（历史汇总去重池）+ 当前 main.m3u（已上线的可用流，优先重测）
    files = [os.path.join(ROOT, "lives", "main.m3u"),
             os.path.join(ROOT, "lives", "pool.m3u")]
    entries = []
    for f in files:
        if not os.path.exists(f):
            continue
        try:
            lines = open(f, encoding="utf-8", errors="ignore").read().splitlines()
        except Exception:
            continue
        meta = None
        for l in lines:
            if l.startswith("#EXTINF"):
                name = l.split(",")[-1].strip()
                g = re.search(r'group-title="([^"]*)"', l)
                logo = re.search(r'tvg-logo="([^"]*)"', l)
                meta = (name, g.group(1) if g else "", logo.group(1) if logo else "")
            elif l.startswith("http") and meta:
                entries.append((meta[0], meta[1], meta[2], l.strip()))
                meta = None
    if not all_channels:
        entries = [e for e in entries
                   if any(k in e[0].upper() or k in e[0] or k in e[1] for k in CORE_KW)]
    # 按 URL 去重，保留第一个名字
    uniq = {}
    for name, group, logo, url in entries:
        if url not in uniq:
            uniq[url] = (name, group, logo)
    return uniq


def probe(item):
    url, (name, group, logo) = item
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=6, context=CTX) as r:
            code = r.getcode()
            ct = (r.headers.get("Content-Type") or "").lower()
            head = r.read(300)
        ms = int((time.time() - t0) * 1000)
        if code not in (200, 206):
            return None
        ok = (head.startswith(b"#EXTM3U")
              or b"mpegurl" in ct.encode()
              or "video" in ct
              or b"#EXTINF" in head)
        if not ok:
            return None
        return {"name": name, "group": group, "logo": logo, "url": url, "ms": ms}
    except Exception:
        return None


def main():
    all_channels = "--all" in sys.argv
    uniq = collect(all_channels)
    print(f"待探测唯一流: {len(uniq)} 条", flush=True)

    results = []
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=100) as ex:
        for res in ex.map(probe, uniq.items()):
            done += 1
            if res:
                results.append(res)
            if done % 300 == 0:
                print(f"  进度 {done}/{len(uniq)}  可用 {len(results)}  "
                      f"{int(time.time()-t0)}s", flush=True)

    print(f"\n探测完成: {len(uniq)} 条 -> 可用 {len(results)} 条  耗时 {int(time.time()-t0)}s")
    by_name = {}
    for r in results:
        by_name.setdefault(r["name"], []).append(r)
    for v in by_name.values():
        v.sort(key=lambda x: x["ms"])
    json.dump(by_name, open(os.path.join(OUT, "working.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("覆盖频道:", len(by_name))
    for n in list(by_name)[:15]:
        print(f"  {n}: {len(by_name[n])} 条可用, 最快 {by_name[n][0]['ms']}ms")


if __name__ == "__main__":
    main()
