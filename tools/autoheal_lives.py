#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自愈式直播源刷新器 v2（替代原 fetch_raw + clean_lives + build_curated 的直播部分）

每天由 GitHub Actions 调用：
  1) 探测候选池 POOL（现有 10 个 + 9 个备用，共 19 个）
  2) 用 clean_lives.clean_m3u 做中文化/分辨率/分组清洗（质量与原流程一致）
  3) 按台数排名，取最健康的 TOP_N 个；死源（台数过低/抓取失败）自动落选
  4) 把选中的源写入 lives/<key>_clean.m3u
  5) 改写两个根配置（tvbox_curated / tvbox_subscription）的 lives 数组
     —— 只改 lives，点播/解析/规则等一律原样保留
  6) 健康源不足 TOP_N 时，用已抓到的（哪怕偏低）补齐，保证数量稳定

=> 任何一个源挂了，第二天自动被健康备件顶替，无需人工干预。
"""
import os, sys, json, ssl, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # 仓库根目录
LIVES = os.path.join(ROOT, "lives")
os.makedirs(LIVES, exist_ok=True)

sys.path.insert(0, HERE)
import clean_lives                         # 复用现有清洗（台名中文化等）

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36", "Accept": "*/*"}

BASE = "https://anbola.github.io/tvbox"

# 候选池：现有 10 个 + 9 个备用（来自 probe_new_sources.LIVE_CANDS）
POOL = [
    ("cn",        "央视·卫视精选",   "https://iptv-org.github.io/iptv/countries/cn.m3u"),
    ("guovin",    "Guovin 中国IPTV", "https://ghproxy.net/https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.m3u"),
    ("mzky",      "咪咕中转·央视卫视", "https://ghproxy.net/https://raw.githubusercontent.com/mzky/checklist/master/itvlist.m3u"),
    ("yuechan",   "每日更新·央视卫视", "https://ghproxy.net/https://raw.githubusercontent.com/YueChan/live/main/IPTV.m3u"),
    ("yang",      "Yang·咪咕移动",    "https://iptv.yang-1989.xyz/playlist.m3u"),
    ("kimentanm", "Kimentanm·IPTV",  "https://ghproxy.net/https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u"),
    ("yanggather","YangGather·聚合",  "https://ghproxy.net/https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u"),
    ("bestfan",   "BestFan·聚合",     "https://ghproxy.net/https://raw.githubusercontent.com/best-fan/iptv-sources/master/cn_all.m3u8"),
    ("bigbig",    "BigBig 聚合源",    "https://ghproxy.net/https://raw.githubusercontent.com/BigBigGrandG/IPTV-URL/release/Gather.m3u"),
    ("ccsh",      "CCSH 自动采集",    "https://ghproxy.net/https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/live.m3u"),
    ("zbds6",     "直播帝·IPV6",      "https://live.zbds.top/tv/iptv6.m3u"),
    ("zbds4",     "直播帝·IPV4",      "https://live.zbds.top/tv/iptv4.m3u"),
    ("fm6",       "繁星·IPV6",        "https://live.fanmingming.cn/tv/m3u/ipv6.m3u"),
    ("fm4",       "繁星·IPV4",        "https://live.fanmingming.cn/tv/m3u/ipv4.m3u"),
    ("burning",   "BurningC4·IPTV",   "https://ghproxy.net/https://raw.githubusercontent.com/BurningC4/Chinese-IPTV/master/TV-IPV4.m3u"),
    ("vamos",     "Vamoschuck·TV",    "https://ghproxy.net/https://raw.githubusercontent.com/vamoschuck/TV/main/M3U"),
    ("niubihu",   "牛逼虎·直播",      "https://ghproxy.net/https://raw.githubusercontent.com/niubihu1/tvbox/main/live.txt"),
    ("top",       "TOP·IPTV4",       "https://ghproxy.net/https://raw.githubusercontent.com/top/tv/iptv4.m3u"),
    ("ngo5",      "NGO5·IPTV",       "https://ghproxy.net/https://raw.githubusercontent.com/ngo5/IPTV/main/result.m3u"),
]

MIN_CH = 20      # 低于此台数视为"不健康/死源"
TOP_N = 10       # 最终保留的直播源数量


def fetch(url, tries=3, timeout=45):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            last = e
            time.sleep(3)
    raise RuntimeError(f"fetch failed after {tries} tries: {url} -> {last}")


def main():
    scored = []
    for key, name, url in POOL:
        try:
            raw = fetch(url)
            cleaned = clean_lives.clean_m3u(raw)
            n = cleaned.count("#EXTINF")
            scored.append((key, name, url, cleaned, n))
            print(f"  {'OK ' if n >= MIN_CH else 'LOW'} {name:<16} {n} 台")
        except Exception as e:
            print(f"  FAIL {name:<16} 抓取失败: {type(e).__name__}")

    healthy = [s for s in scored if s[4] >= MIN_CH]
    healthy.sort(key=lambda x: -x[4])
    chosen = healthy[:TOP_N]

    # 健康源不足时，用已抓到的（哪怕偏低）补齐，保证数量
    if len(chosen) < TOP_N:
        for s in scored:
            if len(chosen) >= TOP_N:
                break
            if s not in chosen:
                chosen.append(s)

    print(f"\n选中 {len(chosen)} 个（探测 {len(scored)} 个，健康≥{MIN_CH}台 {len(healthy)} 个）")
    if len(healthy) < TOP_N:
        print(f"  ! 健康源仅 {len(healthy)} 个 < {TOP_N}，已用低质量源补齐（建议扩充 POOL）")

    lives = []
    for key, name, url, cleaned, n in chosen:
        fn_root = os.path.join(LIVES, f"{key}_clean.m3u")
        with open(fn_root, "w", encoding="utf-8") as fh:
            fh.write(cleaned)
        lives.append({"name": f"{name}（{n}台）", "url": f"{BASE}/lives/{key}_clean.m3u"})

    # 改写三个根配置的 lives 数组（其余字段原样保留）
    for cfg in ["tvbox_curated.json", "tvbox_subscription.json"]:
        p = os.path.join(ROOT, cfg)
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        d["lives"] = lives
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  已更新 {cfg} 的 lives（{len(lives)} 个）")

    # 同步生成「直播专用」拆分文件（供没有订阅入口的 TVBox 直接粘进"直播源"框）
    parses, rules = [], []
    curated_path = os.path.join(ROOT, "tvbox_curated.json")
    if os.path.exists(curated_path):
        try:
            _c = json.load(open(curated_path, encoding="utf-8"))
            parses, rules = _c.get("parses", []), _c.get("rules", [])
        except Exception:
            pass
    if not parses:
        parses = [{"name": "阿雪解析", "type": 1, "url": "https://jx.xmflv.com/?url="}]
    if not rules:
        rules = ["vip", "tpl", "ju", "qb", "iqiyi", "qiyi", "letv", "sohu", "qq",
                 "wetv", "mgtv", "bilibili", "wasu", "tvid", "renrenmi"]
    with open(os.path.join(ROOT, "tvbox_lives.json"), "w", encoding="utf-8") as fh:
        json.dump({"lives": lives, "parses": parses, "rules": rules}, fh, ensure_ascii=False, indent=2)
    print(f"  已生成 tvbox_lives.json（直播专用，{len(lives)} 源）")

    print("done")


if __name__ == "__main__":
    main()
