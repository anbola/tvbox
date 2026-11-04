#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成最终单文件配置 tvbox_clean.json

输入：_probe/vod_report.json（点播站真实测速结果）+ lives/main.m3u
规则：
  1) 只保留"视频分片实测 ≥ MIN_VOD_KBPS"的站，按视频速度降序
  2) 每站分类逐类查 total，只保留"真有货"的分类（total ≥ MIN_TOTAL）
  3) 只有最快的 2 个站开 quickSearch（搜索时并发查询，站越多越慢）
  4) 配置只留 sites + lives 两项，无任何外部依赖（不会"配置解析失败"）
"""
import hashlib
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "okhttp/3.15.0"

MIN_VOD_KBPS = 1200     # 视频分片低于此值会卡
MIN_TOTAL = 100         # 分类至少这么多片才算"有货"
MAX_SITES = 6           # 站越多首页标签越多，但只前 2 个开 quickSearch，故 6 个也流畅且更抗单站失效
MAX_CATS = 14

# 分类优先级：主分类 → 电影子类 → 剧集 → 综艺 → 动漫 → 纪录片 → 其它
# 注意 1：实测这些采集站的"电影/电视剧"主分类服务器端普遍是 0 条，
#         真正有货的是子分类（动作片/剧情片/国产剧…），所以子分类必须排在能入选的位置。
# 注意 2：伦理片/理论片 属于成人内容，家用电视必须剔除，故不在列表中。
PRIORITY = [
    "电影", "电影片", "电视剧", "连续剧",
    "动作片", "喜剧片", "剧情片", "科幻片", "爱情片", "恐怖片",
    "国产剧", "欧美剧", "香港剧", "韩国剧",
    "综艺", "综艺片", "大陆综艺",
    "动画片", "动漫", "动漫片", "国产动漫",
    "纪录片", "记录片",
    "战争片", "犯罪片", "悬疑片", "冒险片", "奇幻片", "武侠片", "灾难片",
    "短剧", "体育", "解说", "预告片", "其他",
]


def get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def site_key(api):
    """给每个站点生成稳定的 ASCII key。

    TVBox 用 key 作为站点唯一标识（首页标签、搜索、历史记录都依赖它）。
    v2.0 曾经漏掉这个字段，导致首页站点列表全部失效 —— 必须保留。
    """
    host = urllib.parse.urlparse(api).netloc.split(":")[0]
    base = re.sub(r"[^a-z0-9]", "", host.split(".")[0].lower()) or "site"
    return base + "_" + hashlib.md5(api.encode("utf-8")).hexdigest()[:4]


def force_https(api):
    """统一走 https：Android 9+ 默认禁止明文 http，混用会让部分站点直接空列表。"""
    return re.sub(r"^http://", "https://", api, count=1)


def cat_total(api, tid):
    try:
        d = get_json(f"{api}?ac=videolist&t={urllib.parse.quote(str(tid))}&pg=1", timeout=12)
        return int(d.get("total") or len(d.get("list") or []))
    except Exception:
        return 0


def build_site(site, quick):
    api = force_https(site["api"])
    try:
        classes = get_json(api + "?ac=list").get("class") or []
    except Exception as e:
        print(f"  {site['name']}: 取分类失败 {type(e).__name__}")
        return None
    idmap = {c["type_name"]: c["type_id"] for c in classes if c.get("type_name")}
    names = [n for n in PRIORITY if n in idmap]
    # 候选不足时补其它分类（保持服务器顺序）
    if len(names) < 12:
        for c in classes:
            n = c.get("type_name")
            if n and n not in names:
                names.append(n)

    # 关键：对【全部候选分类】查 total，而不是只查前 20 个，
    # 否则"动画片/纪录片/短剧"这类排在后面但真有货的分类会被漏掉。
    cand = [(n, idmap[n]) for n in names[:30]]
    ex = ThreadPoolExecutor(max_workers=10)
    futs = {ex.submit(cat_total, api, c[1]): c[0] for c in cand}
    totals = {}
    try:
        for f in as_completed(futs, timeout=300):
            totals[futs[f]] = f.result()
    except TimeoutError:
        for f in futs:
            if f.done():
                try:
                    totals[futs[f]] = f.result()
                except Exception:
                    pass
    finally:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    picked = [n for n in names[:30] if totals.get(n, 0) >= MIN_TOTAL]
    if len(picked) < 6:
        picked = [n for n in names[:30] if totals.get(n, 0) >= 30][:8]
    picked = sorted(picked, key=lambda n: PRIORITY.index(n) if n in PRIORITY else 99)[:MAX_CATS]
    if not picked:
        print(f"  {site['name']}: 无有货分类，丢弃")
        return None

    detail = ", ".join(f"{n}{totals.get(n, 0)}" for n in picked)
    print(f"  {site['name']:<8} 视频{site['vod_kbps']:>7.0f}kbps  分类{len(picked)}: [{detail}]")
    return {
        "key": site_key(api),
        "name": site["name"],
        "type": 1,
        "api": api,
        "searchable": 1,
        "quickSearch": 1 if quick else 0,
        "filterable": 0,
        "categories": picked,
    }


def main():
    # 数据源优先级：稳定性榜单（多轮采样）> 旧版 final > 单次报告
    # 单次测速波动极大（同一站可能 7.3Mbps / 0.6Mbps 来回跳），
    # 只有 vod_stable.json 的「成功率 × 码率中位数」才能代表真正优质。
    cands = [
        os.path.join(ROOT, "_probe", "vod_stable.json"),
        os.path.join(ROOT, "_probe", "vod_final.json"),
        os.path.join(ROOT, "_probe", "vod_report.json"),
    ]
    src = next((p for p in cands if os.path.exists(p)), None)
    if not src:
        raise SystemExit("没有点播测速数据，请先跑 tools/vod_stable.py")
    rep = json.load(open(src, encoding="utf-8"))
    print(f"数据来源: {os.path.basename(src)}")

    stable = "vod_stable.json" in src
    if stable:
        # 稳定性榜单：必须 qualify（成功率≥2/3 且码率中位数≥1200），按综合评分降序
        good = [r for r in rep if r.get("qualify")]
        good.sort(key=lambda r: -r.get("score", 0))
    else:
        # 旧数据兼容路径
        good = [r for r in rep if r.get("vod_kbps", 0) >= MIN_VOD_KBPS and not r.get("err")]
        good.sort(key=lambda r: (-r["vod_kbps"], r.get("list_ms") or 9999))

    # 同族去重：「量子 / 量子1」「非凡 / 非凡5 / 非凡1」「360 / 360新」
    # 往往是同一套资源池的不同域名，同时入选等于重复内容、白占名额。
    def family(name):
        return re.sub(r"(新|\d+)$", "", (name or "").strip()) or name
    seen = set()
    deduped = []
    for r in good:
        fam = family(r.get("name"))
        if fam in seen:
            continue
        seen.add(fam)
        deduped.append(r)
    good = deduped[:MAX_SITES]
    if not good:
        raise SystemExit("没有达标点播站，请先跑 tools/vod_stable.py（多轮稳定性测速）")

    # 【2026-11-04 电视提速】quickSearch 不再按「评分前 2」给。
    # TVBox 搜索时并发请求这些站，等待时间 = 最慢那个，所以按**9 轮 P75 尾部延迟**挑，
    # 不能按中位数：实测只测 3 轮按中位数会选出波动最大的虎牙(P75 1739ms/最差 5.5s)。
    # 数据优先级：tv_vod_stability.json(9轮P75) > tv_vod_ttfb.json(多轮中位数) > 评分前2。
    # 站点**成员与顺序仍按 3 轮稳定性评分**，保证画质/片源不受影响。
    # 内层兜底：测速数据文件若被清理，也别退回「评分前 2」（那会选中波动最大的虎牙）。
    # 2026-11-04 20:42 九轮 P75 实测值，按站名固定，仅在没有数据文件时生效。
    FALLBACK_P75 = {"索尼": 836, "360": 1147, "量子": 1148,
                    "虎牙": 1739, "暴风": 1892, "金鹰": 3328}
    rank_name, rank_api = {}, {}
    sp = os.path.join(ROOT, "_probe", "tv_vod_stability.json")
    tp = os.path.join(ROOT, "_probe", "tv_vod_ttfb.json")
    if os.path.exists(sp):
        for s in json.load(open(sp, encoding="utf-8")).get("sites", []):
            if s.get("p75_ms") is not None:
                rank_name[s["name"]] = s["p75_ms"]
    if os.path.exists(tp):
        for k, v in json.load(open(tp, encoding="utf-8")).items():
            if v.get("ttfb_ms") is not None and v.get("ok"):
                rank_api[k.split("/?")[0]] = v["ttfb_ms"]
    quick_apis = set()
    if rank_name or rank_api:
        def cost(r):
            v = rank_name.get(r["name"], FALLBACK_P75.get(r["name"]))
            return v if v is not None else rank_api.get(
                force_https(r["api"]).rstrip("/"), 9e9)
        ranked = sorted(good, key=cost)
        quick_apis = {force_https(r["api"]).rstrip("/") for r in ranked[:2]}
        print(f"  quickSearch 按尾部延迟(P75)给: {[r['name'] for r in ranked[:2]]}")

    print(f"入选点播站 {len(good)} 个（稳定性评分降序）：")
    sites = []
    for i, r in enumerate(good):
        quick = (force_https(r["api"]).rstrip("/") in quick_apis
                 if (rank_name or rank_api) else (i < 2))
        s = build_site(r, quick=quick)
        if s:
            sites.append(s)

    # 直播源主用地址：用户熟悉的 GitHub Pages（稳定、长期可用）。
    # 想换成自己的真·国内托管（Cloudflare Pages / 七牛 / 又拍云）时，
    # 设环境变量 TVBOX_LIVE_BASE 即可，无需改代码；例如：
    #   TVBOX_LIVE_BASE=https://anbola-tvbox.pages.dev/lives/main.m3u
    #   TVBOX_LIVE_BASE=https://<你的七牛CDN域名>/lives/main.m3u
    LIVE_PRIMARY = os.environ.get(
        "TVBOX_LIVE_BASE",
        "https://anbola.github.io/tvbox/lives/main.m3u",
    )
    # 备用：国内加速镜像。主用偶发慢/超时时，TVBox 自动回退到这一条（详见仓库根 TVBox_CDN与部署修复方案.md）。
    LIVE_BACKUP = "https://testingcf.jsdelivr.net/gh/anbola/tvbox@main/lives/main.m3u"

    # ⚠️ lives 字段规范（TVBox / 影视仓 / FongMi / takagen99 通用，2026-11-04 核实）：
    #   · "type": 0 必须显式写 —— 0=M3U、1=TXT。缺省值虽是 0，但不少分支缺省时
    #     会把整段 lives 判为无效并静默丢弃，表现就是「点播有、直播全空」。
    #   · "playerType" 必须是【整数】1(IJK)，写成字符串 "1" 会让部分 Gson 严格解析抛错。
    #   · lives 对象里【没有 url2 字段】！备用直播源只能靠「数组里放多个对象」实现，
    #     TVBox 会在直播页并列列出、可手动切换；写非法字段有整段被丢弃的风险。
    #   · playerType 钉死 1(IJK)：微鲸 WTV55K1 用 EXO 硬解这批源的 MP3 音频时，
    #     Android 5.0.2 的 ACodec 会在 OMX_IndexParamAudioMp3 上 CHECK 失败直接 abort，
    #     表现为「点直播闪一下就退出」。IJK + 软解可绕开该平台缺陷。
    # 【2026-11-04 19:42 用户拍板：电视绝对优先，不许再改】
    # lives[0] 是 TVBox / 影视仓**默认加载**的直播源，必须是家里电视用的内网极速
    # main.m3u（106 台 / 174 线路，运营商内网 CDN，实测首包 0.05~0.14s）。
    # 19:30 曾把公网 public.m3u 挪到第一想让手机"零操作可看"，实测对电视影响过大：
    #   · 台数 106 → 43（少 6 成，陕西本地台/地方台全没了）
    #   · 起播 0.1s 级 → 部分公网线路 2~8s，且是民间小站/裸 IP，随时会失效
    #   · 电视是主力设备，每次开机/换台都要手动切源，遥控器操作更烦
    # 用户明确「最主要是看电视，影响大就绝对把电视放第一位」→ 恢复内网第一。
    # 手机侧成本：首次在直播页切一次 ③（App 会记住），或壳若有独立「直播地址」框
    # 直接填 public.m3u 一次配好。这已经是最接近"区分设备"的做法。
    # ⚠️ 静态单网址（GitHub Pages 无后端、TVBox 不执行 JS、手机连家里 WiFi 时
    #    与电视出口 IP 完全相同）在架构上**无法**按设备/网络自动返回不同 lives 顺序。
    #    不要为了"智能化"引入动态后端 / 第二个网址 —— 会牺牲速度、稳定性和固定网址。
    # ⚠️ 订阅地址 SUBSCRIBE_URL 一字未改；以后别再把公网挪到第一项。
    PUBLIC_BASE = os.environ.get(
        "TVBOX_PUBLIC_BASE",
        "https://anbola.github.io/tvbox/lives/public.m3u",
    )
    has_public = os.path.exists(os.path.join(ROOT, "lives", "public.m3u"))

    lives = [
        {
            "name": "① 家里电视·移动内网极速",
            "type": 0,
            "url": LIVE_PRIMARY,
            "playerType": 1,
        },
        {
            "name": "② 备用·国内加速镜像",
            "type": 0,
            "url": LIVE_BACKUP,
            "playerType": 1,
        },
    ]
    if has_public:
        lives.append({
            "name": "③ 手机/外网·公网通用",
            "type": 0,
            "url": PUBLIC_BASE,
            "playerType": 1,
        })
    else:
        print("! 未找到 lives/public.m3u，跳过公网版（建议跑 tools/build_public.py）")

    cfg = {"sites": sites, "lives": lives}
    out = os.path.join(ROOT, "tvbox_clean.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {out}")
    print(f"站点 {len(sites)} 个 | 顶层键 {list(cfg.keys())}")


if __name__ == "__main__":
    main()
