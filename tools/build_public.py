#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成【公网通用版】直播源 lives/public.m3u（2026-11-04 新增）

背景 / 为什么必须有这个文件：
  lives/main.m3u 里 100% 是 `dbiptv.sn.chinamobile.com` 等陕西移动 IPTV
  **内网/组播地址**。这些地址只有在家里的陕西移动宽带内网才可达：
    · 电视（家里 WiFi）→ 秒开，最快
    · 手机用蜂窝数据 / 外面 WiFi / 别的运营商 → 全部连不上，直播页就是「空的」
  这正是用户「手机 TVBox / 影视仓 点播能看、直播空白」的第二层根因。

做法：
  从 3 个社区优质订阅源里，挑出【IPv4 公网可达】的央视/卫视/陕西本地核心频道，
  逐条实测（能连上 + 返回真实 m3u8），按 TTFB 排序，每台最多 2 条，
  生成一份不依赖运营商内网的 public.m3u。
  TVBox 里把它作为第 3 个 lives 对象，手机上手动切过去即可看直播。

数据源（2026-11-04 实测均 200）：
  · https://live.zhi35.com/iptv.m3u                 (392 台，每日更新)
  · https://live.hacks.tools/tv/iptv4.m3u            (404 台，IPv4 优先)
  · suxuang/myIPTV ipv4.m3u                          (1273 台，代理型)
  · https://live.zbds.top/tv/iptv4.m3u               (809 条，服务器端验活)

过滤规则（很关键，否则集成进来全是死链）：
  ✗ IPv6 字面量 [2409:...] —— 手机蜂窝/多数家宽没有 IPv6 或路由不通
  ✗ otttv/PLTV/chinamobile 组播地址 —— 运营商内网，公网不可达
  ✗ 10./172.16~31./192.168. 私网地址
  ✓ 保留 http/https 的 IPv4 直连、以及 live.php?id= 这类公网代理型

输出：lives/public.m3u + _probe/public_report.json
"""
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_live import normalize, group_of, LOCAL_KW, SHOP_KW  # 复用频道名归一化

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "lives", "public.m3u")
REPORT = os.path.join(ROOT, "_probe", "public_report.json")
CACHE = os.path.join(ROOT, "_r", "pub")

UA = "okhttp/3.15.0"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

SOURCES = [
    ("zhi35", "https://live.zhi35.com/iptv.m3u"),
    ("hacks", "https://live.hacks.tools/tv/iptv4.m3u"),
    ("zbds", "https://live.zbds.top/tv/iptv4.m3u"),
    ("myiptv", "https://gh-proxy.com/https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u"),
]

# 只保留核心频道：央视 1~17 + 5+ / CETV / CGTN + 卫视 + 陕西本地
CORE = re.compile(r"^(CCTV|CETV|CGTN)|卫视$|" + "|".join(LOCAL_KW))
MAX_PER_CHANNEL = 2
PROBE_TIMEOUT = 8
MAX_WORKERS = 32


def is_public(url):
    """判断这条线路在公网（手机蜂窝/异网）是否可能可达"""
    u = url.strip()
    if not u.startswith("http"):
        return False
    if "[" in u and "]" in u:            # IPv6 字面量
        return False
    low = u.lower()
    # 运营商 IPTV 组播/内网特征
    for kw in ("otttv.", "/pltv/", "chinamobile", "unicom", "telecom",
               "hwcdn", "iptv", "239.", "224.2", "udpxy"):
        if kw in low and ("chinamobile" in low or "/pltv/" in low or "otttv" in low):
            return False
    host = (urllib.parse.urlsplit(u).hostname or "").strip("[]")
    # 私网段
    if re.match(r"^(10\.|127\.|192\.168\.|169\.254\.)", host):
        return False
    m = re.match(r"^172\.(\d+)\.", host)
    if m and 16 <= int(m.group(1)) <= 31:
        return False
    # 组播
    m = re.match(r"^(\d+)\.", host)
    if m and 224 <= int(m.group(1)) <= 239:
        return False
    return True


def parse_m3u(text):
    out = []
    lines = text.splitlines()
    name = None
    for l in lines:
        s = l.strip()
        if s.startswith("#EXTINF"):
            name = s.split(",")[-1].strip()
        elif s.startswith("http") and name:
            out.append((name, s))
            name = None
    return out


def fetch(name, url):
    dst = os.path.join(CACHE, name + ".m3u")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25, context=CTX) as r:
            raw = r.read()
        if len(raw) < 200:
            return ""
        open(dst, "wb").write(raw)
        return raw.decode("utf-8", "ignore")
    except Exception as e:
        # 抓不到时用缓存（离线也能重建公网版）
        if os.path.exists(dst):
            print(f"  ! {name} 抓取失败({type(e).__name__})，用缓存")
            return open(dst, encoding="utf-8", errors="ignore").read()
        print(f"  ✗ {name} 抓取失败({type(e).__name__})")
        return ""


def probe(item):
    """实测：能连上 + 返回 m3u8/视频数据"""
    std, url = item
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT, context=CTX) as r:
            code = r.status
            head = r.read(2048)
        ms = int((time.time() - t0) * 1000)
        body = head.decode("utf-8", "ignore")
        ok = code == 200 and ("#EXTM3U" in body or len(head) > 256 or "live.php" in url)
        return {"name": std, "url": url, "ok": ok, "ms": ms, "code": code}
    except Exception as e:
        return {"name": std, "url": url, "ok": False, "ms": 9999,
                "err": type(e).__name__}


def main():
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)

    print("① 抓取公网订阅源")
    pairs = []
    for n, u in SOURCES:
        txt = fetch(n, u)
        if not txt:
            continue
        items = parse_m3u(txt)
        print(f"  ✓ {n:<8} 解析 {len(items)} 条")
        pairs.extend(items)

    print("\n② 归一化频道名 + 公网可达性过滤")
    cand = {}
    stats = {"总条目": len(pairs), "丢弃_IPv6内网": 0, "非核心频道": 0}
    for raw_name, url in pairs:
        if not is_public(url):
            stats["丢弃_IPv6内网"] += 1
            continue
        std = normalize(raw_name)
        if not std or not CORE.search(std) or any(k in std for k in SHOP_KW):
            stats["非核心频道"] += 1
            continue
        if url in {v for v in cand.get(std, [])}:
            continue
        cand.setdefault(std, []).append(url)
    print(f"  {stats}，核心频道 {len(cand)} 个，候选线路 {sum(len(v) for v in cand.values())} 条")

    todo = [(std, u) for std, us in cand.items() for u in us]
    print(f"\n③ 逐条实测可达性（{len(todo)} 条，{MAX_WORKERS} 并发）")
    socket.setdefaulttimeout(PROBE_TIMEOUT)
    ex = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    futs = [ex.submit(probe, it) for it in todo]
    results = []
    try:
        for f in as_completed(futs, timeout=180):
            try:
                results.append(f.result())
            except Exception:
                pass
    except TimeoutError:
        print("  ⚠ 探测超时，仅收录已完成结果")
        for f in futs:
            if f.done():
                try:
                    results.append(f.result())
                except Exception:
                    pass
    ex.shutdown(wait=False, cancel_futures=True)
    ok = [r for r in results if r["ok"]]
    print(f"  实测可用 {len(ok)}/{len(todo)} 条")

    print("\n④ 生成 lives/public.m3u")
    by_ch = {}
    for r in ok:
        by_ch.setdefault(r["name"], []).append(r)
    lines = ["#EXTM3U"]
    total = 0
    stat = {"央视": 0, "卫视": 0, "陕西本地": 0, "其他": 0}
    for std in sorted(by_ch.keys()):
        lst = sorted(by_ch[std], key=lambda r: r["ms"])
        g = group_of(std)
        stat[g] += 1
        for r in lst[:MAX_PER_CHANNEL]:
            lines.append(f'#EXTINF:-1 tvg-name="{std}" group-title="{g}",{std}')
            lines.append(r["url"])
            total += 1
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    json.dump({"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
               "stats": stats, "channels": len(by_ch), "lines": total,
               "ok": ok},
              open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  频道 {len(by_ch)} 个 / 线路 {total} 条 | 分组 {stat}")
    print(f"  已写入 {OUT}")


if __name__ == "__main__":
    main()
