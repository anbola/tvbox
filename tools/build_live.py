#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按【实测速度】生成直播源 main.m3u

输入：_probe/speeds.json（speedtest.py 产出）
规则：
  1) 频道名归一化（CCTV-1高清2K / CCTV1 / 央视一套 → 同一台）
  2) 每频道只保留最快的 N 条（默认 3），按码率降序 = TVBox 默认用最快那条
  3) 丢弃：码率 < 阈值、购物/导视/测试/轮播频道
  4) 分组：央视 / 卫视 / 陕西本地 / 其他
输出：lives/main.m3u
"""
import json
import os
import re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_KBPS = 700          # 低于此码率必然卡
KEEP_PER_CHANNEL = 3    # 每台保留条数（第1条是默认）

# 默认播放条目的"安全码率带"。
# 实测这批移动源里有 81 条 >10Mbps（最高 48Mbps），多为 2K/HEVC。
# 电视盒子自动播放第一条时若直接上 40Mbps+ 的 HEVC，老解码器极易花屏/闪退，
# 所以第一条只从 1500~8000kbps 里选，超高的降级为备用线路。
SAFE_MIN = 1500
SAFE_MAX = 8000

# ---------- 频道名归一化 ----------

CCTV_MAP = {
    1: "CCTV-1 综合", 2: "CCTV-2 财经", 3: "CCTV-3 综艺", 4: "CCTV-4 中文国际",
    5: "CCTV-5 体育", 6: "CCTV-6 电影", 7: "CCTV-7 国防军事", 8: "CCTV-8 电视剧",
    9: "CCTV-9 纪录", 10: "CCTV-10 科教", 11: "CCTV-11 戏曲", 12: "CCTV-12 社会与法",
    13: "CCTV-13 新闻", 14: "CCTV-14 少儿", 15: "CCTV-15 音乐", 16: "CCTV-16 奥林匹克",
    17: "CCTV-17 农业农村",
}

# 常见别名 → 标准名
ALIAS = {
    "央视一套": "CCTV-1 综合", "央视1套": "CCTV-1 综合", "CCTV1": "CCTV-1 综合",
    "央视二套": "CCTV-2 财经", "CCTV2": "CCTV-2 财经",
    "央视三套": "CCTV-3 综艺", "CCTV3": "CCTV-3 综艺",
    "央视四套": "CCTV-4 中文国际", "CCTV4": "CCTV-4 中文国际",
    "央视五套": "CCTV-5 体育", "CCTV5": "CCTV-5 体育",
    "央视六套": "CCTV-6 电影", "CCTV6": "CCTV-6 电影",
    "央视七套": "CCTV-7 国防军事", "CCTV7": "CCTV-7 国防军事",
    "央视八套": "CCTV-8 电视剧", "CCTV8": "CCTV-8 电视剧",
    "央视九套": "CCTV-9 纪录", "CCTV9": "CCTV-9 纪录",
    "CCTV10": "CCTV-10 科教", "CCTV11": "CCTV-11 戏曲", "CCTV12": "CCTV-12 社会与法",
    "CCTV13": "CCTV-13 新闻", "CCTV14": "CCTV-14 少儿", "CCTV15": "CCTV-15 音乐",
    "CCTV16": "CCTV-16 奥林匹克", "CCTV17": "CCTV-17 农业农村",
    "CCTV5+": "CCTV-5+ 体育赛事", "CCTV-5+": "CCTV-5+ 体育赛事",
    "CGTN": "CGTN", "中国教育1": "CETV-1 中国教育", "CETV1": "CETV-1 中国教育",
}

# 本地台（陕西商洛）
LOCAL_KW = ("商洛", "陕西", "西安", "咸阳", "渭南", "宝鸡", "汉中", "安康", "延安", "榆林", "铜川", "杨凌")
SHOP_KW = ("购物", "导视", "九宫格", "测试", "彩条", "广告", "春晚2023", "直播中国", "优购物", "好购物",
           "家有购物", "快乐购", "央广", "广播")


def normalize(name):
    """把各种写法的台名归一到标准名；无法识别返回清理后的原名"""
    s = name.strip()
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = re.sub(r"[（(][^）)]*[）)]", "", s)

    # 先看别名表（去掉后缀后比较）
    core = re.sub(r"(高清2K|高清|标清|超清|4K|HD|SD|蓝光|原画|-4K)$", "", s, flags=re.I).strip()
    core = core.replace(" ", "")
    for k, v in ALIAS.items():
        if core.replace("-", "").upper() == k.replace("-", "").upper():
            return v

    # CCTV-N 各种写法
    m = re.match(r"^(CCTV|央视)[-－]?\s*(\d{1,2})(\s*\+)?$", core, re.I)
    if m:
        num = int(m.group(2))
        plus = bool(m.group(3))
        if plus:
            return "CCTV-5+ 体育赛事" if num == 5 else f"CCTV-{num}+"
        if num in CCTV_MAP:
            return CCTV_MAP[num]
        return f"CCTV-{num}"

    # 央视"XX频道"中文写法
    for num, std in CCTV_MAP.items():
        if core in (f"央视{num}套", std.replace(" ", "")):
            return std

    # 卫视：统一成 "XX卫视"
    s2 = re.sub(r"(高清2K|高清|标清|超清|4K|HD|SD)$", "", s, flags=re.I).strip()
    s2 = s2.replace(" ", "")
    if "卫视" in s2:
        return s2
    return s2


def group_of(name):
    if name.startswith("CCTV") or name.startswith("CGTN") or name.startswith("CETV"):
        return "央视"
    if "卫视" in name:
        return "卫视"
    if any(k in name for k in LOCAL_KW):
        return "陕西本地"
    return "其他"


def should_skip(name, kbps):
    if kbps < MIN_KBPS:
        return True
    if any(k in name for k in SHOP_KW):
        return True
    # 纯轮播/剧场类点播频道（NewTV/IPTV- 剧场）保留在"其他"，不跳过
    if re.fullmatch(r"[\d\s\W]*", name):
        return True
    return False


def load_codecs():
    """读 codec_probe.py 的结果：url -> (codec, w, h)。缺失时返回空表（退化为只按码率排序）。"""
    p = os.path.join(ROOT, "_probe", "codecs.json")
    if not os.path.exists(p):
        print("! 未找到 _probe/codecs.json，跳过编码过滤（建议先跑 tools/codec_probe.py）")
        return {}
    m = {}
    for r in json.load(open(p, encoding="utf-8")):
        if r.get("ok"):
            m[r["url"]] = (r.get("codec"), r.get("w") or 0, r.get("h") or 0)
    return m


def main():
    path = os.path.join(ROOT, "_probe", "speeds.json")
    data = json.load(open(path, encoding="utf-8"))
    ok = [r for r in data if r.get("ok")]
    codecs = load_codecs()

    chans = defaultdict(list)
    skipped = 0
    for r in ok:
        std = normalize(r["name"])
        if not std or should_skip(std, r["kbps"]):
            skipped += 1
            continue
        chans[std].append(r)

    # 每台排序：**优先移动自家 CDN**（同网，稳定）；
    # 其次只把 1500~8000kbps 的流放到第一条（电视盒子解码安全区），
    # 超过 8000kbps 的 2K/HEVC 流降级为备用，避免一进直播就闪退。
    # 微鲸 WTV55K1（Android 5.0.2 / MStar）实测：解 HEVC 会 MediaCodec SIGABRT 直接崩App，
    # 所以 HEVC 一律不用；同频道内优先 1080p AVC，其次标清 AVC；同类里优先 ≤9Mbps。
    def prefer(it):
        k = it["kbps"]
        codec, w, h = codecs.get(it["url"], (None, 0, 0))
        avc = 0 if codec == "avc" else 1
        hd = 0 if h >= 720 else 1
        band = 0 if k <= 9000 else 1
        return (avc, hd, band, -min(k, 9000), it["ttfb_ms"])

    picked = {}
    dropped_hevc = []
    for std, lst in chans.items():
        if codecs:
            avc = [x for x in lst if codecs.get(x["url"], ("", 0, 0))[0] == "avc"]
            if not avc:
                dropped_hevc.append(std)
                continue
            lst = avc
        lst.sort(key=prefer)
        seen = set()
        out = []
        for it in lst:
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            out.append(it)
            if len(out) >= KEEP_PER_CHANNEL:
                break
        picked[std] = out

    # 排序：央视按频道号 → 卫视按固定顺序 → 陕西本地 → 其他
    def cctv_num(n):
        m = re.match(r"CCTV-(\d+)", n)
        return int(m.group(1)) if m else 99

    weishi_order = ["湖南卫视", "浙江卫视", "江苏卫视", "东方卫视", "北京卫视", "安徽卫视",
                    "广东卫视", "深圳卫视", "山东卫视", "天津卫视", "四川卫视", "湖北卫视",
                    "河南卫视", "河北卫视", "江西卫视", "东南卫视", "辽宁卫视", "黑龙江卫视",
                    "吉林卫视", "山西卫视", "陕西卫视", "甘肃卫视", "宁夏卫视", "青海卫视",
                    "新疆卫视", "云南卫视", "贵州卫视", "广西卫视", "海南卫视", "内蒙古卫视",
                    "重庆卫视", "厦门卫视", "南方卫视", "兵团卫视", "农林卫视", "延边卫视",
                    "三沙卫视", "康巴卫视", "安多卫视"]

    def order_key(n):
        g = group_of(n)
        gi = {"央视": 0, "卫视": 1, "陕西本地": 2, "其他": 3}[g]
        if g == "央视":
            return (gi, cctv_num(n), n)
        if g == "卫视":
            idx = weishi_order.index(n) if n in weishi_order else 999
            return (gi, idx, n)
        return (gi, 0, n)

    names = sorted(picked.keys(), key=order_key)

    lines = ["#EXTM3U"]
    total = 0
    stat = {"央视": 0, "卫视": 0, "陕西本地": 0, "其他": 0}
    for n in names:
        g = group_of(n)
        stat[g] += 1
        for it in picked[n]:
            lines.append(f'#EXTINF:-1 tvg-name="{n}" group-title="{g}",{n}')
            lines.append(it["url"])
            total += 1

    out = os.path.join(ROOT, "lives", "main.m3u")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    print(f"频道数: {len(names)} | 流数: {total} | 跳过(低码率/购物等): {skipped}")
    if dropped_hevc:
        print(f"剔除纯 HEVC 频道 {len(dropped_hevc)} 个（本机解码器会崩）: {', '.join(dropped_hevc)}")
    print(f"分组: {stat}")
    print(f"已写入 {out}")
    print("\n=== 各台最快一条 ===")
    for n in names:
        it = picked[n][0]
        star = "⭐" if it["kbps"] >= 8000 else ("✓" if it["kbps"] >= 3000 else "·")
        print(f"  {star} {n:<20} {it['kbps']:>8.0f}kbps  ttfb{it['ttfb_ms']:>4}ms  备份{len(picked[n])-1}条")


if __name__ == "__main__":
    main()
