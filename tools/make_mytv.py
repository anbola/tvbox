#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 anbola/tvbox 的直播源 m3u 合并成「MyTV（我的电视·〇）」订阅源。

产出两个文件：
  - mytv.m3u      全量（所有分组，约 7900 台），适合大屏 / 想看全部的
  - mytv_lite.m3u 精简（央视+卫视+4K·8K+港澳台+体育+少儿+影视+综艺，约 3800 台，
                    体积约一半、去掉自动 EPG 头），手机 MyTV 秒开不卡

MyTV 支持的直播源格式：m3u / txt / json（my-tv-0）；m3u / TVBox / XML（mytv-android）。
这里产出通用 m3u，两种 MyTV 都能直接导入（在「自定义直播源 / 远程配置」填本文件 URL）。

合并规则：
  - 各源 m3u 的 #EXTM3U 头只保留一个；
  - 每个 #EXTINF + 其后播放地址（及 #EXTVLCOPT 等选项行）原样保留；
  - group-title 沿用各源的统一分组（央视/卫视/地方台/4K·8K/…），不同源的同组频道会
    自然合并为多条线路，MyTV 播放失败可自动切换下一线路（多线路容错）。
用法：python make_mytv.py [lives_dir] [out_full_m3u] [out_lite_m3u]
"""
import os, sys, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # 仓库根（_deploy 的上级）

# 与 tvbox_lives.json 里一致的源 key（决定合并顺序）
SOURCES = ["ccsh", "bigbig", "guovin", "cn", "mzky",
           "yang", "kimentanm", "yanggather", "bestfan", "yuechan"]

# 精简版（手机 MyTV 秒开）只保留这些分组
LITE_WHITELIST = re.compile(r'央视|卫视|4K|8K|港澳|体育|少儿|影视|综艺')


def group_of(block):
    for line in block:
        if line.startswith('#EXTINF'):
            m = re.search(r'group-title="([^"]*)"', line)
            return m.group(1) if m else ''
    return ''


def combine(lives_dir: str, out_full: str, out_lite: str = None):
    entries = []  # 每个元素是一串行（含 #EXTINF + 地址 + 选项）
    per_source = {}
    for key in SOURCES:
        fp = os.path.join(lives_dir, f"{key}_clean.m3u")
        if not os.path.exists(fp):
            print(f"  - 跳过缺失: {fp}")
            continue
        # 按块读取：遇到 #EXTINF 开始一个新条目，直到下一个 #EXTINF 或文件尾
        cur = []
        n = 0
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\n").rstrip("\r")
                if line.startswith("#EXTM3U"):
                    continue  # 丢弃各源自己的头
                if line.startswith("#EXTINF"):
                    if cur:
                        entries.append(cur); n += 1
                    cur = [line]
                else:
                    if line.strip() == "":
                        continue
                    cur.append(line)
            if cur:
                entries.append(cur); n += 1
        per_source[key] = n
        print(f"  + {key:<12} {n} 条")
    total = sum(per_source.values())

    with open(out_full, "w", encoding="utf-8") as f:
        f.write('#EXTM3U\n')
        for blk in entries:
            f.write("\n".join(blk) + "\n")
    print(f"\n全量合并：{total} 条频道 -> {out_full} ({os.path.getsize(out_full)} B)")

    if out_lite:
        lite = [b for b in entries if LITE_WHITELIST.search(group_of(b))]
        with open(out_lite, "w", encoding="utf-8") as f:
            f.write('#EXTM3U\n')
            for blk in lite:
                f.write("\n".join(blk) + "\n")
        print(f"精简版：{len(lite)} 条频道 -> {out_lite} ({os.path.getsize(out_lite)} B)")
    return total


if __name__ == "__main__":
    lives_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "lives")
    out_full = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "mytv.m3u")
    out_lite = sys.argv[3] if len(sys.argv) > 3 else os.path.join(ROOT, "mytv_lite.m3u")
    print(f"lives_dir = {lives_dir}")
    print(f"out_full  = {out_full}")
    print(f"out_lite  = {out_lite}")
    combine(lives_dir, out_full, out_lite)
