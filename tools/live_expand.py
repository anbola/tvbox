#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高清补源：从 lives/pool.m3u 里给「只有 720x576 标清」的频道找 1080p 线路。

为什么需要：720x576 是 PAL 标清，IJK 内核不认它的宽高比标记，一律按 4:3 显示，
电视上就是"央视被压成方屏"。软件设置 16:9 无效（拉伸只能在播放器层，配置层
改不了）。唯一干净的办法是给每个频道排一条真 1080p 的流。

做法：
  1) 读 main.m3u 得到当前频道表 + 每台已有线路的分辨率
  2) 只挑「没有 1080p」的频道作为目标
  3) 从 pool.m3u 找同名候选（未测过的），逐条拉首个 TS 分片解析 PAT/PMT + SPS
  4) 输出 _probe/codecs2.json（与 codecs.json 同结构，供 build_live.py 合并）

优先级：陕西移动自家 CDN > 央视官方 CDN(cntv) > 咪咕 > 其他
"""
import json
import os
import re
import socket
import ssl
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from codec_probe import (CTX, UA, align_ts, fetch, first_segment, packets,
                         parse_pat, parse_pmt, sps_from_ts)
import build_live as B

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL = os.path.join(ROOT, "lives", "pool.m3u")
MAIN = os.path.join(ROOT, "lives", "main.m3u")
OUT = os.path.join(ROOT, "_probe", "codecs2.json")

GOOD_DOMAIN = ("chinamobile", "cntv", "kcdnvip", "migu", "gitv", "cctv")


def domain_rank(url):
    d = url.split("/")[2] if "://" in url else ""
    for i, k in enumerate(GOOD_DOMAIN):
        if k in d:
            return i
    return len(GOOD_DOMAIN)


def parse_m3u(path):
    out = []
    name = None
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if line.startswith("#EXTINF"):
            m = re.search(r",(.+)$", line)
            name = m.group(1).strip() if m else ""
        elif line.startswith("http") and name is not None:
            out.append((name, line))
            name = None
    return out


def parse_ts_info(raw):
    """返回 dict(codec,w,h,audio) 或 None"""
    buf = align_ts(raw)
    if not buf:
        return None
    pmt = parse_pat(buf)
    if not pmt:
        return None
    res = parse_pmt(buf, pmt)
    if not res:
        return None
    vid, audios = res
    if not vid:
        return None
    return dict(codec={0x1B: "avc", 0x24: "hevc", 0x02: "mpeg2"}.get(vid, hex(vid)),
                w=None, h=None, audio=audios, buf=buf, vid=vid)


def probe(item):
    name, url = item
    rec = dict(name=name, url=url, kbps=0, codec=None, w=None, h=None,
               audio=[], ok=False, domain=url.split("/")[2] if "://" in url else "")
    try:
        seg = first_segment(url)
        if not seg:
            return rec
        raw = fetch(seg, 400000, timeout=8)
        info = parse_ts_info(raw)
        if not info:
            return rec
        rec["codec"] = info["codec"]
        rec["audio"] = [B_audio(a) for a in sorted(set(info["audio"]))]
        if info["vid"] == 0x1B:
            wh = sps_from_ts(info["buf"], info["vid"])
            if wh:
                rec["w"], rec["h"] = wh
        # 码率：用分片真实字节数 / #EXTINF 时长。
        # 早先版本直接拿"下载到的前 900KB"当分片大小，导致所有流都被算成 1440kbps，
        # 排序完全失真 —— 这里改成查 Content-Length（HEAD，失败退化为 Range 请求）。
        dur = extinf_duration(url)
        size = seg_size(seg)
        if dur and size:
            rec["kbps"] = round(size * 8 / dur / 1000)
        rec["ok"] = True
    except Exception:
        pass
    return rec


def seg_size(u):
    """分片真实字节数：先 HEAD，部分老服务器不支持 HEAD 再用 Range 拿 Content-Range。"""
    try:
        req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8, context=CTX) as r:
            n = int(r.headers.get("Content-Length") or 0)
            if n:
                return n
    except Exception:
        pass
    try:
        req = urllib.request.Request(u, headers={"User-Agent": UA, "Range": "bytes=0-1"})
        with urllib.request.urlopen(req, timeout=8, context=CTX) as r:
            cr = r.headers.get("Content-Range") or ""
            if "/" in cr:
                return int(cr.rsplit("/", 1)[1])
    except Exception:
        pass
    return 0


def B_audio(a):
    from codec_probe import AUDIO_NAME
    return AUDIO_NAME.get(a, hex(a))


def extinf_duration(m3u8_url):
    try:
        txt = fetch(m3u8_url, 60000, timeout=6).decode("utf-8", "ignore")
        m = re.search(r"#EXTINF:\s*([\d.]+)", txt)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def main():
    cur = {}
    for name, url in parse_m3u(MAIN):
        cur.setdefault(B.normalize(name), []).append(url)

    known = {}
    for f in ("codecs.json", "codecs2.json"):
        p = os.path.join(ROOT, "_probe", f)
        if os.path.exists(p):
            for r in json.load(open(p, encoding="utf-8")):
                known[r["url"]] = r

    # 目标：当前没有 1080p 的频道
    target = set()
    for ch, urls in cur.items():
        if not any((known.get(u) or {}).get("h") == 1080 for u in urls):
            target.add(ch)

    # 再加一类：池里有、但主列表完全缺失的央视频道/卫视/陕西本地台
    # （v2.2 因"只有 HEVC"被剔掉的 CCTV-3/5/6/8 就在这一类，补到 AVC 就该回来）
    pool_names = {B.normalize(n) for n, _ in parse_m3u(POOL)}
    for ch in pool_names:
        if ch and ch not in cur and B.group_of(ch) in ("央视", "卫视", "陕西本地"):
            target.add(ch)
    print(f"频道总数 {len(cur)}，需补源的 {len(target)} 个")

    cands = []
    seen = set()
    for name, url in parse_m3u(POOL):
        std = B.normalize(name)
        if std not in target:
            continue
        if url in seen or url in known:
            continue
        seen.add(url)
        cands.append((std, url))
    cands.sort(key=lambda x: domain_rank(x[1]))
    print(f"候选线路 {len(cands)} 条，开始探测…")

    socket.setdefaulttimeout(20)
    results = []
    ex = ThreadPoolExecutor(max_workers=24)
    futs = [ex.submit(probe, (n, u)) for n, u in cands]
    done = 0
    try:
        for f in as_completed(futs, timeout=300):
            rec = f.result()
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(cands)}", flush=True)
            if rec["ok"]:
                results.append(rec)
    except TimeoutError:
        print("⚠ 高清补源超时，仅保留已完成结果", flush=True)
        for f in futs:
            if f.done():
                try:
                    results.append(f.result())
                except Exception:
                    pass
    finally:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    ok = [r for r in results if r["ok"]]
    hd = [r for r in ok if r["h"] == 1080]
    print(f"探测完成：可用 {len(ok)} 条，其中 1080p {len(hd)} 条")

    # 合并而不是覆盖：codecs2.json 要跨多次运行累积，否则上一轮补到的线路会被冲掉
    merged = {}
    if os.path.exists(OUT):
        for r in json.load(open(OUT, encoding="utf-8")):
            if r.get("ok"):
                merged[r["url"]] = r
    before = len(merged)
    for r in ok:
        merged[r["url"]] = r
    allr = list(merged.values())
    json.dump(allr, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"已写入 {OUT}：本轮 +{len(allr) - before} 条，累计 {len(allr)} 条")


if __name__ == "__main__":
    main()
