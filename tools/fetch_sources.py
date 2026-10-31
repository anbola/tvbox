#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取候选直播源清单（可在任何网络环境跑，不做测速）

产出：_r/*.txt  （供 speedtest.py 使用）
"""
import os
import ssl
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_r")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

SOURCES = [
    # 中国移动陕西 IPTV 官方 CDN（对陕西移动宽带最快）
    ("sx_mobile_1", "https://gh-proxy.com/https://raw.githubusercontent.com/yusanpiao/iptv/main/"
                    "%E9%99%95%E8%A5%BF%E7%A7%BB%E5%8A%A8%E7%9B%B4%E6%92%AD%E6%BA%90.txt"),
    # vbskycn/iptv：服务器端每天自动扫描验证过的 iptv4，失效比例最低
    ("zbds_iptv4", "https://live.zbds.top/tv/iptv4.m3u"),
    # 全国大合集（含各地移动源）
    ("qist_all", "https://gh-proxy.com/https://raw.githubusercontent.com/taomi/qist_tvbox/master/tvboxtv.txt"),
    # 牛虎直播（2000+ 频道）
    ("niuhu", "https://gh-proxy.com/https://raw.githubusercontent.com/niubihu1/tvbox/main/live.txt"),
    # iptv-org 中国区
    ("iptvorg_cn", "https://iptv-org.github.io/iptv/countries/cn.m3u"),
    # 月光宝盒
    ("ygbh", "https://gh-proxy.com/https://raw.githubusercontent.com/guot54/YGBH/main/zB/zB.txt"),
    # 天微直播
    ("tianwei", "http://tvkj.top/tvlive.txt"),
]


def fetch(name, url):
    dst = os.path.join(OUT, name + ".txt")
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=35, context=CTX) as r:
                raw = r.read()
            if len(raw) < 200:
                continue
            open(dst, "wb").write(raw)
            n = raw.decode("utf-8", "ignore").count("http")
            print(f"  ✓ {name:<14} {len(raw)//1024:>6}KB  含链接约 {n} 条")
            return True
        except Exception as e:
            if attempt == 1:
                print(f"  ✗ {name:<14} {type(e).__name__}")
    return False


def main():
    os.makedirs(OUT, exist_ok=True)
    print("抓取候选源：")
    ok = sum(1 for n, u in SOURCES if fetch(n, u))
    print(f"\n成功 {ok}/{len(SOURCES)} 个源 → {OUT}")


if __name__ == "__main__":
    main()
