#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
唯一权威地址表（2026-11-04 用户拍板）

用户明确要求：「能不能每次不要变那个网址？」
→ 订阅地址 SUBSCRIBE_URL **永久固定**。以后不管直播源、点播站、频道怎么更新，
  只改这个 URL 背后的文件内容（覆盖上传同一个文件），**绝不改 URL 本身**，
  也绝不要求用户重填或换地址。填一次，一直用。

→ 任何脚本 / 文档 / CI 需要引用地址时，一律以本文件为准；
  想改地址必须先改这里，且 tools/check_address.py 会把不一致拦下来。

⚠️ EMERGENCY_URLS 只是「主地址连续多日完全打不开」时的临时应急入口，
   平时绝不填、绝不改，也不要写进「推荐 / 主用」段落。
"""
SUBSCRIBE_URL = "https://anbola.github.io/tvbox/tvbox_clean.json"
LIVE_MAIN_URL = "https://anbola.github.io/tvbox/lives/main.m3u"
LIVE_PUBLIC_URL = "https://anbola.github.io/tvbox/lives/public.m3u"
LIVE_MIRROR_URL = "https://testingcf.jsdelivr.net/gh/anbola/tvbox@main/lives/main.m3u"
STATUS_URL = "https://anbola.github.io/tvbox/status.json"

# 极端故障时的临时应急入口（平时不要用）
EMERGENCY_URLS = (
    "https://testingcf.jsdelivr.net/gh/anbola/tvbox@main/tvbox_clean.json",
    "https://cdn.jsdmirror.com/gh/anbola/tvbox/tvbox_clean.json",
)

# 配置 lives 里允许出现的全部直播地址（新增备用源必须同步这里）
ALLOWED_LIVE_URLS = (LIVE_MAIN_URL, LIVE_MIRROR_URL, LIVE_PUBLIC_URL)
