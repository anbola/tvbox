#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟 TVBox 行为验证配置：
TVBox 读 site.categories 得到分类名，再用 site.ext.t 的「分类名:type_id」映射
把分类名转成 type_id 去请求 API。
本脚本按这个逻辑逐个分类验证，确保用户点任何分类都有内容。
"""
import json, urllib.request, ssl, urllib.parse, sys

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 5) okhttp/3.12.1"}

CFG = sys.argv[1] if len(sys.argv) > 1 else "tvbox_curated.json"


def get(url, extra=None):
    h = dict(UA)
    if extra:
        h.update(extra)
    r = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(r, timeout=25, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def main():
    d = json.load(open(CFG, encoding="utf-8"))
    print("=" * 70)
    print("模拟 TVBox 加载：逐分类验证是否有内容")
    print("=" * 70)
    total_bad = 0
    for s in d.get("sites", []):
        api = s.get("api", "")
        cats = s.get("categories", [])
        tmap_raw = s.get("ext", {}).get("t", "")
        tmap = {}
        for pair in tmap_raw.split(","):
            if ":" in pair:
                k, v = pair.rsplit(":", 1)
                tmap[k.strip()] = v.strip()
        print(f"\n【{s.get('name')}】 配置分类 {len(cats)} 个")
        if not cats:
            print("   ✗ 未配置 categories —— TVBox 将直接用 API 的 class 前几项（可能为空）")
            total_bad += 1
            continue
        sep = "&" if "?" in api else "?"

        def probe(cn):
            tid = tmap.get(cn)
            if tid is None:
                # 无映射：TVBox 会用分类名请求
                u = f"{api}{sep}ac=videolist&t={urllib.parse.quote(cn)}&pg=1"
            else:
                u = f"{api}{sep}ac=videolist&t={tid}&pg=1"
            try:
                r = get(u)
                return cn, tid, len(r.get("list", []))
            except Exception:
                return cn, tid, -1

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=12) as ex:
            probe_res = list(ex.map(probe, cats))
        bad = [(cn, tid, n) for cn, tid, n in probe_res if n <= 0]
        # 只报前 5 个问题分类
        if bad:
            total_bad += len(bad)
            print(f"   ✗ {len(bad)}/{len(cats)} 个分类取不到内容:")
            for cn, tid, n in bad[:6]:
                print(f"       {cn} (type_id={tid}) -> {n} 部")
        else:
            print(f"   ✓ 全部 {len(cats)} 个分类均有内容")
        # 展示前 6 个分类（用户实际会看到的前几个）
        print(f"   前6个分类: {'、'.join(cats[:6])}")
    print()
    print("=" * 70)
    if total_bad == 0:
        print(f"✓ 全部源的所有分类都有内容，用户不会再看到空页面")
    else:
        print(f"✗ 仍有 {total_bad} 个空分类")
    print("=" * 70)


if __name__ == "__main__":
    main()
