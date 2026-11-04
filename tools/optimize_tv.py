#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""电视端优化（幂等，可反复跑）— 目标只有一个：家里电视最快、最稳。

消费 `tools/tv_speedtest.py` 的 3 轮实测数据，只做两件有实收益的事：

  A. lives/main.m3u —— 剔除「3 轮全部失败」的死链。
     换台撞上死链会白等 5~10 秒，这是电视端唯一还能明显体感到的卡顿来源。
     **其余频道顺序、线路顺序一律不动**：avc / 1080p / 同网 / 码率 的排序优先级
     是 4:3 方屏与微鲸盒子闪退的根治手段，不许为几十毫秒打乱。

  B. tvbox_clean.json —— 按 3 轮实测 API 首包升序，只给最快的 2 个站开
     quickSearch，其余关掉。TVBox 搜索时并发请求这些站，**最慢那个决定整体等待**。
     实测：原「虎牙 842ms + 暴风 1899ms」= 等 1.9s；改「量子 808ms + 虎牙 842ms」
     = 等 0.84s。站点成员与顺序不变（仍按 3 轮稳定性评分排，保画质/片源）。

明确不做的事（2026-11-04 实测踩过，别再重复折腾）：
  · 不把 70ms 的 720x576 / MP3 内网线提到第一：会立刻 4:3 方屏，
    微鲸 WTV55K1(Android 5.0.2) 还有 ACodec abort 闪退风险。
    海南卫视 / 西藏卫视 的 1080p 首条虽然要 1.2~3.2s，但必须保留。
    已从候选池 58 条 IPv4 线里找过替代：快线全是 576p+MP3，无合格替代。
  · 不为「中位省 11ms」去买单去动 106 个频道的线路顺序（收益远小于画质风险）。
  · 不改订阅地址、不改点播站成员、不改 lives 顺序（电视永远第一）。

用法：
  python tools/tv_speedtest.py 3     # 先测，生成 _probe/tv_*_ttfb.json
  python tools/optimize_tv.py        # 应用优化
  python tools/optimize_tv.py --dry  # 只看报告不改文件
"""
import io
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "_probe")
LIVE = os.path.join(ROOT, "lives", "main.m3u")
CFG = os.path.join(ROOT, "tvbox_clean.json")
DRY = "--dry" in sys.argv


def load(name):
    p = os.path.join(PROBE, name)
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else {}


def api_of(measured_url):
    """tv_speedtest 的 key = api.rstrip('/') + '/?ac=videolist&pg=1'"""
    return measured_url.split("/?")[0]


def optimize_live(ttfb):
    dead = {u for u, v in ttfb.items() if not v.get("ok")}
    if not dead:
        return {"removed": [], "lines_before": 0, "lines_after": 0}
    lines = io.open(LIVE, encoding="utf-8").read().splitlines()
    out, removed, i = [], [], 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("#EXTINF") and i + 1 < len(lines):
            u = lines[i + 1].strip()
            if u in dead:
                removed.append(u)
                i += 2
                continue
        out.append(l)
        i += 1
    before = sum(1 for l in lines if l.startswith("http"))
    after = sum(1 for l in out if l.startswith("http"))
    if not DRY and removed:
        with open(LIVE, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(out) + "\n")
    return {"removed": removed, "lines_before": before, "lines_after": after}


def optimize_vod(vod):
    cfg = json.load(io.open(CFG, encoding="utf-8"))
    # 判据：搜索并发的等待 = 最慢那个站，所以看**尾部延迟(P75)**，不是中位数。
    # 2026-11-04 教训：只测 3 轮按中位数挑，选出了波动最大的虎牙
    # （9 轮 P75 1739ms / 最差 5470ms），单独复测时量子也从 808ms 跳到 3468ms。
    # 优先级：9 轮 P75 > 多轮 ttfb 中位数 > 无穷大（缺数据不误开慢站）。
    stab = load("tv_vod_stability.json")
    # 与 build_config.py 完全一致的内置兜底：测速数据丢失也不会退回「评分前 2」。
    p75 = {"索尼": 836, "360": 1147, "量子": 1148,
           "虎牙": 1739, "暴风": 1892, "金鹰": 3328}
    p75.update({s["name"]: s["p75_ms"] for s in stab.get("sites", [])
                if s.get("p75_ms") is not None})
    med = {}
    for measured_url, v in vod.items():
        if v.get("ttfb_ms") is not None and v.get("ok"):
            med[api_of(measured_url)] = v["ttfb_ms"]

    def cost(s):
        v = p75.get(s["name"])
        return v if v is not None else med.get(s["api"].rstrip("/"), 9e9)

    scored = sorted(((cost(s), s["name"], s["api"]) for s in cfg["sites"]),
                    key=lambda x: x[0])
    fastest = {a for _, _, a in scored[:2]}
    before = {s["name"]: s.get("quickSearch", 0) for s in cfg["sites"]}
    wait_before = max([cost(s) for s in cfg["sites"] if before.get(s["name"])] or [0])
    for s in cfg["sites"]:
        s["quickSearch"] = 1 if s["api"] in fastest else 0
    after = {s["name"]: s.get("quickSearch", 0) for s in cfg["sites"]}
    if not DRY:
        with open(CFG, "w", encoding="utf-8", newline="\n") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    return {
        "criterion": "9轮P75(ms)" if stab.get("sites") else "内置9轮P75兜底(ms)",
        "cost_ms": {s["name"]: cost(s) for s in cfg["sites"]},
        "quick_before": before, "quick_after": after,
        "fastest_two": [n for _, n, _ in scored[:2]],
        "wait_before_ms": wait_before,
        "wait_after_ms": scored[1][0] if len(scored) > 1 else None,
    }


def main():
    ttfb = load("tv_live_ttfb.json")
    vod = load("tv_vod_ttfb.json")
    if not ttfb or not vod:
        raise SystemExit("缺少测速数据，请先跑：python tools/tv_speedtest.py 3")

    a = optimize_live(ttfb)
    b = optimize_vod(vod)
    report = {
        "generated": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": DRY, "live": a, "vod": b,
    }
    with open(os.path.join(PROBE, "tv_optimize_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    print("=== 电视端优化报告 ===")
    print(f"[直播] 剔除死链 {len(a['removed'])} 条：{a['lines_before']} -> {a['lines_after']} 线路")
    for u in a["removed"]:
        print("   -", u[:110])
    print(f"[点播] 判据 {b['criterion']}:", b["cost_ms"])
    print(f"[点播] 搜索并发 {b['fastest_two']}；"
          f"最慢等待 {b['wait_before_ms']}ms -> {b['wait_after_ms']}ms")
    print("[点播] quickSearch:", b["quick_after"])
    print("（未改：订阅地址 / 站点成员与顺序 / lives 顺序 / 1080p 优先）")
    print("模式:", "只出报告（--dry）" if DRY else "已写入文件")


if __name__ == "__main__":
    main()
