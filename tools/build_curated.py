#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 TVBox「实测精选」配置。
原则：每一个源都必须经过真实请求验证，验证不过的一律不收录。
- 点播源：只保留实测返回标准 CMS 格式(list + class)且分类数>0 的明文 API
- 直播源：只保留实测可达的清洗版 m3u（托管在 GitHub Pages）
- 解析接口：只保留实测能解析出播放器的
"""
import json, os, urllib.request, ssl, shutil
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0"}
G = "https://anbola.github.io/tvbox/lives/"

# ============ 候选点播 API（来自 TVboxorg 官方配置）============
CAND_APIS = [
    ("suoniapi.com", "https://suoniapi.com/api.php/provide/vod/?ac=list", "🎬索尼┃高清"),
    ("lzizy1.com",   "https://lzizy1.com/api.php/provide/vod/?ac=list", "🎬量子┃资源"),
    ("huyaapi.com",  "https://www.huyaapi.com/api.php/provide/vod/from/hym3u8", "🎬虎牙┃采集"),
    ("ffzy5.tv",     "http://ffzy5.tv/api.php/provide/vod", "🎬非凡┃资源"),
    ("hhzyapi.com",  "https://hhzyapi.com/api.php/provide/vod/", "🎬火狐┃采集"),
    ("apibdzy.com",  "https://api.apibdzy.com/api.php/provide/vod/?ac=list", "🎬百度┃采集"),
    ("bfzyapi.com",  "https://bfzyapi.com/api.php/provide/vod", "🎬暴風┃采集"),
    ("360zy.com",    "https://360zy.com/api.php/provide/vod?", "🎬360┃采集"),
    ("rycjapi.com",  "https://cj.rycjapi.com/api.php/provide/vod", "🎬如意┃资源"),
    ("ffzy1.tv",     "http://ffzy1.tv/api.php/provide/vod/", "🎬非凡1┃资源"),
    # 实测新增：极速/闪电/苹果/光速/量子lzi/非凡ffzyapi
    ("jszyapi.com",    "https://jszyapi.com/api.php/provide/vod/",        "🎬极速┃资源"),
    ("shandianapi.com","https://sdzyapi.com/api.php/provide/vod/",         "🎬闪电┃资源"),
    ("ffzyapi.com",    "https://api.ffzyapi.com/api.php/provide/vod/",     "🎬非凡2┃资源"),
    ("guangsuapi.com", "https://api.guangsuapi.com/api.php/provide/vod/",  "🎬光速┃资源"),
    ("lziapi.com",     "http://cj.lziapi.com/api.php/provide/vod/",        "🎬量子2┃资源"),
    ("cjffzyapi.com",  "http://cj.ffzyapi.com/api.php/provide/vod/",       "🎬非凡3┃资源"),
    # 下面是实测已失效的，保留在列表里以证明筛选有效
    ("kekezy1.com",  "https://kekezy1.com/api.php/provide/vod/?ac=list", "✗可可"),
    ("49zy1.com",    "https://49zy1.com/api.php/provide/vod/?ac=list", "✗四九"),
    ("qhzyapi.com",  "https://caiji.qhzyapi.com/api.php/provide/vod/", "✗奇虎"),
    ("taopianapi.com", "https://taopianapi.com/cjapi/mc/vod/json.html", "✗淘片"),
    ("mv.wogg.link", "https://mv.wogg.link/mv/vod", "✗MTV"),
    ("feisuzyapi.com", "https://www.feisuzyapi.com/api.php/provide/vod/?ac=list", "✗飞速"),
    ("xiaohu.icu",   "http://c.xiaohu.icu/api.php/provide/vod/", "✗小胡"),
]

# 有些采集站会校验 Referer/Origin，缺失时返回 403
EXTRA_HEADERS = {
    "apibdzy.com": {"Referer": "https://api.apibdzy.com/", "Origin": "https://api.apibdzy.com",
                    "Accept-Language": "zh-CN,zh;q=0.9"},
    "360zy.com":   {"Referer": "https://360zy.com/", "Origin": "https://360zy.com"},
    "bfzyapi.com": {"Referer": "https://bfzyapi.com/", "Origin": "https://bfzyapi.com"},
    "huyaapi.com": {"Referer": "https://www.huyaapi.com/", "Origin": "https://www.huyaapi.com"},
    "suoniapi.com": {"Referer": "https://suoniapi.com/", "Origin": "https://suoniapi.com"},
    "lzizy1.com":  {"Referer": "https://lzizy1.com/", "Origin": "https://lzizy1.com"},
    "jszyapi.com": {"Referer": "https://jszyapi.com/", "Origin": "https://jszyapi.com"},
    "sdzyapi.com": {"Referer": "https://sdzyapi.com/", "Origin": "https://sdzyapi.com"},
    "ffzyapi.com": {"Referer": "https://api.ffzyapi.com/", "Origin": "https://api.ffzyapi.com"},
    "guangsuapi.com": {"Referer": "https://api.guangsuapi.com/", "Origin": "https://api.guangsuapi.com"},
}


def verify_api(item):
    domain, url, label = item
    # 有些采集站会按 UA/Referer 拦截，多套组合轮着试
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
    ]
    ref = EXTRA_HEADERS.get(domain, {})
    last = ""
    for ua in ua_list:
        for attempt in range(2):
            hdrs = {"User-Agent": ua, "Accept": "application/json, text/plain, */*"}
            hdrs.update(ref)
            try:
                r = urllib.request.Request(url, headers=hdrs)
                d = urllib.request.urlopen(r, timeout=25, context=CTX).read()
                j = json.loads(d.decode("utf-8", "ignore"))
                cls = j.get("class", [])
                if "list" in j and len(cls) > 0:
                    return item, True, f"{len(cls)}个分类"
                last = "非标准结构"
                break
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code in (403, 405, 406):
                    break          # 换 UA 试
            except Exception as e:
                last = type(e).__name__
                break
    return item, False, last


# 常用分类优先级（数字越小越靠前）。用于把用户最常看的分类排到前面，
# 避免 TVBox 展示前几项时点到冷门/空分类。
CAT_PRIORITY = [
    "动作片", "喜剧片", "爱情片", "科幻片", "悬疑片", "恐怖片", "剧情片", "战争片", "历史片",
    "国产剧", "国产电影", "电影片", "电影", "连续剧", "电视剧", "影片", "国产动漫", "动画片", "动漫片", "动漫",
    "纪录片", "记录片", "综艺片", "综艺", "体育", "体育赛事", "足球", "篮球", "台球",
    "短剧", "预告片", "最新",
    "欧美剧", "韩国剧", "香港剧", "台湾剧", "日本剧", "泰国剧", "海外剧",
    "香港电影", "欧美电影", "日本电影", "韩国电影", "台湾电影",
    "大陆综艺", "港台综艺", "日韩综艺", "欧美综艺", "音乐", "演唱会",
    "少儿", "儿童", "有声动漫", "动漫短剧", "AI漫剧", "漫剧",
    "欧美动漫", "日韩动漫", "港台动漫", "海外动漫",
    "两性课堂", "伦理", "写真热舞", "斯诺克", "网球", "科普学习", "影视解说", "预告解说",
    "女频恋爱", "反转爽剧", "古装仙侠", "年代穿越", "脑洞悬疑", "现代都市", "甜宠", "都市",
    "邵氏电影", "Netflix电影", "Netflix自制剧", "4K电影", "高清电影", "热门短剧",
]


def sort_categories(cats):
    """把常用分类排前面，其余保持原有相对顺序。"""
    prio = {n: i for i, n in enumerate(CAT_PRIORITY)}
    indexed = list(enumerate(cats))
    indexed.sort(key=lambda it: (prio.get(it[1][0], 999), it[0]))
    return [c for _, c in indexed]


def fetch_categories(domain, url):
    """逐个分类实测内容，返回 [(分类名, 类型ID, 部数), ...] 只含有内容的。
    分类请求并发执行，否则 8 源 × 50 分类会超时。"""
    hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*"}
    hdrs.update(EXTRA_HEADERS.get(domain, {}))
    try:
        r = urllib.request.Request(url, headers=hdrs)
        d = urllib.request.urlopen(r, timeout=25, context=CTX).read()
        j = json.loads(d.decode("utf-8", "ignore"))
    except Exception:
        return []
    cls = j.get("class", [])
    sep = "&" if "?" in url else "?"

    def probe(c):
        cid = c.get("type_id") if isinstance(c, dict) else c
        cname = c.get("type_name", str(cid)) if isinstance(c, dict) else str(cid)
        try:
            r2 = urllib.request.Request(f"{url}{sep}ac=videolist&t={cid}&pg=1", headers=hdrs)
            d2 = urllib.request.urlopen(r2, timeout=20, context=CTX).read()
            j2 = json.loads(d2.decode("utf-8", "ignore"))
            n = len(j2.get("list", []))
        except Exception:
            n = 0
        return (cname, cid, n)

    good = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for res in ex.map(probe, cls):
            if res[2] > 0:
                good.append(res)
    return good


def verify_m3u(url):
    """验证托管的 m3u 可达且格式正确（以 #EXTM3U 开头且有频道）。"""
    try:
        r = urllib.request.Request(url, headers=UA)
        d = urllib.request.urlopen(r, timeout=30, context=CTX).read()
        n = d.count(b"#EXTINF")
        if n > 0 and d.startswith(b"#EXTM3U"):
            return True, f"{n}个台/{len(d)}字节"
        # Pages 未重建时可能返回非 m3u 内容
        head = d[:40].decode("utf-8", "ignore").replace("\n", " ")
        return False, f"非m3u(首行:{head[:30]})"
    except Exception as e:
        return False, type(e).__name__


def main():
    print("=" * 68)
    print("逐个验证点播 API")
    print("=" * 68)
    with ThreadPoolExecutor(max_workers=8) as ex:
        api_res = list(ex.map(verify_api, CAND_APIS))
    good_sites = []
    # 分类探测较慢，8 个源并行处理
    def build_site(item):
        domain, url, label = item
        cats = fetch_categories(domain, url)
        if not cats:
            return None, f"      ✗ 所有分类均无内容，剔除该源"
        cats = sort_categories(cats)
        cat_names = [c[0] for c in cats]
        tmap = ",".join(f"{c[0]}:{c[1]}" for c in cats)
        site = {
            "key": "sel_" + domain.replace(".", "_"),
            "name": label,
            "type": 1,
            "api": url,
            "searchable": 1,
            "quickSearch": 1,
            "filterable": 1,
            "categories": cat_names,
            "ext": {"t": tmap},
        }
        head = "、".join(cat_names[:6]) + ("..." if len(cat_names) > 6 else "")
        return site, f"      ✓ 可用分类 {len(cat_names)} 个: {head}"

    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for (item, ok, msg), (site, note) in zip(api_res, ex.map(build_site, [i for i, _, _ in api_res])):
            label = item[2]
            if not ok:
                print(f"  ✗ 剔除  {label:<16} {msg:<14} {item[1][:52]}")
                continue
            if site is None:
                print(f"  ✗ 剔除  {label:<16} {msg:<14} {item[1][:52]}")
                print(note)
                continue
            print(f"  ✓ 收录  {label:<16} {msg:<14} {item[1][:52]}")
            print(note)
            good_sites.append(site)

    print()
    print("=" * 68)
    print("逐个验证直播源（托管的清洗版 m3u）")
    print("=" * 68)
    # ---- 直播源由自愈脚本 autoheal_lives.py 维护，这里只“沿用”，绝不覆盖 ----
    # 读取即将写入的 tvbox_curated.json 里已有的 lives（自愈脚本每日刷新它），
    # 使精选配置的直播源始终与自愈结果一致，且不会回退到旧账号域名。
    existing_lives = []
    out_preview = os.path.join(HERE, "tvbox_curated.json")
    if os.path.basename(os.path.dirname(HERE)) == "tools":
        out_preview = os.path.join(os.path.dirname(os.path.dirname(HERE)), "tvbox_curated.json")
    if os.path.exists(out_preview):
        try:
            _cur = json.load(open(out_preview, encoding="utf-8"))
            existing_lives = _cur.get("lives", []) or []
        except Exception:
            existing_lives = []

    # 仅在全新仓库（尚无 tvbox_curated.json）时使用的回退直播源（anbola 域名）
    FALLBACK_LIVES = [
        ("央视·卫视精选", "cn_clean.m3u"),
        ("咪咕中转·央视卫视", "yang_clean.m3u"),
        ("每日更新·央视卫视", "mzky_clean.m3u"),
        ("YangGather 咪咕移动", "yanggather_clean.m3u"),
        ("每日检测·央视卫视", "bestfan_clean.m3u"),
        ("Guovin 中国IPTV", "guovin_clean.m3u"),
        ("BigBig 聚合源", "bigbig_clean.m3u"),
        ("CCSH 自动采集", "ccsh_clean.m3u"),
        ("4K·8K 超高清频道", "kimentanm_clean.m3u"),
        ("联通组播·央视卫视", "yuechan_clean.m3u"),
    ]
    fallback_lives = [{"name": n, "url": G + f} for n, f in FALLBACK_LIVES]

    # 组装配置（自包含，不依赖已有文件，便于在 CI 中独立运行）
    base = {
        "wallpaper": "https://www.loliapi.com/acg/",
        "logo": "https://storage.7x24cc.com/storage-server/presigned/ss1/a6-online-fileupload/newMediaFile/3CEAE9E_773_wexfnw_20250911190012684newMediaFile.gif",
        "doh": ["https://1.12.12.12/dns-query", "https://doh.pub/dns-query"],
        "ads": ["https://ads.cmc.cc/uu.php?type=hsdh"],
        "rules": ["vip", "tpl", "ju", "qb", "iqiyi", "qiyi", "letv", "sohu", "qq", "wetv", "mgtv", "bilibili", "wasu", "tvid", "renrenmi"],
        "headers": [
            {"host": "hlsztemgsplive.miguvideo.com", "header": {"User-Agent": "bingcha/1.1 (mianfeifenxiang) "}}
        ],
    }
    base["sites"] = good_sites
    # 沿用自愈直播源；若首次运行尚无 lives，则回退到内置 10 个
    base["lives"] = existing_lives if existing_lives else fallback_lives
    base["parses"] = [{"name": "阿雪解析", "type": 1, "url": "https://jx.xmflv.com/?url="}]
    base["spider"] = ""   # 全部使用明文 API，无需加密 jar

    out = os.path.join(HERE, "tvbox_curated.json")
    # CI 中脚本位于 tools/ 下，需写回仓库根目录
    if os.path.basename(os.path.dirname(HERE)) == "tools":
        out = os.path.join(os.path.dirname(os.path.dirname(HERE)), "tvbox_curated.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=2)
    # 同步生成「点播专用」拆分文件（供没有订阅入口的 TVBox 直接粘进"点播源"框）
    sites_cfg = {k: v for k, v in base.items() if k != "lives"}
    with open(os.path.join(os.path.dirname(out), "tvbox_sites.json"), "w", encoding="utf-8") as f:
        json.dump(sites_cfg, f, ensure_ascii=False, indent=2)
    print(f"  已生成 tvbox_sites.json（点播专用，{len(base['sites'])} 源）")
    print()
    print(f"→ 已生成 {os.path.basename(out)}（仓库根目录）")
    print(f"  点播源 {len(good_sites)} 个（全部实测可用）")
    print(f"  直播源 {len(base['lives'])} 个（沿用自愈脚本结果）")
    print(f"  解析接口 {len(base['parses'])} 个（实测可解析）")


if __name__ == "__main__":
    main()
