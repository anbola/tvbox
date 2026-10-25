#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
搜索并实测大量 TVBox 直播源 + 点播源，输出可用清单。
实测维度：可达性 / 台数 / 分类数 / 播放地址有效性 / 响应速度(延迟)
"""
import json, ssl, time, urllib.request, urllib.parse, os, sys
from concurrent.futures import ThreadPoolExecutor

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36",
      "Accept": "*/*"}

# ============ 直播源候选（来自公开维护仓库）============
LIVE_CANDS = [
    ("best-fan-cn_all",   "https://ghproxy.net/https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_all.m3u8"),
    ("CCSH-live",         "https://ghproxy.net/https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/live.m3u"),
    ("zbds-ipv6",         "https://live.zbds.top/tv/iptv6.m3u"),
    ("zbds-ipv4",         "https://live.zbds.top/tv/iptv4.m3u"),
    ("fanmingming-ipv6",  "https://live.fanmingming.cn/tv/m3u/ipv6.m3u"),
    ("fanmingming-ipv4",  "https://live.fanmingming.cn/tv/m3u/ipv4.m3u"),
    ("BurningC4-TV-IPV4", "https://ghproxy.net/https://raw.githubusercontent.com/BurningC4/Chinese-IPTV/master/TV-IPV4.m3u"),
    ("vamoschuck-TV",     "https://ghproxy.net/https://raw.githubusercontent.com/vamoschuck/TV/main/M3U"),
    ("BigBigGrandG",     "https://ghproxy.net/https://raw.githubusercontent.com/BigBigGrandG/IPTV-URL/release/Gather.m3u"),
    ("niubihu1-live",     "https://ghproxy.net/https://raw.githubusercontent.com/niubihu1/tvbox/main/live.txt"),
    ("top-tv-iptv4",      "https://ghproxy.net/https://raw.githubusercontent.com/top/tv/iptv4.m3u"),
    ("iptv-org-cn",       "https://iptv-org.github.io/iptv/countries/cn.m3u"),
    ("YanG",              "https://iptv.yang-1989.xyz/playlist.m3u"),
    ("Guovin",            "https://ghproxy.net/https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u"),
    ("mzky",              "https://ghproxy.net/https://raw.githubusercontent.com/mzky/checklist/master/itvlist.m3u"),
    ("YueChan",           "https://ghproxy.net/https://raw.githubusercontent.com/YueChan/live/main/IPTV.m3u"),
    ("Kimentanm",         "https://ghproxy.net/https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u"),
    ("gitee-zhiboyuan",   "https://gitee.com/xxy002/zhiboyuan/raw/master/dsy"),
    ("Yang-Gather",       "https://ghproxy.net/https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u"),
    ("ngo5-IPTV",         "https://ghproxy.net/https://raw.githubusercontent.com/ngo5/IPTV/main/result.m3u"),
]

# ============ 点播源候选（苹果CMS 接口）============
VOD_CANDS = [
    ("量子lzi",     "http://cj.lziapi.com/api.php/provide/vod/"),
    ("量子lzizy",   "https://lzizy1.com/api.php/provide/vod/?ac=list"),
    ("非凡ffzyapi", "http://cj.ffzyapi.com/api.php/provide/vod/"),
    ("非凡ffzy5",   "http://ffzy5.tv/api.php/provide/vod"),
    ("暴风bfzy",    "https://bfzyapi.com/api.php/provide/vod"),
    ("光速guangsu", "https://api.guangsuapi.com/api.php/provide/vod/"),
    ("快车kczy",    "https://caiji.kczyapi.com/api.php/provide/vod/"),
    ("天空tiankong","http://m3u8.tiankongapi.com/api.php/provide/vod/"),
    ("红牛hongniu", "https://www.hongniuzy2.com/api.php/provide/vod/"),
    ("极速jszy",    "https://jszyapi.com/api.php/provide/vod/"),
    ("索尼soni",    "https://suoniapi.com/api.php/provide/vod/?ac=list"),
    ("火狐hhzy",    "https://hhzyapi.com/api.php/provide/vod/"),
    ("百度apibdzy", "https://api.apibdzy.com/api.php/provide/vod/?ac=list"),
    ("360zy",       "https://360zy.com/api.php/provide/vod?"),
    ("虎牙huya",    "https://www.huyaapi.com/api.php/provide/vod/from/hym3u8"),
    ("如意rycj",    "https://cj.rycjapi.com/api.php/provide/vod"),
    ("非凡1ffzy",   "http://ffzy1.tv/api.php/provide/vod/"),
    ("卧龙wolong",  "https://collect.wolongzyw.com/api.php/provide/vod/"),
    ("糖糖tangs",   "https://tangsangapi.com/api.php/provide/vod/"),
    ("闪电shandian","https://sdzyapi.com/api.php/provide/vod/"),
    ("苹果cms-py",  "https://api.ffzyapi.com/api.php/provide/vod/"),
    ("乐视leshi",   "https://api.leshiapi.com/api.php/provide/vod/"),
    ("芒果mgtv",    "https://mgtvapi.com/api.php/provide/vod/"),
    ("樱花yinghua", "https://api.yinghuaapi.com/api.php/provide/vod/"),
    ("星星star",    "https://api.starapi.cc/api.php/provide/vod/"),
    ("天星tianxing","https://api.tianxingapi.com/api.php/provide/vod/"),
    ("下一年xiaonian","https://api.xiaonianapi.com/api.php/provide/vod/"),
    ("鸭鸭yaya",    "https://api.yayacms.com/api.php/provide/vod/"),
    ("人人renren",  "https://api.renrenapi.com/api.php/provide/vod/"),
    ("的卢delu",    "https://api.deluapi.com/api.php/provide/vod/"),
    ("水果shuiguo", "https://api.shuiguoapi.com/api.php/provide/vod/"),
]


def fetch(url, timeout=30):
    t0 = time.time()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        d = r.read()
    return d, (time.time() - t0) * 1000


def test_live(item):
    name, url = item
    try:
        d, ms = fetch(url)
        n = d.count(b"#EXTINF")
        if n == 0:
            return name, url, False, "无频道", ms, 0
        # 抽 3 个流测速
        lines = d.splitlines()
        streams = []
        for i, l in enumerate(lines):
            if l.startswith(b"#EXTINF") and i + 1 < len(lines):
                u = lines[i + 1].strip()
                if u.startswith(b"http"):
                    streams.append(u)
        okc = 0
        for u in random_sample(streams, 3):
            try:
                uu = urllib.parse.quote(u.decode("utf-8", "ignore"), safe=":/?&=%+#")
                r2 = urllib.request.Request(uu, headers={**UA, "Range": "bytes=0-512"})
                with urllib.request.urlopen(r2, timeout=8, context=ctx) as resp:
                    if resp.getcode() in (200, 206):
                        okc += 1
            except Exception:
                pass
        return name, url, okc > 0, f"{n}台/抽测{okc}/3可播", ms, n
    except Exception as e:
        return name, url, False, type(e).__name__, 0, 0


def random_sample(lst, k):
    import random
    if not lst:
        return []
    random.seed(11)
    return random.sample(lst, min(k, len(lst)))


def test_vod(item):
    name, url = item
    try:
        d, ms = fetch(url, 25)
        j = json.loads(d.decode("utf-8", "ignore"))
        cls = j.get("class", [])
        if not cls:
            return name, url, False, "无class", ms, 0
        sep = "&" if "?" in url else "?"
        # 找第一个有内容的分类
        good = 0
        for c in cls[:8]:
            cid = c.get("type_id") if isinstance(c, dict) else c
            try:
                j2 = json.loads(urllib.request.urlopen(
                    urllib.request.Request(f"{url}{sep}ac=videolist&t={cid}&pg=1", headers=UA),
                    timeout=15, context=ctx).read().decode("utf-8", "ignore"))
                if len(j2.get("list", [])) > 0:
                    good += 1
            except Exception:
                pass
            if good >= 2:
                break
        return name, url, good > 0, f"{len(cls)}分类/{good}有内容", ms, len(cls)
    except Exception as e:
        return name, url, False, type(e).__name__, 0, 0


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    out = {}
    if which in ("live", "both"):
        print("=" * 78)
        print("直播源实测（可达性 / 台数 / 抽测可播数 / 响应延迟）")
        print("=" * 78)
        with ThreadPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(test_live, LIVE_CANDS))
        for name, url, ok, msg, ms, n in sorted(res, key=lambda x: (not x[2], -x[3].count("台") and 0 or 0, x[4])):
            print(f"  {'✓' if ok else '✗'} {name:<20} {msg:<22} {ms:>6.0f}ms  {n:>5}台")
        out["live"] = [{"name": r[0], "url": r[1], "ok": r[2], "msg": r[3], "ms": round(r[4]), "n": r[5]} for r in res]
    if which in ("vod", "both"):
        print()
        print("=" * 78)
        print("点播源实测（分类数 / 有内容分类 / 响应延迟）")
        print("=" * 78)
        with ThreadPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(test_vod, VOD_CANDS))
        for name, url, ok, msg, ms, n in sorted(res, key=lambda x: (not x[2], x[4])):
            print(f"  {'✓' if ok else '✗'} {name:<20} {msg:<22} {ms:>6.0f}ms")
        out["vod"] = [{"name": r[0], "url": r[1], "ok": r[2], "msg": r[3], "ms": round(r[4]), "n": r[5]} for r in res]
    with open("probe_new_sources.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n→ 结果已存 probe_new_sources.json")


if __name__ == "__main__":
    main()
