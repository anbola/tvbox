#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成最终单文件配置 tvbox_clean.json

输入：_probe/vod_report.json（点播站真实测速结果）+ lives/main.m3u
规则：
  1) 只保留"视频分片实测 ≥ MIN_VOD_KBPS"的站，按视频速度降序
  2) 每站分类逐类查 total，只保留"真有货"的分类（total ≥ MIN_TOTAL）
  3) 只有最快的 2 个站开 quickSearch（搜索时并发查询，站越多越慢）
  4) 配置只留 sites + lives 两项，无任何外部依赖（不会"配置解析失败"）
"""
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "okhttp/3.15.0"

MIN_VOD_KBPS = 1200     # 视频分片低于此值会卡
MIN_TOTAL = 100         # 分类至少这么多片才算"有货"
MAX_SITES = 4           # 站越多首页越慢
MAX_CATS = 10

PRIORITY = ["电影", "电影片", "电视剧", "连续剧", "国产剧", "港台剧", "日韩剧", "欧美剧",
            "动作片", "喜剧片", "爱情片", "科幻片", "恐怖片", "剧情片", "战争片", "犯罪片",
            "悬疑片", "冒险片", "奇幻片", "武侠片", "灾难片", "邵氏电影", "短剧",
            "综艺", "综艺片", "大陆综艺", "港台综艺", "日韩综艺",
            "动漫", "动漫片", "动画片", "国产动漫", "日韩动漫", "欧美动漫",
            "纪录片", "记录片", "解说", "体育"]


def get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def cat_total(api, tid):
    try:
        d = get_json(f"{api}?ac=videolist&t={urllib.parse.quote(str(tid))}&pg=1", timeout=12)
        return int(d.get("total") or len(d.get("list") or []))
    except Exception:
        return 0


def build_site(site, quick):
    api = site["api"]
    try:
        classes = get_json(api + "?ac=list").get("class") or []
    except Exception as e:
        print(f"  {site['name']}: 取分类失败 {type(e).__name__}")
        return None
    idmap = {c["type_name"]: c["type_id"] for c in classes if c.get("type_name")}
    names = [n for n in PRIORITY if n in idmap]
    # 候选不足时补其它分类
    if len(names) < 8:
        for c in classes:
            n = c.get("type_name")
            if n and n not in names:
                names.append(n)

    cand = [(n, idmap[n]) for n in names[:20]]
    with ThreadPoolExecutor(max_workers=8) as ex:
        totals = dict(zip([c[0] for c in cand], ex.map(lambda c: cat_total(api, c[1]), cand)))

    picked = [n for n in names[:20] if totals.get(n, 0) >= MIN_TOTAL]
    if len(picked) < 6:
        # 放宽阈值
        picked = [n for n in names[:20] if totals.get(n, 0) >= 30][:8]
    picked = sorted(picked, key=lambda n: PRIORITY.index(n) if n in PRIORITY else 99)[:MAX_CATS]
    if not picked:
        print(f"  {site['name']}: 无有货分类，丢弃")
        return None

    print(f"  {site['name']:<8} 视频{site['vod_kbps']:>7.0f}kbps  分类{len(picked)}: {picked}")
    return {
        "name": site["name"],
        "type": 1,
        "api": api,
        "searchable": 1,
        "quickSearch": 1 if quick else 0,
        "filterable": 0,
        "categories": picked,
    }


def main():
    rep = json.load(open(os.path.join(ROOT, "_probe", "vod_report.json"), encoding="utf-8"))
    good = [r for r in rep if r.get("vod_kbps", 0) >= MIN_VOD_KBPS and not r.get("err")]
    good.sort(key=lambda r: (-r["vod_kbps"], r.get("list_ms") or 9999))
    good = good[:MAX_SITES]
    if not good:
        raise SystemExit("没有达标点播站，请先跑 tools/vod_probe.py")

    print(f"入选点播站 {len(good)} 个（视频速度降序）：")
    sites = []
    for i, r in enumerate(good):
        s = build_site(r, quick=(i < 2))
        if s:
            sites.append(s)

    cfg = {
        "sites": sites,
        "lives": [{
            "name": "📺 央视·卫视·陕西本地（实测排序）",
            "url": "https://anbola.github.io/tvbox/lives/main.m3u",
        }],
    }
    out = os.path.join(ROOT, "tvbox_clean.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {out}")
    print(f"站点 {len(sites)} 个 | 顶层键 {list(cfg.keys())}")


if __name__ == "__main__":
    main()
