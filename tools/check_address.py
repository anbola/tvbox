#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""订阅地址固定性校验 —— CI + 本地都跑，专门防止「网址又变了」。

用法：python tools/check_address.py   （失败 exit 1）
校验：配置 / README / status / healthcheck / SKILL / CI 里的订阅地址
      必须全部等于 tools/address.py 里的 SUBSCRIBE_URL。
"""
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from address import (  # noqa: E402
    SUBSCRIBE_URL, LIVE_MAIN_URL, LIVE_PUBLIC_URL,
    ALLOWED_LIVE_URLS, EMERGENCY_URLS,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors = []


def ck(name, ok, detail=""):
    print(f"  {'OK  ' if ok else 'FAIL'} {name:<32} {detail}", flush=True)
    if not ok:
        errors.append(f"{name}: {detail}")


def read(rel):
    p = os.path.join(ROOT, rel)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


# 1) 配置里的直播地址必须固定，且不含非法字段
#    ⚠️ 2026-11-04 19:42 用户拍板「电视绝对优先」：lives[0] 必须是内网极速 main.m3u。
#    TVBox / 影视仓默认加载第一项；把公网挪到第一会让家里电视从 106 台变 43 台、
#    起播 0.1s 变 2~8s。手机改用第 ③ 项（切一次即记住）。此断言防止以后被"优化"回去。
cfg = json.loads(read("tvbox_clean.json"))
lives = cfg.get("lives", [])
ck("配置 lives 首项=电视内网极速(电视优先)",
   bool(lives) and lives[0].get("url") == LIVE_MAIN_URL,
   lives[0].get("url", "") if lives else "lives 为空")
ck("配置保留手机公网源", any(l.get("url") == LIVE_PUBLIC_URL for l in lives))
ck("lives 无非法 url2", all("url2" not in l for l in lives))
ck("lives url 均在白名单",
   all(l.get("url") in ALLOWED_LIVE_URLS for l in lives),
   str([l.get("url") for l in lives if l.get("url") not in ALLOWED_LIVE_URLS]))

# 2) README 第一节只能给这一个订阅地址
readme = read("README.md")
sec = readme.split("## 一、唯一地址", 1)[-1].split("\n## ", 1)[0]
urls = set(re.findall(r"https?://[^\s`)\]|]+tvbox_clean\.json", sec))
ck("README 唯一地址段只含主地址",
   SUBSCRIBE_URL in urls and urls <= ({SUBSCRIBE_URL} | set(EMERGENCY_URLS)),
   str(sorted(urls)))
ck("README 已声明永久固定", "永久固定" in sec)
ck("README 不再建议改地址",
   "可直接把配置地址改成" not in readme and "配置地址改填" not in readme
   and "配置地址改成 `https://" not in readme)

# 3) 其他引用处一致
st = read("status.json")
if st:
    ck("status.json subscription 一致",
       json.loads(st).get("subscription") == SUBSCRIBE_URL)
ck("healthcheck 主地址一致", f'"{SUBSCRIBE_URL}"' in read("tools/healthcheck.py"))
skill = read(".workbuddy/skills/anbola-tvbox/SKILL.md")
ck("SKILL 记录唯一入口且声明固定",
   SUBSCRIBE_URL in skill and "永久固定" in skill)
ck("CI 会跑本校验", "check_address.py" in read(".github/workflows/refresh.yml"))

print()
if errors:
    print(f"地址校验失败 {len(errors)} 项：")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print(f"地址校验通过：订阅地址永久固定 = {SUBSCRIBE_URL}")
