# -*- coding: utf-8 -*-
"""v3.3 点播「端到端速度」测速 —— 速度第一，只认完整响应耗时。

为什么重写口径（v3.2 的盲区）：
  · tools/tv_speedtest.probe() 只读 256 字节，测的是 **首包 TTFB**。
    但 TVBox 必须等整份 JSON 下完、解析完才渲染首页/搜索结果。
    某站首包 600ms、body 1.2MB 要拖 3 秒，体感就是 3 秒，不是 0.6 秒。
  · 历史测速只打 `?ac=videolist&pg=1`（首页），没打 `wd=`（搜索）。
    搜索走全文检索，往往比首页慢一个量级，而这是用户最常做的操作。
  · 分类 `?ac=list` 决定首屏标签出现的时间。

三个真实端点（全部强制 https，与 build_config.force_https 同口径）：
  list   ?ac=list                       分类/首屏标签
  home   ?ac=videolist&pg=1             首页列表
  search ?ac=videolist&pg=1&wd=<片名>   搜索（体感权重最高）

两阶段 + 播放链路：
  1) 粗筛：全候选池 × 3 端点 × --coarse 轮，按综合速度取前 N
  2) 精测：入选 + 现用 5 站（同场次 A/B）× --rounds 轮，出 P50/P75/P90/worst
  3) 播放链路：从返回内容里取真实 m3u8，测首片首包与 kbps
     ——「API 快 ≠ 播放快」是 v3.2 用血换来的教训，必须一起验。

判据（速度第一，但仍拒绝单次/中位数定案）：
  score = .45*search_p75 + .25*home_p75 + .15*list_p75 + .15*search_p90
  门槛：成功率 >= 80%、list/home 均返回有效影片、播放分片达标。

用法：
  python tools/vod_e2e.py                       # 默认 3 轮粗筛 + 12 轮精测 + 播放链路
  python tools/vod_e2e.py --coarse 2 --rounds 6 --skip-play
  python tools/vod_e2e.py --list-only          # 只打印候选池
输出：_probe/vod_e2e_{pool,coarse,fine,play}.json
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
import statistics
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
UA = "okhttp/3.15"          # 与 TVBox 客户端一致
TIMEOUT = 8
socket.setdefaulttimeout(TIMEOUT)

SEARCH_WORD = "流浪地球"
ENDPOINTS = {
    "list": "?ac=list",
    "home": "?ac=videolist&pg=1",
    "search": "?ac=videolist&pg=1&wd=" + urllib.parse.quote(SEARCH_WORD),
}

# v3.3 新挖的候选：同内容备用域名（换域名 = 零内容损失的纯提速）+
# 公开订阅里仍在维护的采集接口。成人内容站一律不收（家用电视必须干净）。
EXTRA = [
    ("量子备", "https://cj.lzcaiji.com/api.php/provide/vod"),
    ("非凡采集", "https://api.ffzyapi.com/api.php/provide/vod"),
    ("金鹰点播", "https://jinyingzy.com/api.php/provide/vod"),
    ("金鹰云", "https://jyzyapi.com/provide/vod/from/jinyingyun/at/json"),
    ("速播新", "https://subocaiji.com/api.php/provide/vod"),
    ("闪电备", "https://xsd.sdzyapi.com/api.php/provide/vod"),
    ("茅台", "https://caiji.maotaizy.cc/api.php/provide/vod"),
    ("魔都", "https://www.mdzyapi.com/api.php/provide/vod"),
    ("鸭鸭", "https://cj.yayazy.net/api.php/provide/vod"),
    ("黑木耳", "https://json.heimuer.xyz/api.php/provide/vod"),
    ("黑木耳2", "https://json02.heimuer.xyz/api.php/provide/vod"),
    ("大地", "https://dadiapi.com/api.php/provide/vod"),
    ("优质全", "https://api.yzzy-api.com/inc/ldg_api_all.php/provide/vod"),
    ("神马云", "https://api.1080zyku.com/inc/apijson.php/"),
    ("爱奇艺", "https://iqiyizyapi.com/api.php/provide/vod"),
    ("豆瓣5", "https://caiji.dbzy5.com/api.php/provide/vod"),
    ("快车", "https://caiji.kuaichezy.org/api.php/provide/vod"),
    ("森林备", "https://beiyong.slapibf.com/api.php/provide/vod"),
    # 同族域名猜测：不通会被测速自然淘汰，成本很低但可能捡到就近 CDN
    ("非凡5www", "https://www.ffzy5.tv/api.php/provide/vod"),
    ("量子www", "https://www.lziapi.com/api.php/provide/vod"),
    ("量子1备", "https://cj.lzizy1.com/api.php/provide/vod"),
    ("天堂主域", "https://dyttzyapi.com/api.php/provide/vod"),
    ("天堂采集", "https://cj.dyttzyapi.com/api.php/provide/vod"),
    ("360新", "https://360zy.com/api.php/provide/vod"),
    ("360www", "https://www.360zyzz.com/api.php/provide/vod"),
    ("索尼www", "https://www.suoniapi.com/api.php/provide/vod"),
    ("虎牙json", "https://www.huyaapi.com/api.php/provide/vod/at/json"),
    ("非凡1https", "https://ffzy1.tv/api.php/provide/vod"),
]


def https(api: str) -> str:
    return re.sub(r"^http://", "https://", (api or "").strip())


def norm(api: str) -> str:
    return https(api).rstrip("/")


def family(name: str, api: str) -> str:
    """同内容家族：换域名属于同一家族，最终每家只留最快的一个。"""
    n = (name or "").strip()
    for key, fam in (
        ("非凡", "非凡"), ("量子", "量子"), ("索尼", "索尼"),
        ("360", "360"), ("天堂", "天堂"), ("虎牙", "虎牙"),
        ("金鹰", "金鹰"), ("速播", "速播"), ("闪电", "闪电"),
        ("森林", "森林"), ("豆瓣", "豆瓣"), ("黑木耳", "黑木耳"),
        ("魔都", "魔都"), ("快车", "快车"), ("红牛", "红牛"),
        ("光速", "光速"), ("暴风", "暴风"), ("极速", "极速"),
        ("电影", "天堂"), ("优质", "优质"), ("神马云", "优质"),
        ("最大", "最大"), ("樱花", "樱花"), ("天涯", "天涯"),
        ("旺旺", "旺旺"), ("金鹰", "金鹰"), ("百度", "百度"),
        ("火狐", "火狐"), ("iKun", "iKun"), ("无尽", "无尽"),
    ):
        if key in n:
            return fam
    return n or urllib.parse.urlparse(api).netloc


def load_pool() -> list[dict]:
    pool, seen = [], set()

    def add(name, api):
        api = norm(api)
        if not api.startswith("https://"):
            return
        if api in seen:
            return
        seen.add(api)
        pool.append({"name": name, "api": api, "family": family(name, api)})

    # 历史候选池（45 站，含各轮实测数据）
    for fn in ("vod_stable.json", "vod_final.json"):
        p = os.path.join(PROBE, fn)
        if os.path.exists(p):
            try:
                for x in json.load(io.open(p, encoding="utf-8")):
                    add(x.get("name"), x.get("api"))
            except Exception as e:
                print(f"! 读取 {fn}: {e}", flush=True)
    # 当前在用 5 站（必须进池做 A/B 基线）
    cfgp = os.path.join(ROOT, "tvbox_clean.json")
    for s in json.load(io.open(cfgp, encoding="utf-8")).get("sites", []):
        add(s.get("name"), s.get("api"))
    # v3.3 新挖
    for name, api in EXTRA:
        add(name, api)
    return pool


def fetch(url: str) -> dict:
    """一次完整请求：首包 + 整份 body 读完，模拟 TVBox 拿全 JSON 才渲染。"""
    out = {"ok": False, "full_ms": None, "ttfb_ms": None,
           "bytes": 0, "items": 0, "code": None, "err": ""}
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept-Encoding": "gzip",       # okhttp 默认会协商 gzip，贴近真实
            "Connection": "close",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
            out["code"] = r.status
            head = r.read(1)
            out["ttfb_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            raw = head + r.read()
            enc = (r.headers.get("Content-Encoding") or "").lower()
            if "gzip" in enc:
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            out["full_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            out["bytes"] = len(raw)
            try:
                d = json.loads(raw.decode("utf-8", errors="replace"))
                lis = d.get("list") if isinstance(d, dict) else d
                out["items"] = len(lis) if isinstance(lis, list) else 0
                out["ok"] = isinstance(d, (dict, list))
            except Exception:
                out["err"] = "bad_json"
    except Exception as e:
        out["err"] = type(e).__name__
    return out


def run_batch(sites: list[dict], rounds: int, workers: int, tag: str) -> dict:
    """返回 {api: {endpoint: [sample...]}}；不用 with-Executor，避免 DNS 挂起卡死。"""
    jobs = []
    for s in sites:
        for ep, suffix in ENDPOINTS.items():
            # 历史脚本固定用 api + "/?ac=..."，苹果CMS 两种形式都接受，保持同口径
            url = s["api"] + "/?" + suffix.lstrip("?")
            for _ in range(rounds):
                jobs.append((s["api"], ep, url))
    data = {s["api"]: {ep: [] for ep in ENDPOINTS} for s in sites}
    ex = cf.ThreadPoolExecutor(max_workers=workers)
    fut = {ex.submit(fetch, u): (a, e) for a, e, u in jobs}
    done = 0
    try:
        for f in cf.as_completed(fut, timeout=len(jobs) * TIMEOUT / workers + 240):
            a, e = fut[f]
            try:
                data[a][e].append(f.result())
            except Exception as exc:
                data[a][e].append({"ok": False, "err": type(exc).__name__})
            done += 1
            if done % 100 == 0:
                print(f"  [{tag}] {done}/{len(jobs)}", flush=True)
    except cf.TimeoutError:
        print(f"! [{tag}] 整体超时，用已收样本出报告", flush=True)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return data


def pct(vals: list[float], q: float):
    if not vals:
        return None
    v = sorted(vals)
    return round(v[min(len(v) - 1, int(len(v) * q))], 1)


def summarize(sites: list[dict], data: dict, rounds: int) -> list[dict]:
    rows = []
    for s in sites:
        r = {"name": s["name"], "api": s["api"], "family": s["family"]}
        ok_all = True
        for ep in ENDPOINTS:
            samples = data.get(s["api"], {}).get(ep, [])
            good = [x["full_ms"] for x in samples if x.get("ok") and x.get("full_ms")]
            ttfb = [x["ttfb_ms"] for x in samples if x.get("ok") and x.get("ttfb_ms")]
            r[ep] = {
                "ok": len(good), "req": len(samples),
                "p50": pct(good, .5), "p75": pct(good, .75),
                "p90": pct(good, .9), "worst": round(max(good), 1) if good else None,
                "ttfb_p50": pct(ttfb, .5),
                "bytes": max((x.get("bytes") or 0) for x in samples) if samples else 0,
                "items": max((x.get("items") or 0) for x in samples) if samples else 0,
            }
            if ep in ("list", "home") and r[ep]["items"] == 0:
                ok_all = False
        s75 = r["search"]["p75"]
        h75 = r["home"]["p75"]
        l75 = r["list"]["p75"]
        s90 = r["search"]["p90"]
        rate = min((r[e]["ok"] / max(1, r[e]["req"])) for e in ENDPOINTS)
        r["success_rate"] = round(rate, 3)
        r["usable"] = bool(ok_all and rate >= .8 and s75 and h75 and l75)
        r["score"] = round(.45 * (s75 or 99999) + .25 * (h75 or 99999)
                           + .15 * (l75 or 99999) + .15 * (s90 or 99999), 1) \
            if r["usable"] else 99999
        # 首包 vs 完整响应的差距：暴露「TTFB 看着快其实很慢」的站
        r["body_overhead_ms"] = round((r["home"]["p50"] or 0) - (r["home"]["ttfb_p50"] or 0), 1)
        rows.append(r)
    return sorted(rows, key=lambda x: x["score"])


def play_chain(api: str) -> dict:
    """取真实播放地址，测 m3u8 + 首片首包/速率。API 快不等于播放快。"""
    out = {"ok": False, "m3u8": "", "seg": "", "m3u8_ms": None,
           "seg_ttfb_ms": None, "kbps": None, "err": ""}
    try:
        req = urllib.request.Request(api + "/?ac=videolist&pg=1",
                                     headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
            raw = r.read()
            if "gzip" in (r.headers.get("Content-Encoding") or "").lower():
                raw = gzip.decompress(raw)
        j = json.loads(raw.decode("utf-8", errors="replace"))
        items = j.get("list") or []
        mu = ""
        for it in items[:8]:
            txt = str(it.get("vod_play_url") or "")
            m = re.search(r"https?://[^\s#$\"'<>]+?\.m3u8[^\s#$\"'<>]*", txt)
            if m:
                mu = m.group(0)
                break
        if not mu:
            out["err"] = "no_m3u8"
            return out
        out["m3u8"] = mu
        t0 = time.perf_counter()
        rq = urllib.request.Request(mu, headers={"User-Agent": UA, "Range": "bytes=0-8192"})
        with urllib.request.urlopen(rq, timeout=TIMEOUT, context=CTX) as r:
            body = r.read(200000).decode("utf-8", errors="replace")
        out["m3u8_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        lines = [x.strip() for x in body.splitlines() if x.strip() and not x.startswith("#")]
        # 二级 master 列表再跟一层
        if lines and "#EXT-X-STREAM-INF" in body and ".m3u8" in lines[0]:
            mu2 = urllib.parse.urljoin(mu, lines[0])
            rq2 = urllib.request.Request(mu2, headers={"User-Agent": UA})
            with urllib.request.urlopen(rq2, timeout=TIMEOUT, context=CTX) as r:
                body = r.read(200000).decode("utf-8", errors="replace")
            mu = mu2
            lines = [x.strip() for x in body.splitlines() if x.strip() and not x.startswith("#")]
        if not lines:
            out["err"] = "no_segment"
            return out
        seg = urllib.parse.urljoin(mu, lines[0])
        out["seg"] = seg
        t1 = time.perf_counter()
        rs = urllib.request.Request(seg, headers={"User-Agent": UA, "Range": "bytes=0-262143"})
        with urllib.request.urlopen(rs, timeout=TIMEOUT, context=CTX) as r:
            head = r.read(1)
            first = (time.perf_counter() - t1) * 1000
            chunk = head + r.read(262143)
            elapsed = time.perf_counter() - t1
        out["seg_ttfb_ms"] = round(first, 1)
        out["kbps"] = round(len(chunk) * 8 / elapsed / 1000, 1) if elapsed > 0 else None
        out["ok"] = True
    except Exception as e:
        out["err"] = f"{type(e).__name__}:{str(e)[:60]}"
    return out


def dump(name: str, obj):
    os.makedirs(PROBE, exist_ok=True)
    p = os.path.join(PROBE, name)
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    print(f"  -> {p}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coarse", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--keep", type=int, default=16)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--skip-play", action="store_true")
    ap.add_argument("--list-only", action="store_true")
    a = ap.parse_args()

    pool = load_pool()
    print(f"候选池 {len(pool)} 站（强制 https，去重）", flush=True)
    dump("vod_e2e_pool.json", {"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                               "criterion": "完整响应 full_ms / 三端点 / 多轮 P75",
                               "endpoints": ENDPOINTS, "pool": pool})
    if a.list_only:
        for s in pool:
            print(f"  {s['family']:<6} {s['name']:<10} {s['api']}")
        return 0

    cur = {norm(s["api"]) for s in
           json.load(io.open(os.path.join(ROOT, "tvbox_clean.json"), encoding="utf-8"))["sites"]}

    print(f"\n[1/3] 粗筛 {a.coarse} 轮 × {len(pool)} 站 × 3 端点 ...", flush=True)
    c = run_batch(pool, a.coarse, a.workers, "coarse")
    coarse = summarize(pool, c, a.coarse)
    dump("vod_e2e_coarse.json", coarse)
    print("粗筛前 15：", flush=True)
    for r in coarse[:15]:
        print(f"  {r['name']:<10} 搜索P75={str(r['search']['p75']):>8} "
              f"首页P75={str(r['home']['p75']):>8} 成功={r['success_rate']:<5} "
              f"score={r['score']}", flush=True)

    chosen = [s for s in pool if s["api"] in
              {r["api"] for r in coarse[:a.keep] if r["usable"]}]
    for s in pool:
        if s["api"] in cur and s not in chosen:
            chosen.append(s)
    print(f"\n[2/3] 精测 {a.rounds} 轮 × {len(chosen)} 站（含现用 5 站同场次 A/B）...", flush=True)
    f = run_batch(chosen, a.rounds, a.workers, "fine")
    fine = summarize(chosen, f, a.rounds)
    print("\n精测排名（完整响应，P75）：", flush=True)
    for i, r in enumerate(fine, 1):
        print(f"  {i:>2}. {r['name']:<10} 搜索 {str(r['search']['p75']):>7} / "
              f"首页 {str(r['home']['p75']):>7} / 分类 {str(r['list']['p75']):>7} ms  "
              f"首包{r['home']['ttfb_p50']:>7} body+{r['body_overhead_ms']:>7}  "
              f"字节{r['home']['bytes']:>7} 成功{r['success_rate']:<5} "
              f"{'OK' if r['usable'] else '×'}", flush=True)

    if not a.skip_play:
        print(f"\n[3/3] 播放链路（前 12 站取真实 m3u8 首片）...", flush=True)
        plays = []
        for r in fine[:12]:
            p = play_chain(r["api"])
            p["name"], p["api"], p["family"] = r["name"], r["api"], r["family"]
            plays.append(p)
            print(f"  {r['name']:<10} m3u8={str(p['m3u8_ms']):>7}ms "
                  f"首片={str(p['seg_ttfb_ms']):>7}ms "
                  f"速率={str(p['kbps']):>8}kbps {p['err']}", flush=True)
        dump("vod_e2e_play.json", plays)

    dump("vod_e2e_fine.json", {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "criterion": "完整响应 full_ms；score=.45*搜索P75+.25*首页P75+.15*分类P75+.15*搜索P90",
        "coarse_rounds": a.coarse, "fine_rounds": a.rounds,
        "in_use": sorted(cur), "fine": fine,
    })
    print("\n完成。定稿依据：_probe/vod_e2e_fine.json + vod_e2e_play.json", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
