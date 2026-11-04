#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""电视端提速基线测速（可复用）— 只服务于「家里电视最快」这个目标。

用法：python tools/tv_speedtest.py [轮数，默认3]

产出（_probe/ 下）：
  tv_live_ttfb.json   每条直播线路 3 轮首包耗时中位数 / 成功率 / HTTP 状态
  tv_vod_ttfb.json    每个点播 API 3 轮响应耗时中位数
  tv_baseline.json    汇总：每个频道「当前第一条」耗时 vs 「最快可选」耗时 + 可提升空间

设计约束：
  · 只测量，不修改任何线上文件；后续 optimize_tv.py 消费这里的产出。
  · 每条线路只读前 256 字节（Range），不下整段流；本机内网源 302 跳转会跟随，
    所以测到的就是真实起播耗时。
  · 不用 `with ThreadPoolExecutor`（退出时 shutdown(wait=True) 会在 DNS 挂起时卡死），
    改用 as_completed(timeout=...) + os._exit(0) 兜底。
"""
import concurrent.futures as cf
import io
import json
import os
import re
import socket
import ssl
import statistics
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "_probe")
LIVE = os.path.join(ROOT, "lives", "main.m3u")
CFG = os.path.join(ROOT, "tvbox_clean.json")

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
TIMEOUT = 6
WORKERS = 24
socket.setdefaulttimeout(TIMEOUT)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(urllib.request.HTTPSHandler(context=CTX))


def probe(url):
    """返回 (耗时毫秒 或 None, HTTP状态 或 异常名)"""
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(
            url,
            headers={"Range": "bytes=0-256", "User-Agent": "Mozilla/5.0 TVBox",
                     "Connection": "close"},
        )
        with OPENER.open(req, timeout=TIMEOUT) as resp:
            code = resp.status
            resp.read(256)
        return round((time.perf_counter() - t0) * 1000, 1), code
    except Exception as e:
        return None, type(e).__name__


def measure(urls, tag):
    """多轮采样，返回 {url: {ttfb_ms, ok, rounds}}"""
    result = {u: [] for u in urls}
    for rnd in range(1, ROUNDS + 1):
        fut = {}
        ex = cf.ThreadPoolExecutor(max_workers=WORKERS)
        try:
            for u in urls:
                fut[ex.submit(probe, u)] = u
            done = 0
            for f in cf.as_completed(fut, timeout=300):
                u = fut[f]
                try:
                    ms, code = f.result()
                except Exception:
                    ms, code = None, "worker_error"
                result[u].append((ms, code))
                done += 1
                if done % 50 == 0:
                    print(f"  [{tag}] 第{rnd}/{ROUNDS}轮 {done}/{len(urls)}", flush=True)
        except cf.TimeoutError:
            print(f"  ! [{tag}] 第{rnd}轮超时收尾", flush=True)
        finally:
            ex.shutdown(wait=False, cancel_futures=True)
        # 每轮都落盘，中途中断也不丢数据
        dump = {}
        for u, samples in result.items():
            good = [m for m, c in samples if m is not None]
            dump[u] = {
                "ttfb_ms": round(statistics.median(good), 1) if good else None,
                "ok": len(good), "rounds": len(samples),
                "last_code": samples[-1][1] if samples else None,
            }
        with open(os.path.join(PROBE, f"tv_{tag}_ttfb.json"), "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=1)
        print(f"  [{tag}] 第{rnd}轮完成", flush=True)
    return dump


def parse_m3u():
    lines = io.open(LIVE, encoding="utf-8", errors="replace").read().splitlines()
    out = []
    for i, l in enumerate(lines):
        if not l.startswith("#EXTINF"):
            continue
        m = re.search(r'tvg-name="([^"]+)"', l)
        name = m.group(1) if m else l.rsplit(",", 1)[-1].strip()
        url = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if url.startswith("http"):
            out.append({"name": name, "url": url})
    return out


def main():
    os.makedirs(PROBE, exist_ok=True)
    entries = parse_m3u()
    urls = list(dict.fromkeys(e["url"] for e in entries))
    print(f"[1] 直播线路 {len(urls)} 条 / {len(set(e['name'] for e in entries))} 个频道，"
          f"{ROUNDS} 轮 × {WORKERS} 并发", flush=True)
    live = measure(urls, "live")

    cfg = json.load(io.open(CFG, encoding="utf-8"))
    apis = [s["api"].rstrip("/") + "/?ac=videolist&pg=1" for s in cfg["sites"]]
    print(f"[2] 点播 API {len(apis)} 个，{ROUNDS} 轮", flush=True)
    vod = measure(apis, "vod")

    # 汇总：每个频道当前第一条 vs 最快的一条
    by_ch = {}
    for e in entries:
        by_ch.setdefault(e["name"], []).append(e["url"])
    rows, gains = [], []
    for name, ch_urls in by_ch.items():
        cur = live.get(ch_urls[0], {}).get("ttfb_ms")
        cand = [(live.get(u, {}).get("ttfb_ms"), u) for u in ch_urls
                if live.get(u, {}).get("ttfb_ms") is not None]
        best = min(cand)[0] if cand else None
        rows.append({"channel": name, "lines": len(ch_urls),
                     "current_first_ms": cur, "fastest_ms": best,
                     "gain_ms": round(cur - best, 1) if cur is not None and best is not None else None})
        if cur is not None and best is not None and cur > best:
            gains.append(cur - best)

    all_ok = [v["ttfb_ms"] for v in live.values() if v["ttfb_ms"] is not None]
    cur_ok = [r["current_first_ms"] for r in rows if r["current_first_ms"] is not None]
    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rounds": ROUNDS,
        "channels": len(rows), "lines": len(urls),
        "live_reachable": len(all_ok),
        "live_median_ms": round(statistics.median(all_ok), 1) if all_ok else None,
        "current_first_median_ms": round(statistics.median(cur_ok), 1) if cur_ok else None,
        "current_first_p90_ms": round(sorted(cur_ok)[int(len(cur_ok) * .9)], 1) if cur_ok else None,
        "channels_with_faster_option": len(gains),
        "potential_gain_median_ms": round(statistics.median(gains), 1) if gains else 0,
        "potential_gain_total_ms": round(sum(gains), 1),
        "vod": {k: {"ttfb_ms": v["ttfb_ms"], "ok": v["ok"]} for k, v in vod.items()},
        "per_channel": rows,
    }
    with open(os.path.join(PROBE, "tv_baseline.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    print("\n=== 基线 ===", flush=True)
    print(f"频道 {report['channels']} / 线路 {report['lines']} / 可达 {report['live_reachable']}")
    print(f"全部线路首包中位数 {report['live_median_ms']}ms")
    print(f"当前每频道第一条中位数 {report['current_first_median_ms']}ms，"
          f"P90 {report['current_first_p90_ms']}ms")
    print(f"有更快线路可选的频道 {report['channels_with_faster_option']} 个，"
          f"可省中位数 {report['potential_gain_median_ms']}ms / 累计 {report['potential_gain_total_ms']}ms")
    print("点播 API 响应:", {k.split('/')[2]: v['ttfb_ms'] for k, v in report['vod'].items()}, flush=True)
    os._exit(0)


if __name__ == "__main__":
    main()
