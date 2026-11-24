# -*- coding: utf-8 -*-
"""多影片 × 多分片复测：判定「播放快不快」不能只抽一条片子。

背景（v3.3）：
  tools/vod_e2e.py 的第 3 阶段每站只取首页第一条影片的第一个分片。
  分片速度高度依赖具体片源/CDN/时段，v3.1 就因为单次测速把 360 在
  7290↔620kbps 之间来回误判过。所以这里对每站取多部影片、多轮 detail
  请求，用中位数 + P75 定案，并与 _probe/vod_stable.json 的历史多轮数据交叉。

测三件事（都是用户真实等待的环节）：
  1) detail  ?ac=videolist&ids=<vod_id>   点进详情页的 API 完整响应
  2) m3u8    播放列表首包
  3) 首片    第一个 ts 分片的首包 TTFB 与 256KB 下载速率 kbps

用法：python tools/vod_play_multi.py [--sites 10] [--films 6] [--workers 8]
输出：_probe/vod_play_multi.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import io
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "_probe")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "okhttp/3.15"
TIMEOUT = 8
socket.setdefaulttimeout(TIMEOUT)


def get(url: str, limit: int = 400000) -> tuple[bytes, float]:
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Encoding": "gzip",
                                               "Range": f"bytes=0-{limit - 1}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
        b = r.read(limit)
        if "gzip" in (r.headers.get("Content-Encoding") or "").lower():
            try:
                b = gzip.decompress(b)
            except Exception:
                pass
    return b, round((time.perf_counter() - t0) * 1000, 1)


def first_m3u8(txt: str) -> str:
    m = re.search(r"https?://[^\s#$\"'<>]+?\.m3u8[^\s#$\"'<>]*", str(txt or ""))
    return m.group(0) if m else ""


def seg_of(mu: str) -> tuple[str, float]:
    """返回 (首个分片绝对 URL, m3u8 完整响应 ms)。支持一级 master 列表。"""
    b, ms = get(mu, 200000)
    body = b.decode("utf-8", errors="replace")
    for _ in range(2):
        lines = [x.strip() for x in body.splitlines() if x.strip() and not x.startswith("#")]
        if not lines:
            return "", ms
        nxt = urllib.parse.urljoin(mu, lines[0])
        if ".m3u8" in nxt:
            mu = nxt
            b2, ms2 = get(mu, 200000)
            body = b2.decode("utf-8", errors="replace")
            ms += ms2
            continue
        return nxt, ms
    return "", ms


def probe_seg(seg: str) -> dict:
    out = {"ok": False, "ttfb_ms": None, "kbps": None, "err": ""}
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(seg, headers={"User-Agent": UA,
                                                   "Range": "bytes=0-262143"})
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
            head = r.read(1)
            out["ttfb_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            chunk = head + r.read(262143)
            el = time.perf_counter() - t0
        out["kbps"] = round(len(chunk) * 8 / el / 1000, 1) if el > 0 else None
        out["ok"] = True
    except Exception as e:
        out["err"] = type(e).__name__
    return out


def films_of(api: str, n: int) -> list[dict]:
    try:
        b, _ = get(api + "/?ac=videolist&pg=1", 3000000)
        d = json.loads(b.decode("utf-8", errors="replace"))
        return [x for x in (d.get("list") or [])[:n] if x.get("vod_play_url")]
    except Exception:
        return []


def one_film(api: str, item: dict) -> dict:
    r = {"vod_id": item.get("vod_id"), "name": item.get("vod_name"),
         "m3u8_ms": None, "seg_ttfb_ms": None, "kbps": None, "err": ""}
    try:
        mu = first_m3u8(item.get("vod_play_url"))
        if not mu:
            r["err"] = "no_m3u8"
            return r
        seg, ms = seg_of(mu)
        r["m3u8_ms"] = ms
        if not seg:
            r["err"] = "no_seg"
            return r
        p = probe_seg(seg)
        r.update({"seg_ttfb_ms": p["ttfb_ms"], "kbps": p["kbps"],
                  "err": p["err"], "ok": p["ok"]})
    except Exception as e:
        r["err"] = type(e).__name__
    return r


def detail_probe(api: str, vid) -> float | None:
    t0 = time.perf_counter()
    try:
        b, _ = get(f"{api}/?ac=videolist&ids={vid}", 2000000)
        json.loads(b.decode("utf-8", errors="replace"))
        return round((time.perf_counter() - t0) * 1000, 1)
    except Exception:
        return None


def pct(v, q):
    v = sorted(x for x in v if x is not None)
    return round(v[min(len(v) - 1, int(len(v) * q))], 1) if v else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", type=int, default=10)
    ap.add_argument("--films", type=int, default=6)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    fine = json.load(io.open(os.path.join(PROBE, "vod_e2e_fine.json"), encoding="utf-8"))
    in_use = set(fine.get("in_use", []))
    rows = [r for r in fine["fine"] if r.get("usable")][:a.sites]
    for r in fine["fine"]:
        if r["api"] in in_use and r not in rows:
            rows.append(r)

    hist = {}
    for x in json.load(io.open(os.path.join(PROBE, "vod_stable.json"), encoding="utf-8")):
        hist[(x.get("api") or "").replace("http://", "https://").rstrip("/")] = x.get("vod_kbps") or 0

    print(f"复测 {len(rows)} 站 × 每站 {a.films} 部影片 + 3 次详情 API ...", flush=True)
    results = []
    for r in rows:
        api = r["api"]
        items = films_of(api, a.films)
        jobs = [(api, it) for it in items]
        ex = cf.ThreadPoolExecutor(max_workers=a.workers)
        fut = [ex.submit(one_film, x, y) for x, y in jobs]
        films = []
        try:
            for f in cf.as_completed(fut, timeout=180):
                try:
                    films.append(f.result())
                except Exception as e:
                    films.append({"err": type(e).__name__})
        except cf.TimeoutError:
            print("  ! 影片探测超时", flush=True)
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

        vids = [it.get("vod_id") for it in items[:3] if it.get("vod_id")]
        dex = cf.ThreadPoolExecutor(max_workers=3)
        dfut = [dex.submit(detail_probe, api, v) for v in vids]
        details = []
        try:
            for f in cf.as_completed(dfut, timeout=60):
                try:
                    v = f.result()
                    if v is not None:
                        details.append(v)
                except Exception:
                    pass
        except cf.TimeoutError:
            pass
        finally:
            dex.shutdown(wait=False, cancel_futures=True)

        kbps = [x["kbps"] for x in films if x.get("kbps")]
        ttfb = [x["seg_ttfb_ms"] for x in films if x.get("seg_ttfb_ms")]
        out = {
            "name": r["name"], "api": api, "family": r["family"],
            "search_p75": r["search"]["p75"], "home_p75": r["home"]["p75"],
            "films": len(films), "films_ok": len(kbps),
            "kbps_median": pct(kbps, .5), "kbps_p75": pct(kbps, .75),
            "seg_ttfb_p75": pct(ttfb, .75),
            "detail_p75": pct(details, .75), "detail_ok": len(details),
            "hist_kbps": hist.get(api, 0),
            "samples": films,
        }
        results.append(out)
        print(f"  {r['name']:<10} 分片中位={str(out['kbps_median']):>8}kbps "
              f"P75={str(out['kbps_p75']):>8} 首片P75={str(out['seg_ttfb_p75']):>7}ms "
              f"详情P75={str(out['detail_p75']):>7}ms 成功{out['films_ok']}/{out['films']} "
              f"历史={out['hist_kbps']}", flush=True)

    p = os.path.join(PROBE, "vod_play_multi.json")
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "criterion": "每站多影片首片 kbps 中位/P75 + detail API P75，与历史多轮数据交叉",
                   "rows": results}, f, ensure_ascii=False, indent=1)
    print(f"-> {p}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
