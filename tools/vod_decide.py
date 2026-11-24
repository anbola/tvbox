# -*- coding: utf-8 -*-
"""v3.3 点播定稿决策器 —— 把「速度第一」写成可复现判据，不靠肉眼挑。

输入（同场次实测，全部来自本轮工具链）：
  _probe/vod_e2e_fine.json    搜索/首页/分类「完整响应」12 轮 P75 + 成功率
  _probe/vod_play_multi.json  每站 6 部影片的首片 kbps/TTFB + 详情 API P75
  _probe/vod_e2e_play.json    单条播放链路原始样本（交叉参考）

核心思路：**成员不减，按速度分角色**。
  历史教训：v3.2 只测首包 TTFB，把「搜索端点直接返回『暂不支持搜索』」的索尼
  和「完整响应 3.1s / 4.6s」的量子都当成快站，还让量子参与 quickSearch。
  TVBox 搜索会并发所有可搜索站，尾部等待 = 最慢那个，所以慢站必须退出聚搜。

三层角色：
  · sites[0]   → 首页默认源：完整响应最快的站（用户每次开机都等它）
  · quickSearch→ 只给搜索 P75 最低的 2 站（按搜索键的尾部等待）
  · searchable → 只给搜索有效且 P75 <= MAX_SEARCH_MS 的站；其余降为「仅浏览」，
                 内容池仍保留在首页，但不再拖慢每次搜索

用法：
  python tools/vod_decide.py            # 打印定稿与提速对比（dry-run）
  python tools/vod_decide.py --apply    # 写入 tools/vod_picks.json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "_probe")
PICKS = os.path.join(ROOT, "tools", "vod_picks.json")
MAX_SEARCH_MS = 2300        # 超过它的站不参与聚搜（仍可浏览）
QUICK_N = 2
FAMILY_KEEP = True          # 同内容家族只留最快的一个，避免重复资源池


def nz(x):
    """None/非数字统一按 0 参与对比，避免 round(None) 崩溃。"""
    return x if isinstance(x, (int, float)) else 0


def jload(fn, default=None):
    p = os.path.join(PROBE, fn)
    if not os.path.exists(p):
        return default
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except Exception:
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    fine = jload("vod_e2e_fine.json")
    multi = jload("vod_play_multi.json")
    if not fine or not multi:
        raise SystemExit("缺少 _probe/vod_e2e_fine.json / vod_play_multi.json，先跑测速工具链")
    fine_by = {r["api"]: r for r in fine["fine"]}
    play_by = {r["api"]: r for r in multi["rows"]}
    in_use = list(fine.get("in_use", []))

    # 现用成员作为候选（内容覆盖不减）；额外允许同族更快别名顶替同名家族
    rows = []
    for api in in_use:
        f = fine_by.get(api)
        if not f:
            print(f"! 现用站没进精测: {api}")
            continue
        p = play_by.get(api, {})
        r = {
            "name": f["name"], "api": api, "family": f["family"],
            "search_p75": f["search"]["p75"], "home_p75": f["home"]["p75"],
            "list_p75": f["list"]["p75"],
            "detail_p75": p.get("detail_p75"), "kbps_median": p.get("kbps_median"),
            "seg_ttfb_p75": p.get("seg_ttfb_p75"), "hist_kbps": p.get("hist_kbps"),
            "success_rate": f["success_rate"], "usable": f["usable"],
            "search_ok": f["search"]["p75"] is not None,
        }
        rows.append(r)

    # 同族别名顶替：若某个别名域名「交互更快且播放不更差」，则换域名（零内容损失）
    aliases = []
    for f in fine["fine"]:
        if f["api"] in in_use or not f["usable"] or f["search"]["p75"] is None:
            continue
        p = play_by.get(f["api"], {})
        cur = next((x for x in rows if x["family"] == f["family"]), None)
        if not cur:
            continue
        cand = {
            "name": f["name"], "api": f["api"], "family": f["family"],
            "search_p75": f["search"]["p75"], "home_p75": f["home"]["p75"],
            "list_p75": f["list"]["p75"], "detail_p75": p.get("detail_p75"),
            "kbps_median": p.get("kbps_median"), "seg_ttfb_p75": p.get("seg_ttfb_p75"),
            "hist_kbps": p.get("hist_kbps"), "success_rate": f["success_rate"],
            "usable": True, "search_ok": True,
        }
        aliases.append((cur, cand))

    def interaction(x):
        # 交互速度综合分（越小越快）；缺失项用 3000ms 兜底，不因缺数据被偏爱
        return (.50 * (x["search_p75"] or 9999)
                + .20 * (x["home_p75"] or 3000)
                + .10 * (x["list_p75"] or 3000)
                + .20 * (x["detail_p75"] or 3000))

    for cur, cand in aliases:
        # 速度第一：当且仅当「交互严格更快 且 播放分片不更差」才顶替（零内容损失、纯提速）
        if (interaction(cand) < interaction(cur)
                and (cand.get("kbps_median") or 0) >= (cur.get("kbps_median") or 0)):
            print(f"  别名顶替 {cur['name']}({cur['api'].split('/')[2]}) -> "
                  f"{cand['name']}({cand['api'].split('/')[2]})：交互 "
                  f"{round(interaction(cur))}ms -> {round(interaction(cand))}ms")
            rows[rows.index(cur)] = cand

    rows.sort(key=interaction)
    for i, r in enumerate(rows):
        r["interaction_score"] = round(interaction(r), 1)
        # 搜索端点无效（如索尼返回纯文本「暂不支持搜索」）或过慢 → 仅浏览
        r["searchable"] = 1 if (r["search_ok"] and r["usable"]
                                and r["search_p75"] <= MAX_SEARCH_MS
                                and r["success_rate"] >= 0.9) else 0
        r["quickSearch"] = 0
        r["role"] = ("首页默认源 + 聚搜" if i == 0 and r["searchable"]
                     else "可搜索" if r["searchable"] else "仅浏览")
    quick = [r for r in rows if r["searchable"]][:QUICK_N]
    for r in quick:
        r["quickSearch"] = 1
        r["role"] += " + quickSearch" if "聚搜" not in r["role"] else ""

    # 量化对比：v3.2 的 quickSearch = 非凡5 + 量子；5 站全部 searchable=1
    v32_quick = [r for r in fine["fine"] if r["name"] in ("非凡5", "量子")]
    v32_quick_tail = max([r["search"]["p75"] for r in v32_quick
                          if r["search"]["p75"]] or [0])
    v32_searchable = [r["search"]["p75"] for r in fine["fine"]
                      if r["api"] in in_use and r["search"]["p75"]]
    v33_quick_tail = max([r["search_p75"] for r in quick] or [0])
    v33_searchable = [r["search_p75"] for r in rows if r["searchable"]]
    cmp = {
        "quickSearch 尾部等待_ms": [round(nz(v32_quick_tail)), round(nz(v33_quick_tail))],
        "参与聚搜的路数": [len(in_use), len(v33_searchable)],
        "聚搜尾部等待_ms": [round(max(v32_searchable) if v32_searchable else 0),
                      round(max(v33_searchable) if v33_searchable else 0)],
        "搜索端点无效的站参与聚搜": [1, 0],   # 索尼
        "首页默认源搜索P75_ms": [round(nz(next((r["search"]["p75"] for r in fine["fine"]
                                  if r["name"] == "非凡5"), 0))),
                         round(nz(rows[0]["search_p75"]))],
        "第2站搜索P75_ms": [round(nz(next((r["search"]["p75"] for r in fine["fine"]
                                  if r["name"] == "索尼"), 0))),
                       round(nz(rows[1]["search_p75"]))],
    }

    print("\n=== v3.3 定稿（完整响应 · 速度第一 · 成员不减）===", flush=True)
    print(f"{'#':<3}{'站':<10}{'交互分':>9}{'搜索':>9}{'首页':>9}{'分类':>9}"
          f"{'详情':>9}{'分片kbps':>10}{'首片':>9}  {'搜索':<6}{'快搜':<6}角色")
    for i, r in enumerate(rows, 1):
        print(f"{i:<3}{r['name']:<10}{r['interaction_score']:>9}"
              f"{str(r['search_p75']):>9}{str(r['home_p75']):>9}"
              f"{str(r['list_p75']):>9}{str(r['detail_p75']):>9}"
              f"{str(r['kbps_median']):>10}{str(r['seg_ttfb_p75']):>9}  "
              f"{r['searchable']:<6}{r['quickSearch']:<6}{r['role']}", flush=True)
    print("\nv3.2 -> v3.3（越小越好）：", flush=True)
    for k, (old, new) in cmp.items():
        d = f"  ({(new - old) / old * 100:+.0f}%)" if isinstance(old, (int, float)) and old else ""
        print(f"  {k:<28} {str(old):>8} -> {str(new):>8}{d}", flush=True)

    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": "v3.3",
        "criterion": (
            "完整响应 full_ms（非首包）12轮P75：搜索/首页/分类/详情；"
            "每站6部影片首片 kbps 中位交叉；同场次 https A/B。"
            "成员不减按交互速度排序，quickSearch 给最快2站，"
            "搜索无效或 P75>2300ms 的站降为 searchable=0 仅浏览"
        ),
        "measurement": {
            "tool": "tools/vod_e2e.py + tools/vod_play_multi.py",
            "fine_rounds": fine.get("fine_rounds"),
            "films_per_site": 6,
            "raw": ["_probe/vod_e2e_fine.json", "_probe/vod_play_multi.json",
                    "_probe/vod_e2e_play.json", "_probe/vod_e2e_coarse.json"],
        },
        "sites": [{k: r[k] for k in ("name", "api", "family", "search_p75", "home_p75",
                                     "list_p75", "detail_p75", "kbps_median",
                                     "seg_ttfb_p75", "hist_kbps", "interaction_score",
                                     "searchable", "quickSearch", "role")}
                  for r in rows],
        "quickSearch": [r["name"] for r in quick],
        "compare": cmp,
        "note": (
            "v3.2 按首包 TTFB 选站有盲区：suoniapi.com 对任何 wd= 都返回纯文本"
            "「暂不支持搜索」，量子完整响应搜索 3120ms/首页 4593ms、电影天堂详情 5138ms，"
            "却都参与了搜索并发。v3.3 让慢站退为仅浏览，内容池一个不少，搜索只等最快的站。"
        ),
    }
    if a.apply:
        with io.open(PICKS, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        print(f"\n已写入 {PICKS}", flush=True)
    else:
        p = os.path.join(PROBE, "vod_e2e_decision.json")
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        print(f"\n(dry-run) 决策预览 -> {p}；加 --apply 写入 vod_picks.json", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
