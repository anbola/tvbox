#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直播流真实测速探针（不是"能不能连"，而是"能不能流畅播"）

对每条流执行：
  1) 拉 m3u8 播放列表（跟随 302 跳转）—— 记录 playlist_ms
  2) 若是 master playlist（多码率），选最高带宽变体
  3) 取"直播边缘"分片（倒数第 1~2 个，避免首片缓存失真）
  4) 真实下载该 TS 分片，测量 首字节延迟(TTFB) 与 实际码率(kbps)
  5) 判定流畅度等级

输出 speeds.json：{url: {name, group, ok, kbps, ttfb_ms, playlist_ms, seg_bytes, level, reason}}
"""
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "_probe")
UA = "okhttp/3.15.0"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

PLAYLIST_TIMEOUT = 5
SEG_TIMEOUT = 7
SEG_MAX_BYTES = 4 * 1024 * 1024   # 单分片最多读 4MB，够算码率
SEG_MAX_SECONDS = 4.0              # 最多读 4 秒，避免慢流拖死整体


def _open(url, timeout, headers=None):
    h = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(req, timeout=timeout, context=CTX)


def fetch_text(url, timeout=PLAYLIST_TIMEOUT):
    """拉取文本，返回 (text, elapsed_ms)。跟随跳转由 urllib 自动处理。"""
    t0 = time.time()
    with _open(url, timeout) as r:
        raw = r.read()
        enc = "utf-8"
        ct = r.headers.get("Content-Type", "") or ""
        m = re.search(r"charset=([\w-]+)", ct, re.I)
        if m:
            enc = m.group(1)
        try:
            txt = raw.decode(enc, "ignore")
        except Exception:
            txt = raw.decode("utf-8", "ignore")
    return txt, int((time.time() - t0) * 1000)


def pick_variant(base_url, text):
    """master playlist -> 选最高 BANDWIDTH 的变体 URL"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    best = None
    best_bw = -1
    for i, l in enumerate(lines):
        if l.startswith("#EXT-X-STREAM-INF"):
            m = re.search(r"BANDWIDTH=(\d+)", l)
            bw = int(m.group(1)) if m else 0
            for nxt in lines[i + 1:]:
                if not nxt.startswith("#"):
                    if bw > best_bw:
                        best_bw = bw
                        best = urllib.parse.urljoin(base_url, nxt)
                    break
    return best, best_bw


def parse_segments(base_url, text):
    """返回分片 URL 列表"""
    segs = []
    for l in text.splitlines():
        s = l.strip()
        if not s or s.startswith("#"):
            continue
        segs.append(urllib.parse.urljoin(base_url, s))
    return segs


def measure_segment(url):
    """下载一个分片，返回 (kbps, ttfb_ms, total_ms, nbytes)"""
    t0 = time.time()
    kbps = 0.0
    ttfb = 0
    n = 0
    with _open(url, SEG_TIMEOUT) as r:
        ttfb = int((time.time() - t0) * 1000)
        chunks = []
        while True:
            buf = r.read(64 * 1024)
            if not buf:
                break
            chunks.append(buf)
            n += len(buf)
            el = time.time() - t0
            if n >= SEG_MAX_BYTES or el >= SEG_MAX_SECONDS:
                break
    total_ms = int((time.time() - t0) * 1000)
    if total_ms > 0:
        kbps = n * 8 / (total_ms / 1000) / 1000
    return kbps, ttfb, total_ms, n


def test_one(item):
    name, group, url = item
    res = {
        "name": name, "group": group, "url": url,
        "ok": False, "kbps": 0.0, "ttfb_ms": 0, "playlist_ms": 0,
        "seg_bytes": 0, "level": "dead", "reason": "",
    }
    try:
        text, pms = fetch_text(url)
        res["playlist_ms"] = pms
        if "#EXTM3U" not in text:
            res["reason"] = "非m3u8"
            return res

        # master playlist -> 选变体
        if "#EXT-X-STREAM-INF" in text:
            var, bw = pick_variant(url, text)
            if not var:
                res["reason"] = "无变体"
                return res
            text, pms2 = fetch_text(var)
            res["playlist_ms"] += pms2
            if "#EXTM3U" not in text:
                res["reason"] = "变体无效"
                return res
            base = var
        else:
            base = url

        segs = parse_segments(base, text)
        if not segs:
            res["reason"] = "无分片"
            return res

        # 优先测直播边缘（倒数第2个），失败再退到倒数第1个
        candidates = segs[-2:] if len(segs) >= 2 else segs
        candidates = list(reversed(candidates))
        last_err = ""
        for seg in candidates[:2]:
            try:
                kbps, ttfb, total_ms, n = measure_segment(seg)
                if n <= 0:
                    last_err = "分片空"
                    continue
                res.update(kbps=round(kbps, 1), ttfb_ms=ttfb,
                           seg_bytes=n, ok=True)
                break
            except Exception as e:
                last_err = type(e).__name__
        if not res["ok"]:
            res["reason"] = last_err or "分片失败"
            return res

        k = res["kbps"]
        if k >= 4000 and res["ttfb_ms"] <= 800:
            res["level"] = "超清流畅"      # 4K/高码率
        elif k >= 1800 and res["ttfb_ms"] <= 1200:
            res["level"] = "高清流畅"      # 1080p
        elif k >= 900:
            res["level"] = "标清可用"      # 720p/576p
        elif k >= 350:
            res["level"] = "勉强"          # 会卡
        else:
            res["level"] = "太慢"
        return res
    except urllib.error.HTTPError as e:
        res["reason"] = f"HTTP{e.code}"
    except socket.timeout:
        res["reason"] = "超时"
    except Exception as e:
        res["reason"] = type(e).__name__
    return res


# ---------- 候选源解析 ----------

def parse_m3u(path):
    out = []
    try:
        lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
    except Exception:
        return out
    name = group = None
    for l in lines:
        s = l.strip()
        if s.startswith("#EXTINF"):
            # 名称在最后一个逗号之后
            name = s.split(",")[-1].strip() if "," in s else ""
            g = re.search(r'group-title="([^"]*)"', s)
            group = g.group(1) if g else ""
        elif s.startswith("http") and name:
            out.append((name, group, s))
            name = None
    return out


def parse_txt(path):
    """'名称,地址' 或 '#genre#' 分组格式"""
    out = []
    try:
        lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
    except Exception:
        return out
    group = ""
    for l in lines:
        s = l.strip()
        if not s or s.startswith("#EXTM3U"):
            continue
        if s.startswith("#") and s.endswith("#genre#"):
            group = s.strip("#").replace("genre", "").strip(",")
            continue
        if "," in s and "http" in s:
            name, _, url = s.partition(",")
            url = url.strip()
            if url.startswith("http"):
                out.append((name.strip(), group, url))
    return out


def collect(paths):
    items = []
    seen = set()
    for p in paths:
        if not os.path.exists(p):
            continue
        data = parse_m3u(p) if p.lower().endswith((".m3u", ".m3u8")) else parse_txt(p)
        for name, group, url in data:
            if url in seen:
                continue
            seen.add(url)
            items.append((name, group, url))
    return items


def main():
    targets = sys.argv[1:]
    if not targets:
        targets = [
            os.path.join(ROOT, "_r", "yusanpiao.txt"),
            os.path.join(ROOT, "_r", "qist_sn.txt"),
            os.path.join(ROOT, "_r", "niuhu.txt"),
            os.path.join(ROOT, "_r", "iptvorg_cn.txt"),
            os.path.join(ROOT, "lives", "pool.m3u"),
        ]
    items = collect(targets)
    print(f"候选流总数: {len(items)}")

    # 只测央视/卫视/本地台，过滤购物、测试、点播轮播等
    SKIP = ("购物", "测试", "彩条", "导视", "九宫格", "春晚2023", "广告", "直播中国")
    KEEP_KW = ("CCTV", "央视", "卫视", "CETV", "CGTN", "中国教育", "IPTV-", "CHC", "爱上",
               "商洛", "陕西", "西安", "咸阳", "渭南", "宝鸡", "汉中", "安康", "延安",
               "榆林", "铜川", "杨凌")
    filtered = []
    for n, g, u in items:
        up = n.upper()
        if any(k in n for k in SKIP):
            continue
        if any(k.upper() in up for k in KEEP_KW) or any(k in g for k in ("央视", "卫视", "陕西", "地方")):
            filtered.append((n, g, u))
    print(f"核心频道候选: {len(filtered)}")

    os.makedirs(OUT_DIR, exist_ok=True)
    results = []
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=48) as ex:
        futs = {ex.submit(test_one, it): it for it in filtered}
        for f in as_completed(futs):
            done += 1
            r = f.result()
            results.append(r)
            if done % 200 == 0:
                ok = sum(1 for x in results if x["ok"])
                print(f"  进度 {done}/{len(filtered)}  可播 {ok}  用时 {time.time()-t0:.0f}s", flush=True)

    ok = [r for r in results if r["ok"]]
    ok.sort(key=lambda x: -x["kbps"])
    json.dump(results, open(os.path.join(OUT_DIR, "speeds.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\n===== 测速完成 =====")
    print(f"总测 {len(results)} 条 | 可播 {len(ok)} 条 | 用时 {time.time()-t0:.0f}s")
    from collections import Counter
    lv = Counter(r["level"] for r in ok)
    for k, v in lv.most_common():
        print(f"  {k}: {v} 条")
    print("\n最快 15 条:")
    for r in ok[:15]:
        print(f"  {r['kbps']:7.0f}kbps  ttfb{r['ttfb_ms']:5d}ms  {r['name'][:22]:<24} {r['url'][:60]}")
    print("\n最慢 8 条（可播但会卡）:")
    for r in ok[-8:]:
        print(f"  {r['kbps']:7.0f}kbps  {r['name'][:22]}")


if __name__ == "__main__":
    main()
