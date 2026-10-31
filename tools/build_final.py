#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性生成最终交付物：
  1) lives/main.m3u  —— 只含「实测可播」的央视/卫视流，每台取最快 3 条
  2) tvbox_clean.json —— 单文件配置（sites 只保留总量≥阈值的分类 + 内置直播）

用法: python tools/build_final.py
依赖: _probe/working.json（由 tools/probe_streams.py 生成）
"""
import json
import os
import re
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0"}

SITES = [
    ("ffzy5", "🎬 非凡", "https://ffzy5.tv/api.php/provide/vod/"),
    ("hhzy", "🎬 火狐", "https://hhzyapi.com/api.php/provide/vod/"),
    ("jyzy", "🎬 金鹰", "https://jyzyapi.com/api.php/provide/vod/"),
    ("dbzy", "🎬 豆瓣", "https://dbzy.tv/api.php/provide/vod/"),
    ("bfzy", "🎬 暴风", "https://bfzyapi.com/api.php/provide/vod/"),
]

# 分类展示优先级
PRIORITY = ["电影", "电影片", "电视剧", "连续剧", "动作片", "喜剧片", "剧情片", "科幻片",
            "爱情片", "恐怖片", "战争片", "综艺", "综艺片", "动漫", "动漫片", "动画片",
            "纪录片", "记录片", "国产剧", "香港剧", "韩国剧", "欧美剧", "短剧"]
# 排除成人/擦边分类
BLOCK = ("伦理", "福利", "写真", "成人", "情色", "自拍", "偷拍", "里番", "无码")


def api_get(url, timeout=12, retries=3):
    """带重试的请求：采集站偶发超时很常见，绝不能因此丢掉整个站点。"""
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def canon(name):
    s = re.sub(r"[〔\[（(][^〕\]）)]*[〕\]）)]", "", name)
    s = s.replace("HD", "").replace("hd", "").replace("4K", "").replace("高清", "").replace("标清", "")
    s = re.sub(r"\s+", "", s)
    return s.strip()


def build_live():
    src = os.path.join(ROOT, "_probe", "working.json")
    data = json.load(open(src, encoding="utf-8"))
    chans = {}
    for name, items in data.items():
        c = canon(name)
        chans.setdefault(c, []).extend(items)

    def order_key(c):
        m = re.search(r"央视([一二三四五六七八九十]+)套", c)
        if m:
            num = "一二三四五六七八九十".index(m.group(1)[0]) + 1 if m.group(1)[0] in "一二三四五六七八九十" else 99
            return (0, num, c)
        if "卫视" in c:
            return (1, 0, c)
        if "CCTV" in c.upper():
            return (0, 50, c)
        return (2, 0, c)

    lines = ["#EXTM3U"]
    total = 0
    JUNK = ("春晚", "测试", "彩条", "广告", "备用", "回看", "导视", "试播")
    for c in sorted(chans, key=order_key):
        if any(k in c for k in JUNK):
            continue
        items = sorted(chans[c], key=lambda x: x["ms"])[:3]
        group = "央视" if ("央视" in c or "CCTV" in c.upper() or "中国教育" in c) else ("卫视" if "卫视" in c else "其他")
        for it in items:
            # 不写 tvg-logo：原台标走 ghfast.top（国内不可达），会拖慢列表加载
            lines.append(
                f'#EXTINF:-1 tvg-name="{c}" group-title="{group}",{c}'
            )
            lines.append(it["url"])
            total += 1
    out = os.path.join(ROOT, "lives", "main.m3u")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"lives/main.m3u: {len(chans)} 个频道 / {total} 条流")
    return len(chans), total


PREV_SITES = []
_prev_path = os.path.join(ROOT, "tvbox_clean.json")
if os.path.exists(_prev_path):
    try:
        PREV_SITES = json.load(open(_prev_path, encoding="utf-8")).get("sites", []) or []
    except Exception:
        PREV_SITES = []


def build_sites():
    out_sites = []
    for key, disp, base in SITES:
        try:
            classes = api_get(base + "?ac=list").get("class") or []
        except Exception as e:
            print(f"  {disp}: 取分类失败({type(e).__name__})，保留上一版条目")
            prev = {s.get("key"): s for s in PREV_SITES}.get(key)
            if prev:
                out_sites.append(prev)
            continue
        cands = [c for c in classes
                 if c.get("type_name") and not any(b in c.get("type_name") for b in BLOCK)]
        names = [c.get("type_name") for c in cands]
        idmap = {c.get("type_name"): c.get("type_id") for c in cands}
        ordered = [n for n in PRIORITY if n in idmap] + [n for n in names if n not in PRIORITY]

        def check(n):
            try:
                d = api_get(base + f"?ac=videolist&t={idmap[n]}&pg=1")
                return n, int(d.get("total") or len(d.get("list") or []))
            except Exception:
                return n, 0

        with ThreadPoolExecutor(max_workers=10) as ex:
            totals = dict(ex.map(check, ordered[:16]))

        # 阈值规则（2026-10-31 实测）：这 5 个采集站的「电影/电视剧」总分类本身就是空的
        # （0~14 条），真正的片源全在子分类里（动作片/剧情片/喜剧片…）。
        # 因此：主分类门槛 ≥30（避免点进去只有一两条），子分类门槛 ≥200。
        MAIN = ("电影", "电影片", "电视剧", "连续剧", "综艺", "综艺片",
                "动漫", "动漫片", "纪录片", "记录片")
        picked = [n for n in ordered
                  if totals.get(n, 0) >= (30 if n in MAIN else 200)]
        # 保障每站至少 5 个分类：不足则放宽子分类门槛
        if len(picked) < 5:
            picked = [n for n in ordered if totals.get(n, 0) >= 50]
        picked = sorted(picked, key=lambda n: PRIORITY.index(n) if n in PRIORITY else 99)[:10]
        detail = "、".join(f"{n}({totals.get(n,0)})" for n in picked)
        print(f"  {disp}: {len(picked)} 个分类 -> {detail}")
        out_sites.append({
            "key": key,
            "name": disp,
            "type": 1,
            "api": base,
            "searchable": 1,
            "quickSearch": 1,
            "filterable": 0,
            "categories": picked,
        })
    return out_sites


def main():
    print("=" * 60)
    print("1) 生成直播源")
    n_ch, n_url = build_live()
    print("\n2) 生成点播站点（只保留有内容的分类）")
    sites = build_sites()

    cfg = {
        "sites": sites,
        "lives": [{
            "name": f"📺 央视·卫视 {n_ch} 台（逐条实测可播）",
            "url": "https://anbola.github.io/tvbox/lives/main.m3u",
        }],
    }
    p = os.path.join(ROOT, "tvbox_clean.json")
    json.dump(cfg, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n3) 已生成 tvbox_clean.json（{os.path.getsize(p)} 字节，"
          f"sites={len(sites)} lives={len(cfg['lives'])}）")
    print("   注意：已去除 wallpaper/logo/parses/rules/doh/spider，"
          "最小化配置可避免「配置解析失败」")


if __name__ == "__main__":
    main()
