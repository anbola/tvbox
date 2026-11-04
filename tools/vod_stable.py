#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
点播站【稳定性】精选（2026-11-04 新增）

为什么要这个脚本：
  单次测速波动极大 —— 同一个站在陕西移动宽带上，昨天 360=7290kbps，
  今天只有 620kbps；电影天堂昨天 1862kbps 今天就断连；速播昨天没影、
  今天冒到 1902kbps。单次采样根本不足以判定「优质」。
  本脚本对同一批站连续测 N 轮（默认 3 轮），统计：
    · 成功率      —— 几轮能完整走通 分类→列表→详情→真实分片
    · 码率中位数  —— 各轮码率的中位数（抗单次尖峰/掉底）
    · 延迟        —— 首页列表 / 详情 的平均耗时
    · 片源量      —— 站里到底有多少部片
  综合成 score，只有「成功率达标 + 码率达标」的站才配进配置。

候选来源：
  1) tools/vod_probe.py 原有 35 站里「至少有一轮响应过」的；
  2) 2026-11-04 从 GitHub 公开配置（TVboxorg/TVbox、newwex、XPTV）
     提取的裸采集站 API（已去重、去掉中文域名/分享页型）。

输出 _probe/vod_stable.json —— 字段与 vod_final.json 兼容，
build_config.py 优先读它（更可信），没有才回退到旧数据。

用法：
  python tools/vod_stable.py            # 3 轮
  python tools/vod_stable.py --rounds 5
"""
import argparse
import json
import os
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vod_probe as vp  # 复用 check()：分类/列表/详情/真实分片测速

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_probe", "vod_stable.json")

# 原有候选里「两轮实测至少响应过一次」的站（纯死站不浪费轮次）
LEGACY = [
    ("量子", "http://cj.lziapi.com/api.php/provide/vod/"),
    ("非凡", "http://cj.ffzyapi.com/api.php/provide/vod/"),
    ("非凡5", "https://ffzy5.tv/api.php/provide/vod/"),
    ("360", "https://360zyzz.com/api.php/provide/vod/"),
    ("电影天堂", "http://caiji.dyttzyapi.com/api.php/provide/vod/"),
    ("速播", "https://subocj.com/api.php/provide/vod/"),
    ("光速", "https://api.guangsuapi.com/api.php/provide/vod/"),
    ("极速", "https://jszyapi.com/api.php/provide/vod/"),
    ("天涯", "https://tyyszyapi.com/api.php/provide/vod/"),
    ("金鹰", "https://jyzyapi.com/api.php/provide/vod/"),
    ("火狐", "https://hhzyapi.com/api.php/provide/vod/"),
    ("无尽", "https://api.wujinapi.me/api.php/provide/vod/"),
    ("闪电", "http://sdzyapi.com/api.php/provide/vod/"),
    ("百度", "https://api.apibdzy.com/api.php/provide/vod/"),
    ("最大", "https://api.zuidapi.com/api.php/provide/vod/"),
    ("豆瓣", "https://dbzy.tv/api.php/provide/vod/"),
    ("猫眼", "https://api.maoyanapi.top/api.php/provide/vod/"),
    ("森林", "https://slapibf.com/api.php/provide/vod/"),
    ("暴风", "https://bfzyapi.com/api.php/provide/vod/"),
]

# 从 GitHub 公开配置挖到的新线路（TVboxorg official.json / newwex.json / XPTV）
DISCOVERED = [
    ("索尼", "https://suoniapi.com/api.php/provide/vod/"),
    ("非凡1", "http://ffzy1.tv/api.php/provide/vod/"),
    ("量子1", "https://lzizy1.com/api.php/provide/vod/"),
    ("四九", "https://49zy1.com/api.php/provide/vod/"),
    ("奇虎", "https://caiji.qhzyapi.com/api.php/provide/vod/"),
    ("可可", "https://kekezy1.com/api.php/provide/vod/"),
    ("飞速", "https://www.feisuzyapi.com/api.php/provide/vod/"),
    ("360新", "https://360zy.com/api.php/provide/vod/"),
    ("虎牙", "https://www.huyaapi.com/api.php/provide/vod/from/hym3u8"),
]

CANDIDATES = LEGACY + DISCOVERED

# 陕西移动宽带下的达标线
MIN_KBPS = 1200.0        # 码率中位数下限（低于此值播放会转圈）
MIN_SUCCESS = 0.67       # 3 轮里至少 2 轮必须完整走通
MAX_SITES = 6            # 最终入选数量


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0.0


def run_round(round_no, total_rounds):
    print(f"\n===== 第 {round_no}/{total_rounds} 轮（共 {len(CANDIDATES)} 站）=====", flush=True)
    socket.setdefaulttimeout(20)
    ex = ThreadPoolExecutor(max_workers=10)
    futs = {ex.submit(vp.check, c): c[0] for c in CANDIDATES}
    got = {}
    try:
        for f in as_completed(futs, timeout=240):
            name = futs[f]
            try:
                got[name] = f.result()
            except Exception:
                pass
    except TimeoutError:
        print("  ⚠ 本轮超时，仅收录已完成结果", flush=True)
        for f in futs:
            if f.done():
                try:
                    got[futs[f]] = f.result()
                except Exception:
                    pass
    ex.shutdown(wait=False, cancel_futures=True)
    print(f"  本轮完成 {len(got)}/{len(CANDIDATES)}", flush=True)
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rounds = []
    for i in range(args.rounds):
        if i and args.rounds > 1:
            print("\n轮间冷却 5s（避开瞬时抖动）…", flush=True)
            time.sleep(5)
        rnd = run_round(i + 1, args.rounds)
        rounds.append(rnd)
        # 每轮立即落盘：即使后续汇总出错，也不至于多轮实测全部白跑
        json.dump(rnd, open(os.path.join(os.path.dirname(OUT), f"vod_round{i+1}.json"),
                           "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 汇总
    summary = []
    for name, api in CANDIDATES:
        recs = [rnd.get(name) for rnd in rounds]
        recs = [r for r in recs if r]
        ok = [r for r in recs if not r.get("err") and r.get("vod_kbps", 0) > 0]
        kb = median([r["vod_kbps"] for r in ok]) if ok else 0.0
        success = len(ok) / args.rounds if args.rounds else 0
        lms = median([r["list_ms"] for r in recs if r.get("list_ms")]) if recs else 0
        dms = median([r["detail_ms"] for r in recs if r.get("detail_ms")]) if recs else 0
        total = max((r.get("total") or 0) for r in recs) if recs else 0
        cats = max((r.get("cats") or 0) for r in recs) if recs else 0
        last = recs[-1] if recs else {}
        # 综合评分：码率 × 稳定性² × 片源规模因子 ÷ 延迟惩罚
        stock = min(1.0, total / 60000.0) if total else 0.2
        delay_penalty = 1.0 + (lms or 3000) / 4000.0
        score = kb * (success ** 2) * (0.6 + 0.4 * stock) / delay_penalty
        summary.append({
            "name": name, "api": api,
            "vod_kbps": round(kb, 1),
            "class_ms": last.get("class_ms"),
            "list_ms": int(lms), "detail_ms": int(dms),
            "ttfb": last.get("ttfb", 0), "total": total, "cats": cats,
            "kind": last.get("kind", ""),
            "err": "" if ok else (recs[-1].get("err") if recs else "无响应"),
            "success_rate": round(success, 2),
            "rounds_ok": len(ok),
            "score": round(score, 1),
            "qualify": bool(success >= MIN_SUCCESS and kb >= MIN_KBPS),
        })

    summary.sort(key=lambda r: -r["score"])
    json.dump(summary, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("\n===== 稳定性总榜（陕西移动宽带实测 %d 轮）=====" % args.rounds)
    print(f"{'站':<10}{'成功率':>7}{'码率中位':>11}{'首页':>8}{'详情':>8}{'片源':>9}{'评分':>9}  结论")
    for r in summary:
        mark = "✅入选" if r["qualify"] else "淘汰"
        print(f"{r['name']:<10}{r['success_rate']:>7.2f}{r['vod_kbps']:>10.0f}k"
              f"{r['list_ms']:>7}ms{r['detail_ms']:>7}ms{r['total']:>9}{r['score']:>9.0f}  {mark}")
    good = [r for r in summary if r["qualify"]][:MAX_SITES]
    print(f"\n达标 {len([r for r in summary if r['qualify']])} 个，最终入选 {len(good)} 个："
          f" {', '.join(r['name'] for r in good)}")
    print(f"已写入 {OUT}")


if __name__ == "__main__":
    main()
