#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取直播源原始 m3u 并落盘，供清洗脚本使用。
带重试、超时、UA。
"""
import urllib.request, ssl, time, sys, os

OUT = os.path.dirname(os.path.abspath(__file__))
SOURCES = {
    "cn_raw.m3u":        "https://iptv-org.github.io/iptv/countries/cn.m3u",
    "guovin_raw.m3u":    "https://ghproxy.net/https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u",
    "mzky_raw.m3u":      "https://ghproxy.net/https://raw.githubusercontent.com/mzky/checklist/master/itvlist.m3u",
    "yuechan_raw.m3u":   "https://ghproxy.net/https://raw.githubusercontent.com/YueChan/live/main/IPTV.m3u",
    "yang_raw.m3u":      "https://iptv.yang-1989.xyz/playlist.m3u",
    "kimentanm_raw.m3u": "https://ghproxy.net/https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u",
    # 新增：实测 3/3 可播
    "yanggather_raw.m3u": "https://ghproxy.net/https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
    "bestfan_raw.m3u":    "https://ghproxy.net/https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_all.m3u8",
    "bigbig_raw.m3u":    "https://ghproxy.net/https://raw.githubusercontent.com/BigBigGrandG/IPTV-URL/release/Gather.m3u",
    "ccsh_raw.m3u":      "https://ghproxy.net/https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/live.m3u",
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

def fetch(url, tries=4, timeout=40):
    last = ""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (TVBox; Linux) AppleWebKit/537.36",
                "Accept": "*/*",
            })
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                data = r.read()
            if data and len(data) > 100:
                return data
            last = f"empty({len(data)})"
        except Exception as e:
            last = repr(e)
        time.sleep(2 + i*2)
    raise RuntimeError(f"fetch failed after {tries} tries: {url} -> {last}")

if __name__ == "__main__":
    for name, url in SOURCES.items():
        path = os.path.join(OUT, name)
        print(f"抓取 {name} ...")
        try:
            data = fetch(url)
            with open(path, "wb") as f:
                f.write(data)
            print(f"  OK  {len(data)} bytes -> {path}")
        except Exception as e:
            print(f"  FAIL {e}")
            sys.exit(1)
