#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直播流可用性检测 + 死链过滤。
对每个 #EXTINF 后的 URL 发 Range 请求，判定 200/206 = 可用。
输出可用性报告，并可写出过滤后的 m3u。
并发用线程池加速。
"""
import re, os, sys, ssl, json, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
LIVES = os.path.join(HERE, "lives")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Linux; Android 5) AppleWebKit/537.36 Chrome/144.0 Mobile Safari/537.36"


def probe(url, timeout=10):
    """返回 (可用?, 状态)"""
    if url.startswith("rtp://"):
        return None, "RTP"          # 组播，无法用 HTTP 探测
    try:
        u = urllib.parse.quote(url, safe=":/?&=%+#")
        req = urllib.request.Request(u, headers={"User-Agent": UA, "Range": "bytes=0-1024"})
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            code = r.getcode()
            ct = r.headers.get("Content-Type", "")
        ok = code in (200, 206) and ("mpegurl" in ct or "octet-stream" in ct or len(ct) == 0)
        return ok, f"{code}"
    except urllib.error.HTTPError as e:
        return False, str(e.code)
    except Exception as e:
        return False, type(e).__name__


def parse_m3u(path):
    """返回 [(extinf_line, url_line), ...]"""
    lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
    items = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF"):
            j = i + 1
            while j < len(lines) and lines[j].startswith("#EXT"):
                j += 1
            if j < len(lines):
                items.append((lines[i], lines[j], lines[i:j+1]))
                i = j + 1
                continue
        i += 1
    return items


def check_file(path, workers=16):
    items = parse_m3u(path)
    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(probe, url): (ext, url, blk) for ext, url, blk in items}
        for fut in as_completed(futs):
            ext, url, blk = futs[fut]
            ok, st = fut.result()
            results.append({"ext": ext, "url": url, "ok": ok, "status": st})
    return results


def main():
    targets = sys.argv[1:] or [
        "lives/cn_clean.m3u", "lives/guovin_clean.m3u", "lives/mzky_clean.m3u",
        "lives/yuechan_clean.m3u", "lives/yang_clean.m3u", "lives/kimentanm_clean.m3u",
    ]
    report = {}
    for t in targets:
        if not os.path.exists(t):
            continue
        res = check_file(t)
        total = len(res)
        http = [r for r in res if r["status"] != "RTP"]
        okc = sum(1 for r in http if r["ok"])
        rtp = total - len(http)
        pct = (okc / len(http) * 100) if http else 0
        report[t] = {"total": total, "http": len(http), "ok": okc, "rtp": rtp, "pct": round(pct, 1)}
        print(f"{t}: 总{total} HTTP{len(http)} 可用{okc}({pct:.1f}%) RTP{rtp}")

        # 写可用性明细
        det = os.path.join(HERE, t.replace("lives/", "probe_").replace(".m3u", ".json"))
        with open(det, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False)
    with open(os.path.join(HERE, "probe_summary.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
