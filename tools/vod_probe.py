#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
点播源体检（针对陕西移动宽带实测）

对每个采集站测 4 项，全部是你在电视上真实会遇到的环节：
  1) class_ms  —— 拉分类树（决定首页分类标签出现快不快）
  2) list_ms   —— 拉首页列表（决定打开 App 多久出海报）
  3) detail_ms —— 点开一部片子的详情（决定"点了多久才出现集数"）
  4) vod_kbps  —— 真实下载视频分片（决定播放会不会转圈）

输出 _probe/vod_report.json
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# Windows 控制台默认 GBK，打印中文数据会抛 UnicodeEncodeError，这里强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "okhttp/3.15.0"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def safe_url(u):
    """把含中文/空格的 URL 转成合法 ASCII URL（很多采集站返回未编码的中文路径）"""
    return urllib.parse.quote(u, safe=":/?&=#%[]@!$'()*+,;~-._")

# 候选采集站（来源：社区公开接口表 + 每日健康检测项目）
CANDIDATES = [
    ("量子", "http://cj.lziapi.com/api.php/provide/vod/"),
    ("非凡", "http://cj.ffzyapi.com/api.php/provide/vod/"),
    ("非凡5", "https://ffzy5.tv/api.php/provide/vod/"),
    ("暴风", "https://bfzyapi.com/api.php/provide/vod/"),
    ("光速", "https://api.guangsuapi.com/api.php/provide/vod/"),
    ("快车", "https://caiji.kczyapi.com/api.php/provide/vod/"),
    ("红牛", "https://www.hongniuzy2.com/api.php/provide/vod/"),
    ("极速", "https://jszyapi.com/api.php/provide/vod/"),
    ("无尽", "https://api.wujinapi.me/api.php/provide/vod/"),
    ("樱花", "https://m3u8.apiyhzy.com/api.php/provide/vod/"),
    ("闪电", "http://sdzyapi.com/api.php/provide/vod/"),
    ("百度", "https://api.apibdzy.com/api.php/provide/vod/"),
    ("天涯", "https://tyyszyapi.com/api.php/provide/vod/"),
    ("电影天堂", "http://caiji.dyttzyapi.com/api.php/provide/vod/"),
    ("无线", "https://api.wuxianzy.net/api.php/provide/vod/"),
    ("蜂巢", "https://api.fczy888.me/api.php/provide/vod/"),
    ("优质", "https://api.1080zyku.com/inc/api.php/provide/vod/"),
    ("U酷", "https://api.ukuapi.com/api.php/provide/vod/"),
    ("森林", "https://slapibf.com/api.php/provide/vod/"),
    ("奥斯卡", "https://aosikazy.com/api.php/provide/vod/"),
    ("360", "https://360zyzz.com/api.php/provide/vod/"),
    ("最大", "https://api.zuidapi.com/api.php/provide/vod/"),
    ("新浪", "https://api.xinlangapi.com/api.php/provide/vod/"),
    ("旺旺", "https://api.wwzy.tv/api.php/provide/vod/"),
    ("魔爪", "https://mozhuazy.com/api.php/provide/vod/"),
    ("速播", "https://subocj.com/api.php/provide/vod/"),
    ("如意", "https://api.ryzyapi.com/api.php/provide/vod/"),
    ("金鹰", "https://jyzyapi.com/api.php/provide/vod/"),
    ("火狐", "https://hhzyapi.com/api.php/provide/vod/"),
    ("豆瓣", "https://dbzy.tv/api.php/provide/vod/"),
    ("iKun", "https://ikunzyapi.com/api.php/provide/vod/"),
    ("猫眼", "https://api.maoyanapi.top/api.php/provide/vod/"),
    ("魔都", "https://caiji.moduapi.cc/api.php/provide/vod/"),
    ("卧龙", "https://collect.wolongzyw.com/api.php/provide/vod/"),
    ("天空", "http://m3u8.tiankongapi.com/api.php/provide/vod/"),
]


def get(url, timeout=14, as_json=True, referer=None):
    t0 = time.time()
    h = {"User-Agent": UA}
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(safe_url(url), headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    ms = int((time.time() - t0) * 1000)
    return (json.loads(raw.decode("utf-8", "ignore")) if as_json else raw), ms


def pick_play(play_url):
    """从 vod_play_url 里挑一个【真正可直连】的地址

    采集站常见三种写法：
      A) 第01集$http://x/index.m3u8#第02集$http://x/2.m3u8
      B) http://share/page$$$正片$http://x/index.m3u8     <- $$$ 分隔多线路
      C) http://share/page                              <- 只有分享页，必须走解析器
    优先返回 .m3u8，其次 .mp4，最后才返回分享页。
    """
    if not play_url:
        return None
    cands = []
    for ep in play_url.split("#"):
        for line in ep.split("$$$"):
            line = line.strip()
            u = line.rsplit("$", 1)[1].strip() if "$" in line else line
            if u.startswith("http"):
                cands.append(u)
    for u in cands:
        if ".m3u8" in u:
            return u
    for u in cands:
        if ".mp4" in u:
            return u
    return cands[0] if cands else None


def measure_media(url, referer=None, budget=6.0, max_bytes=3 * 1024 * 1024):
    """下载真实媒体数据：m3u8 走分片；mp4 走 Range 分段"""
    url = safe_url(url)
    hdr = {"User-Agent": UA}
    if referer:
        hdr["Referer"] = referer

    if ".mp4" in url or ".mkv" in url:
        t0 = time.time()
        hdr2 = dict(hdr)
        hdr2["Range"] = "bytes=0-2097151"
        n = 0
        ttfb = 0
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr2),
                                    timeout=10, context=CTX) as r:
            ttfb = int((time.time() - t0) * 1000)
            while True:
                b = r.read(64 * 1024)
                if not b:
                    break
                n += len(b)
                if n >= max_bytes or time.time() - t0 >= budget:
                    break
        el = time.time() - t0
        return (round(n * 8 / el / 1000, 1) if el > 0 else 0), ttfb, n, 0, "mp4"

    raw, pms = get(url, timeout=10, as_json=False, referer=referer)
    text = raw.decode("utf-8", "ignore")
    if "#EXTM3U" not in text:
        # 可能是网页播放页（需要解析器），当作不可直连
        return 0, 0, 0, pms, "网页"
    base = url
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
            base = safe_url(best)
            raw, p2 = get(base, timeout=10, as_json=False, referer=referer)
            text = raw.decode("utf-8", "ignore")
            pms += p2
    segs = [urllib.parse.urljoin(base, l.strip()) for l in text.splitlines()
            if l.strip() and not l.strip().startswith("#")]
    if not segs:
        return 0, 0, 0, pms, "无分片"
    seg = safe_url(segs[len(segs) // 2])
    t0 = time.time()
    n = 0
    ttfb = 0
    try:
        with urllib.request.urlopen(urllib.request.Request(seg, headers=hdr),
                                    timeout=10, context=CTX) as r:
            ttfb = int((time.time() - t0) * 1000)
            while True:
                b = r.read(64 * 1024)
                if not b:
                    break
                n += len(b)
                if n >= max_bytes or time.time() - t0 >= budget:
                    break
    except urllib.error.HTTPError as e:
        return 0, ttfb, 0, pms, f"分片HTTP{e.code}"
    el = time.time() - t0
    return (round(n * 8 / el / 1000, 1) if el > 0 else 0), ttfb, n, pms, "hls"


def check(site):
    name, api = site
    r = {"name": name, "api": api, "class_ms": None, "list_ms": None,
         "detail_ms": None, "vod_kbps": 0, "ttfb": 0, "total": 0,
         "cats": 0, "kind": "", "err": ""}
    try:
        d, ms = get(api + "?ac=list")
        r["class_ms"] = ms
        cls = d.get("class") or []
        r["cats"] = len(cls)
        if not cls:
            r["err"] = "无分类"
            return r

        d2, ms2 = get(api + "?ac=videolist&pg=1")
        r["list_ms"] = ms2
        lst = d2.get("list") or []
        r["total"] = int(d2.get("total") or 0)
        if not lst:
            r["err"] = "列表空"
            return r

        # 详情（模拟"点开一部片子"）
        vid = lst[0].get("vod_id")
        play = None
        if vid:
            try:
                d3, ms3 = get(f"{api}?ac=detail&ids={vid}")
                r["detail_ms"] = ms3
                dl = d3.get("list") or []
                if dl:
                    play = pick_play(dl[0].get("vod_play_url"))
            except Exception:
                pass
        if not play:
            play = pick_play(lst[0].get("vod_play_url"))
        if not play:
            for v in lst[:10]:
                play = pick_play(v.get("vod_play_url"))
                if play:
                    break
        if not play:
            r["err"] = "无播放地址"
            return r

        base_host = "{0.scheme}://{0.netloc}/".format(urllib.parse.urlsplit(api))
        # 两次采样取中位数：单次采样波动很大（同一站可能 1.6Mbps / 4.2Mbps 来回跳）
        samples = []
        kind = ""
        ttfb = 0
        for _ in range(2):
            kbps, t, nbytes, _, kd = measure_media(play, referer=base_host)
            kind = kind or kd
            ttfb = ttfb or t
            if nbytes > 0:
                samples.append(kbps)
        samples.sort()
        r["vod_kbps"] = samples[len(samples) // 2] if samples else 0
        r["ttfb"] = ttfb
        r["kind"] = kind
        if not samples:
            r["err"] = kind or "分片失败"
    except Exception as e:
        r["err"] = type(e).__name__
    return r


def main():
    os.makedirs(os.path.join(ROOT, "_probe"), exist_ok=True)
    print(f"待测采集站: {len(CANDIDATES)} 个（从陕西移动宽带实测）\n")
    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(check, CANDIDATES):
            results.append(r)
            e = ("  ERR:" + r["err"]) if r["err"] else ""
            print(f"  {r['name']:<8} 分类{r['cats']:>3}个 {str(r['class_ms']):>5}ms "
                  f"列表{str(r['list_ms']):>5}ms 详情{str(r['detail_ms']):>5}ms "
                  f"视频{r['vod_kbps']:>8}kbps 共{r['total']:>7}条{e}", flush=True)

    json.dump(results, open(os.path.join(ROOT, "_probe", "vod_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    # 同步写一份 final（build_config.py 优先读它）
    json.dump(results, open(os.path.join(ROOT, "_probe", "vod_final.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    good = [r for r in results if r["vod_kbps"] >= 1500 and not r["err"]]
    good.sort(key=lambda x: -x["vod_kbps"])
    print(f"\n===== 达标（视频>=1500kbps 且无错）: {len(good)} 个 =====")
    for r in good:
        print(f"  {r['name']:<8} 视频{r['vod_kbps']:>8}kbps 首页{r['list_ms']:>4}ms "
              f"详情{str(r['detail_ms']):>5}ms 片源{r['total']:>7}")
    bad = [r for r in results if r not in good]
    print(f"\n淘汰 {len(bad)} 个:")
    for r in bad:
        print(f"  {r['name']:<8} {r['err'] or ('慢:%dkbps' % r['vod_kbps'])}")


if __name__ == "__main__":
    main()
