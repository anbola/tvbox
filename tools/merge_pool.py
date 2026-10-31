#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取各社区直播源 → 去重合并进候选池 lives/pool.m3u

只扩充候选池，绝不改动 lives/main.m3u（main 由本地测速结果生成）。
可在云端 / 本地任意网络环境运行。
"""
import os
import re
import ssl
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL = os.path.join(ROOT, "lives", "pool.m3u")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

SOURCES = [
    ("sx_mobile", "https://gh-proxy.com/https://raw.githubusercontent.com/yusanpiao/iptv/main/"
                  "%E9%99%95%E8%A5%BF%E7%A7%BB%E5%8A%A8%E7%9B%B4%E6%92%AD%E6%BA%90.txt"),
    ("qist_all", "https://gh-proxy.com/https://raw.githubusercontent.com/taomi/qist_tvbox/master/tvboxtv.txt"),
    ("niuhu", "https://gh-proxy.com/https://raw.githubusercontent.com/niubihu1/tvbox/main/live.txt"),
    ("iptvorg_cn", "https://iptv-org.github.io/iptv/countries/cn.m3u"),
    ("ygbh", "https://gh-proxy.com/https://raw.githubusercontent.com/guot54/YGBH/main/zB/zB.txt"),
    ("tianwei", "http://tvkj.top/tvlive.txt"),
]

SKIP_KW = ("购物", "导视", "九宫格", "测试", "彩条", "广告", "优购物", "好购物",
           "家有购物", "快乐购", "直播中国")


def fetch(url):
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                raw = r.read()
            if len(raw) > 200:
                return raw.decode("utf-8", "ignore")
        except Exception:
            pass
    return ""


def parse(text):
    """兼容 m3u / name,url 两种格式，返回 [(name, group, url)]"""
    out = []
    lines = text.splitlines()
    if "#EXTINF" in text:
        name = group = None
        for l in lines:
            s = l.strip()
            if s.startswith("#EXTINF"):
                name = s.split(",")[-1].strip()
                g = re.search(r'group-title="([^"]*)"', s)
                group = g.group(1) if g else ""
            elif s.startswith("http") and name:
                out.append((name, group, s))
                name = None
    else:
        group = ""
        for l in lines:
            s = l.strip()
            if not s:
                continue
            if s.startswith("#") and "genre" in s:
                group = s.strip("#").replace("genre", "").strip(",")
                continue
            if "," in s and "http" in s:
                name, _, url = s.partition(",")
                url = url.strip()
                if url.startswith("http"):
                    out.append((name.strip(), group, url))
    return out


def is_junk(name):
    return any(k in name for k in SKIP_KW) or not name.strip()


def main():
    old = {}
    if os.path.exists(POOL):
        for n, g, u in parse(open(POOL, encoding="utf-8", errors="ignore").read()):
            old[u] = (n, g)
    print(f"原候选池: {len(old)} 条")

    added = 0
    for name, url in SOURCES:
        txt = fetch(url)
        if not txt:
            print(f"  ✗ {name}")
            continue
        items = parse(txt)
        new = 0
        for n, g, u in items:
            if u in old or is_junk(n):
                continue
            old[u] = (n, g)
            new += 1
        added += new
        print(f"  ✓ {name:<12} 解析 {len(items):>5} 条, 新增 {new}")

    os.makedirs(os.path.dirname(POOL), exist_ok=True)
    with open(POOL, "w", encoding="utf-8", newline="\n") as f:
        f.write("#EXTM3U\n")
        for u, (n, g) in old.items():
            f.write(f'#EXTINF:-1 group-title="{g or "其他"}",{n}\n{u}\n')
    print(f"\n候选池: {len(old)} 条（新增 {added}）→ {POOL}")


if __name__ == "__main__":
    main()
