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
import hashlib
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
MAX_CATS = 14

# 分类优先级：主分类 → 电影子类 → 剧集 → 综艺 → 动漫 → 纪录片 → 其它
# 注意 1：实测这些采集站的"电影/电视剧"主分类服务器端普遍是 0 条，
#         真正有货的是子分类（动作片/剧情片/国产剧…），所以子分类必须排在能入选的位置。
# 注意 2：伦理片/理论片 属于成人内容，家用电视必须剔除，故不在列表中。
PRIORITY = [
    "电影", "电影片", "电视剧", "连续剧",
    "动作片", "喜剧片", "剧情片", "科幻片", "爱情片", "恐怖片",
    "国产剧", "欧美剧", "香港剧", "韩国剧",
    "综艺", "综艺片", "大陆综艺",
    "动画片", "动漫", "动漫片", "国产动漫",
    "纪录片", "记录片",
    "战争片", "犯罪片", "悬疑片", "冒险片", "奇幻片", "武侠片", "灾难片",
    "短剧", "体育", "解说", "预告片", "其他",
]


def get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def site_key(api):
    """给每个站点生成稳定的 ASCII key。

    TVBox 用 key 作为站点唯一标识（首页标签、搜索、历史记录都依赖它）。
    v2.0 曾经漏掉这个字段，导致首页站点列表全部失效 —— 必须保留。
    """
    host = urllib.parse.urlparse(api).netloc.split(":")[0]
    base = re.sub(r"[^a-z0-9]", "", host.split(".")[0].lower()) or "site"
    return base + "_" + hashlib.md5(api.encode("utf-8")).hexdigest()[:4]


def force_https(api):
    """统一走 https：Android 9+ 默认禁止明文 http，混用会让部分站点直接空列表。"""
    return re.sub(r"^http://", "https://", api, count=1)


def cat_total(api, tid):
    try:
        d = get_json(f"{api}?ac=videolist&t={urllib.parse.quote(str(tid))}&pg=1", timeout=12)
        return int(d.get("total") or len(d.get("list") or []))
    except Exception:
        return 0


def build_site(site, quick):
    api = force_https(site["api"])
    try:
        classes = get_json(api + "?ac=list").get("class") or []
    except Exception as e:
        print(f"  {site['name']}: 取分类失败 {type(e).__name__}")
        return None
    idmap = {c["type_name"]: c["type_id"] for c in classes if c.get("type_name")}
    names = [n for n in PRIORITY if n in idmap]
    # 候选不足时补其它分类（保持服务器顺序）
    if len(names) < 12:
        for c in classes:
            n = c.get("type_name")
            if n and n not in names:
                names.append(n)

    # 关键：对【全部候选分类】查 total，而不是只查前 20 个，
    # 否则"动画片/纪录片/短剧"这类排在后面但真有货的分类会被漏掉。
    cand = [(n, idmap[n]) for n in names[:30]]
    with ThreadPoolExecutor(max_workers=10) as ex:
        totals = dict(zip([c[0] for c in cand],
                          ex.map(lambda c: cat_total(api, c[1]), cand)))

    picked = [n for n in names[:30] if totals.get(n, 0) >= MIN_TOTAL]
    if len(picked) < 6:
        picked = [n for n in names[:30] if totals.get(n, 0) >= 30][:8]
    picked = sorted(picked, key=lambda n: PRIORITY.index(n) if n in PRIORITY else 99)[:MAX_CATS]
    if not picked:
        print(f"  {site['name']}: 无有货分类，丢弃")
        return None

    detail = ", ".join(f"{n}{totals.get(n, 0)}" for n in picked)
    print(f"  {site['name']:<8} 视频{site['vod_kbps']:>7.0f}kbps  分类{len(picked)}: [{detail}]")
    return {
        "key": site_key(api),
        "name": site["name"],
        "type": 1,
        "api": api,
        "searchable": 1,
        "quickSearch": 1 if quick else 0,
        "filterable": 0,
        "categories": picked,
    }


def main():
    # 优先用"多次采样取中位数"的 vod_final.json（更稳），退回单次报告
    p_final = os.path.join(ROOT, "_probe", "vod_final.json")
    p_report = os.path.join(ROOT, "_probe", "vod_report.json")
    src = p_final if os.path.exists(p_final) else p_report
    rep = json.load(open(src, encoding="utf-8"))
    print(f"数据来源: {os.path.basename(src)}")
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
        # playerType：0 系统 / 1 IJK / 2 EXO（见 README「直播参数说明」）
        # 必须钉死 1(IJK)：微鲸 WTV55K1 用 EXO 硬解这批源的 MP3 音频时，
        # Android 5.0.2 的 ACodec 会在 OMX_IndexParamAudioMp3 上 CHECK 失败直接 abort，
        # 表现为"点直播闪一下就退出"。IJK + 软解可绕开该平台缺陷。
        "lives": [{
            "name": "央视·卫视·陕西本地（实测排序）",
            "url": "https://anbola.github.io/tvbox/lives/main.m3u",
            "playerType": "1",
        }],
    }
    out = os.path.join(ROOT, "tvbox_clean.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {out}")
    print(f"站点 {len(sites)} 个 | 顶层键 {list(cfg.keys())}")


if __name__ == "__main__":
    main()
