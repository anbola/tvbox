#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成「极速版」直播源 lives/fast.m3u：
  - 只收国内 CDN 流为主的源（mzky 咪咕中转 + cn 央视卫视精选）
  - 砍掉所有「境外图床」台标（imgur / tvchinese / .je / 未知域名），
    仅保留 gitee / ghfast / github / jsdelivr 等国内可达图床，
    从源头消除「划台等图」的卡顿。
  - 剔除明确境外流的条目（如 .je 泽西岛节点）。
目的：让 TVBox 直播页秒开、换台即播，不再被上千境外台标/流拖累。
"""
import os, re, io

HERE = os.path.dirname(os.path.abspath(__file__))
LIVES = os.path.join(HERE, "lives")
os.makedirs(LIVES, exist_ok=True)

# 候选源（本地优先，否则从 GitHub Pages 拉）
SOURCES = ["mzky_clean.m3u", "cn_clean.m3u", "yang_clean.m3u"]

# 允许保留的台标图床（国内可达）；其余一律删除，避免境外图卡列表
LOGO_OK = ("gitee.com", "ghfast.top", "ghproxy.com", "githubusercontent.com",
           "jsdelivr.net", "loliapi.com", "7x24cc.com")

# 明确境外/慢节点（流地址 host 命中则整条丢弃）
STREAM_DROP = (".je", ".gs", ".sh", ".gg", ".to", ".ru", ".uk", ".us", ".de", ".fr", ".nl")

from urllib.parse import urlparse

def fetch_local_or_pages(name):
    p = os.path.join(LIVES, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8", errors="ignore") as f:
            return f.read()
    import urllib.request
    url = "https://anbola.github.io/tvbox/lives/" + name
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  拉取 {name} 失败: {e}")
        return ""

LOGO_RE = re.compile(r'(tvg-logo=")[^"]*(")')

def keep_logo(ext):
    m = re.search(r'tvg-logo="([^"]*)"', ext)
    if not m:
        return ext
    host = urlparse(m.group(1)).netloc.lower()
    if any(host.endswith(ok) for ok in LOGO_OK):
        return ext
    # 删除境外/未知台标属性（保留其余字段，列表秒开）
    return LOGO_RE.sub(r'\1\2', ext)

def parse_items(text):
    items = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not lines[i].startswith("#EXTINF"):
            i += 1; continue
        j = i + 1
        while j < len(lines) and lines[j].startswith("#EXT") and not lines[j].startswith("#EXTINF"):
            j += 1
        if j < len(lines) and not lines[j].startswith("#EXTINF"):
            items.append((lines[i], lines[j]))
            i = j + 1
        else:
            i += 1
    return items

def main():
    out = ["#EXTM3U"]
    total = 0
    dropped = 0
    for src in SOURCES:
        txt = fetch_local_or_pages(src)
        if not txt:
            continue
        header = ""
        for ln in txt.splitlines():
            if ln.startswith("#EXTM3U"):
                header = ln; break
        for ext, url in parse_items(txt):
            host = urlparse(url.strip()).netloc.lower()
            if any(host.endswith(d) for d in STREAM_DROP):
                dropped += 1; continue
            ext2 = keep_logo(ext)
            out.append(ext2)
            out.append(url.strip())
            total += 1
        print(f"  {src}: 采用后 {total} 台（累计），本源丢弃境外流 {dropped} 条")
    content = "\n".join(out) + "\n"
    dp = os.path.join(LIVES, "fast.m3u")
    with open(dp, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n→ lives/fast.m3u 生成：{total} 台，{len(content.encode('utf-8'))} 字节（已砍境外台标/境外流）")

if __name__ == "__main__":
    main()
