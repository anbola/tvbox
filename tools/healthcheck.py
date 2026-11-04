#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日健康检查（云端 GitHub Actions 调用，也可本地跑）

检查项：
  1) 线上 tvbox_clean.json：HTTP 200 + JSON 合法 + sites/lives 结构
     ★ 重点校验 lives 规范：type 必须 == 0、playerType 必须是 int、
       不能出现 url2 等非法字段 —— 写错就是「点播正常、直播空白」。
  2) lives/main.m3u、lives/public.m3u：200 + #EXTM3U 头 + 频道数达标 + 无非法行
  3) 每个点播站 api：能否返回含分类的 JSON（code=1 / class 非空）
  4) 订阅主地址 + 国内加速镜像：是否都能取到配置

输出：
  status.json        供 Pages 访问，人也能直接打开看
  GITHUB_OUTPUT      has_error / summary，供 workflow 决定是否开 issue
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://anbola.github.io/tvbox/"
UA = "okhttp/3.15.0"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

CONFIG_URLS = [
    ("主用 GitHub Pages", "https://anbola.github.io/tvbox/tvbox_clean.json"),
    ("备用 国内加速镜像", "https://testingcf.jsdelivr.net/gh/anbola/tvbox@main/tvbox_clean.json"),
]

errors = []
checks = []


def rec(name, ok, detail=""):
    checks.append({"item": name, "ok": bool(ok), "detail": str(detail)})
    print(f"  {'✓' if ok else '✗'} {name:<28} {detail}", flush=True)
    if not ok:
        errors.append(f"{name}: {detail}")
    return ok


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.status, r.read()


def check_config():
    print("\n[1] 配置订阅地址")
    cfg = None
    for name, url in CONFIG_URLS:
        try:
            code, raw = fetch(url)
            d = json.loads(raw.decode("utf-8", "ignore"))
            rec(f"{name} HTTP", code == 200, f"{code} / {len(raw)}B")
            if cfg is None:
                cfg = d
            # 第三方镜像有数小时缓存滞后：内容不同只做提示，不记入 errors，
            # 否则每日 healthcheck 会误报并自动开无用 issue（2026-11-04 修正）。
            # HTTP 200 + JSON 可解析 + lives 结构合法 已足以判定镜像可用。
            if cfg is not None and d.get("sites") != cfg.get("sites"):
                print(f"  INFO  {name} 内容滞后（CDN 缓存，仅提示）")
        except Exception as e:
            rec(f"{name} HTTP", False, type(e).__name__)
    return cfg


def validate_cfg(cfg):
    print("\n[2] 配置结构（TVBox / 影视仓 兼容）")
    if not cfg:
        rec("配置可解析", False, "所有订阅地址均失败")
        return
    sites = cfg.get("sites") or []
    rec("sites 非空", len(sites) > 0, f"{len(sites)} 个点播站")
    for s in sites:
        ok = (s.get("key") and s.get("type") == 1 and
              str(s.get("api", "")).startswith("http") and "ext" not in s)
        rec(f"  站 {s.get('name','?')}", ok,
            "key/type/api 完整" if ok else "缺 key 或 type≠1 或含 ext（TVBox 会静默跳过）")

    lives = cfg.get("lives") or []
    rec("lives 非空", len(lives) > 0, f"{len(lives)} 个直播源对象")
    for lv in lives:
        nm = lv.get("name", "?")
        problems = []
        if lv.get("type") != 0:
            problems.append("type≠0(必须为整数0=M3U)")
        if not isinstance(lv.get("playerType"), int):
            problems.append("playerType 不是整数(字符串会让部分分支整段丢弃)")
        if "url2" in lv:
            problems.append("含非法字段 url2(备用源应放数组第二个对象)")
        if not str(lv.get("url", "")).startswith("http"):
            problems.append("url 非法")
        rec(f"  直播 {nm[:16]}", not problems, "; ".join(problems) or "字段合规")


def check_m3u(name, path, min_channels=20):
    print(f"\n[3] 直播源 {path}")
    try:
        code, raw = fetch(BASE + path)
        txt = raw.decode("utf-8", "ignore")
        n = txt.count("#EXTINF")
        rec(f"{name} HTTP", code == 200, f"{code} / {len(raw)}B")
        rec(f"{name} #EXTM3U 头", txt.startswith("#EXTM3U"), txt.splitlines()[0][:40] if txt else "空")
        rec(f"{name} 频道数", n >= min_channels, f"{n} 个（阈值 {min_channels}）")
        bad = [l for l in txt.splitlines()
               if l.strip() and not l.startswith("#") and not l.startswith("http")]
        rec(f"{name} 无非法行", not bad, f"{len(bad)} 行" if bad else "全部合法")
        if any(ord(c) > 0xFFFF for c in txt):
            rec(f"{name} 无 emoji", False, "含非 BMP 字符，老版本 App 会整段解析失败")
        return True
    except Exception as e:
        rec(f"{name} HTTP", False, type(e).__name__)
        return False


def probe_vod(site):
    name, api = site.get("name", "?"), site.get("api", "")
    try:
        url = api + ("&" if "?" in api else "?") + "ac=list"
        code, raw = fetch(urllib.parse.quote(url, safe=":/?&=#%[]@!$'()*+,;~-._"), timeout=15)
        d = json.loads(raw.decode("utf-8", "ignore"))
        cls = d.get("class") or []
        return name, code == 200 and len(cls) > 0, f"HTTP{code} 分类{len(cls)}个"
    except Exception as e:
        return name, False, type(e).__name__


def check_vod(cfg):
    print("\n[4] 点播站 API 存活")
    sites = (cfg or {}).get("sites") or []
    if not sites:
        rec("点播站检查", False, "无站点")
        return
    with ThreadPoolExecutor(max_workers=8) as ex:
        for name, ok, detail in ex.map(probe_vod, sites):
            rec(f"  {name}", ok, detail)


def main():
    print(f"=== TVBox 健康检查 {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    cfg = check_config()
    validate_cfg(cfg)
    check_m3u("main.m3u(内网极速)", "lives/main.m3u", 60)
    check_m3u("public.m3u(公网通用)", "lives/public.m3u", 20)
    check_vod(cfg)

    status = {
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ok": len(errors) == 0,
        "errors": errors,
        "checks": checks,
        "subscription": CONFIG_URLS[0][1],
    }
    with open(os.path.join(ROOT, "status.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    summary = f"检查结果：{'全部通过 ✅' if not errors else '发现 %d 项异常 ❌' % len(errors)}\n\n" + \
              "\n".join(f"- {e}" for e in errors) + \
              f"\n\n共检查 {len(checks)} 项。详见仓库 status.json。"
    print("\n" + summary)

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("has_error=%s\n" % ("true" if errors else "false"))
            f.write("summary<<__END__\n%s\n__END__\n" % summary)


if __name__ == "__main__":
    main()
