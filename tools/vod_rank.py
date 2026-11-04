# -*- coding: utf-8 -*-
"""点播源「速度优先」全网优选：两阶段多轮 P75 采样 + 内容有效性校验。

背景：
  项目历史上反复踩过「单次/中位数测速不可信」的坑（同一站 360 在
  7290↔620 kbps 之间跳、量子某轮 3468ms）。TVBox 搜索是并发请求，
  决定体验的是**尾部延迟**，因此判据固定为多轮 P75，不用单次/中位数。

两阶段：
  1) 粗筛：候选池全部站各测 3 轮，按 P75 取前 KEEP 个进入精测
  2) 精测：入选站各测 9 轮，得到 P50/P75/worst/成功率；再做一次
     `?ac=list` 内容校验，剔除「响应快但是空壳/报错」的站

用法：
  python tools/vod_rank.py                 # 默认 3+9 轮
  python tools/vod_rank.py --coarse 3 --rounds 9 --keep 18
  python tools/vod_rank.py --list-only    # 只看候选池，不测速

输出：_probe/vod_rank_p75.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import io
import json
import os
import statistics
import sys
import time
import urllib.request
import ssl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import tv_speedtest as ts  # noqa: E402  复用同一套首包测速口径

OUT = os.path.join(ROOT, "_probe", "vod_rank_p75.json")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def load_candidates() -> list[dict]:
    """合并历史候选池 + 当前在用站，按 api 去重。"""
    pool, seen = [], set()

    def add(name, api):
        if not api or not api.startswith("http"):
            return
        key = api.rstrip("/")
        if key in seen:
            return
        seen.add(key)
        pool.append({"name": name or key.split("/")[2], "api": key})

    for fn in ("vod_stable.json", "vod_final.json"):
        p = os.path.join(ROOT, "_probe", fn)
        if not os.path.exists(p):
            continue
        try:
            for x in json.load(io.open(p, encoding="utf-8")):
                add(x.get("name"), x.get("api"))
        except Exception as e:
            print(f"! 读取 {fn} 失败: {e}")
    cfg = os.path.join(ROOT, "tvbox_clean.json")
    if os.path.exists(cfg):
        for s in json.load(io.open(cfg, encoding="utf-8")).get("sites", []):
            add(s.get("name"), s.get("api"))
    return pool


def one_probe(url: str) -> float | None:
    try:
        ms, _code = ts.probe(url)
        return ms
    except Exception:
        return None


def measure_batch(sites: list[dict], rounds: int, workers: int = 24) -> dict:
    """对每站做 rounds 次首包测速，返回 {api: [ms,...]}。"""
    urls = {s["api"]: s["api"].rstrip("/") + "/?ac=videolist&pg=1" for s in sites}
    samples = {a: [] for a in urls}
    jobs = [(a, u, r) for a, u in urls.items() for r in range(rounds)]
    ex = cf.ThreadPoolExecutor(max_workers=workers)
    fut = {ex.submit(one_probe, u): (a, u) for a, u, _ in jobs}
    done = 0
    try:
        for f in cf.as_completed(fut, timeout=len(jobs) * 6 / workers + 300):
            a, _u = fut[f]
            try:
                ms = f.result()
            except Exception:
                ms = None
            if ms is not None:
                samples[a].append(round(ms, 1))
            done += 1
            if done % 100 == 0:
                print(f"    {done}/{len(jobs)}", flush=True)
    except cf.TimeoutError:
        print("! 测速整体超时，用已收样本出报告", flush=True)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return samples


def summarize(sites: list[dict], samples: dict) -> list[dict]:
    rows = []
    for s in sites:
        v = sorted(samples.get(s["api"], []))
        n = len(v)
        p75 = v[min(n - 1, int(n * 0.75))] if n else None
        rows.append({
            "name": s["name"], "api": s["api"],
            "ok": n, "p50_ms": round(statistics.median(v), 1) if n else None,
            "p75_ms": round(p75, 1) if p75 is not None else None,
            "worst_ms": round(v[-1], 1) if n else None,
            "samples": v,
        })
    return sorted(rows, key=lambda x: x["p75_ms"] if x["p75_ms"] is not None else 9e9)


def content_check(api: str, timeout: int = 8) -> dict:
    """校验返回的是有效采集 JSON，且确实有分类/影片数据。"""
    u = api.rstrip("/") + "/?ac=list"
    out = {"ok": False, "cats": 0, "bytes": 0, "err": ""}
    try:
        r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(r, timeout=timeout, context=CTX) as f:
            b = f.read(200000)
            out["bytes"] = len(b)
        d = json.loads(b.decode("utf-8", errors="replace"))
        lis = d.get("list") or d.get("class") or []
        out["cats"] = len(lis) if isinstance(lis, list) else 0
        out["ok"] = bool(isinstance(d, dict) and (d.get("list") or d.get("class")))
    except Exception as e:
        out["err"] = f"{type(e).__name__}:{str(e)[:80]}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coarse", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=9)
    ap.add_argument("--keep", type=int, default=18)
    ap.add_argument("--list-only", action="store_true")
    a = ap.parse_args()

    pool = load_candidates()
    print(f"候选池：{len(pool)} 个去重站点", flush=True)
    if a.list_only:
        for s in pool:
            print("  ", s["name"], s["api"])
        return 0

    print(f"\n[阶段1] 粗筛 {a.coarse} 轮 × {len(pool)} 站 ...", flush=True)
    c = measure_batch(pool, a.coarse)
    coarse = summarize(pool, c)
    cur = {s["api"].rstrip("/") for s in
           json.load(io.open(os.path.join(ROOT, "tvbox_clean.json"), encoding="utf-8"))["sites"]}
    chosen = [s for r in coarse[:a.keep] for s in pool if s["api"] == r["api"]]
    for s in pool:
        if s["api"] in cur and s not in chosen:
            chosen.append(s)
    print(f"粗筛 P75 前 {len(chosen)} 名（含当前在用站）:", flush=True)
    for r in coarse[:12]:
        print(f"   {r['name']:<8} P75={r['p75_ms']:>8} ms 成功={r['ok']}/{a.coarse}", flush=True)

    print(f"\n[阶段2] 精测 {a.rounds} 轮 × {len(chosen)} 站 ...", flush=True)
    f = measure_batch(chosen, a.rounds)
    fine = summarize(chosen, f)
    print("\n[内容校验] ?ac=list ...", flush=True)
    for r in fine:
        r["content"] = content_check(r["api"])
        r["usable"] = bool(r["ok"] >= max(3, int(a.rounds * 0.6))
                           and r["content"]["ok"])
        print(f"   {r['name']:<8} P75={str(r['p75_ms']):>8} 最差={str(r['worst_ms']):>8} "
              f"成功={r['ok']}/{a.rounds} 分类={r['content']['cats']:>3} 可用={r['usable']}", flush=True)

    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "criterion": f"{a.rounds}轮P75 + ?ac=list 内容校验",
        "pool_size": len(pool), "coarse_rounds": a.coarse, "fine_rounds": a.rounds,
        "fine": fine,
        "recommended": [r["name"] for r in fine if r["usable"]][:6],
        "quick_search": [r["name"] for r in fine if r["usable"]][:2],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"\n推荐点播组合: {payload['recommended']}")
    print(f"quickSearch: {payload['quick_search']}")
    print(f"结果 -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
