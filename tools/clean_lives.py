#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV 直播源全量清洗器
  1) 台名：拼音/英文 -> 汉字（央视/卫视/地方台）
  2) 分辨率：统一成 〔标清/高清/2K/4K/8K〕
  3) 分组：英文/繁体 -> 中文分类，细化且准确
输出 lives/*.m3u，供 GitHub Pages 托管。
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIVES = os.path.join(HERE, "lives")
os.makedirs(LIVES, exist_ok=True)

# 繁体 -> 简体（可选依赖）
try:
    from opencc import OpenCC
    _cc = OpenCC('t2s')
    def t2s(s):
        return _cc.convert(s)
except Exception:
    def t2s(s):
        return s

# ============ 央视/教育台标准名（编号 -> (标准名, 分类)）============
CCTV_STD = {
    1:  ("央视一套·综合",       "央视·综合"),
    2:  ("央视二套·财经",       "央视·财经"),
    3:  ("央视三套·综艺",       "央视·综艺"),
    4:  ("央视四套·中文国际",   "央视·国际"),
    5:  ("央视五套·体育",       "央视·体育"),
    6:  ("央视六套·电影",       "央视·电影"),
    7:  ("央视七套·国防军事",   "央视·军事"),
    8:  ("央视八套·电视剧",     "央视·电视剧"),
    9:  ("央视九套·纪录",       "央视·纪录"),
    10: ("央视十套·科教",       "央视·科教"),
    11: ("央视十一套·戏曲",     "央视·戏曲"),
    12: ("央视十二套·社会与法", "央视·法治"),
    13: ("央视十三套·新闻",     "央视·新闻"),
    14: ("央视十四套·少儿",     "央视·少儿"),
    15: ("央视十五套·音乐",     "央视·音乐"),
    16: ("央视十六套·奥林匹克", "央视·奥运"),
    17: ("央视十七套·农业农村", "央视·农业"),
}
CETV_STD = {1: "中国教育台·一套", 2: "中国教育台·二套", 3: "中国教育台·三套", 4: "中国教育台·四套"}

# ============ 英文/拼音台名对照表（iptv-org 等）============
TR = {
    "CCTV+ 1": "央视+1", "CCTV+ 2": "央视+2",
    "CCTV-Billiards": "央视·台球", "CCTV-Culture of Quality": "央视·高清频道",
    "CCTV-Golf & Tennis": "央视·高尔夫网球", "CCTV-Health": "央视·卫生健康",
    "CCTV-Nostalgia Theater": "央视·怀旧剧场", "CCTV-Storm Football": "央视·风云足球",
    "CCTV-Storm Music": "央视·风云音乐", "CCTV-Storm Theater": "央视·风云剧场",
    "CCTV-The First Theater": "央视·第一剧场", "CCTV-Weapon & Technology": "央视·兵器科技",
    "CCTV-Women's Fashion": "央视·女性时尚", "CCTV-World Geography": "央视·世界地理",
    "CETV-1": "中国教育台·一套", "CETV-2": "中国教育台·二套",
    "CETV-3": "中国教育台·三套", "CETV-4": "中国教育台·四套",
    "Anhui TV": "安徽卫视", "Beijing Satellite TV": "北京卫视", "Guangdong Satellite TV": "广东卫视",
    "Guangxi Variety & Travel Channel": "广西综艺旅游频道", "Guizhou TV": "贵州卫视",
    "Hebei TV": "河北卫视", "Heilongjiang TV": "黑龙江卫视", "Hunan TV": "湖南卫视",
    "Jiangsu Satellite TV": "江苏卫视", "Jiangxi TV": "江西卫视", "Liaoning TV": "辽宁卫视",
    "Ningxia Satellite Channel": "宁夏卫视", "Qinghai TV": "青海卫视",
    "Shandong Satellite TV": "山东卫视", "Shandong TV": "山东卫视", "Shenzhen Satellite TV": "深圳卫视",
    "Sichuan Satellite TV": "四川卫视", "Tianjin TV": "天津卫视", "Yunnan Satellite TV": "云南卫视",
    "Zhejiang Satellite TV": "浙江卫视", "Zhejiang International Channel": "浙江国际频道",
    "Dragon TV International": "东方卫视·国际版", "Nei Monggol TV": "内蒙古卫视",
    "Nei Monggol TV 2 Mongolian Culture Channel": "内蒙古卫视2·蒙古语文化",
    "Xizang TV Chinese": "西藏卫视·中文", "Xizang TV Tibetan": "西藏卫视·藏语",
    "Kangba TV": "康巴卫视", "Yanbian Satellite TV": "延边卫视",
    "Xinjiang TV 1": "新疆卫视1", "Xinjiang TV 2": "新疆卫视2", "Xinjiang TV 3": "新疆卫视3",
    "Xinjiang TV 5": "新疆卫视5", "Xinjiang TV 8": "新疆卫视8",
    "ABN China": "ABN中国频道", "Ando TV": "安多电视台", "Angel TV Chinese": "天使电视·中文",
    "Anshun Comprehensive News Channel": "安顺综合新闻频道", "BRTV Kaku Childrens Channel": "北京卡酷少儿频道",
    "Baicheng TV": "白城电视台", "Bingtuan Satellite TV": "兵团卫视", "Bread TV": "面包电视台",
    "Chaozhou Public Channel": "潮州公共频道", "Chifeng Comprehensive News Chanel": "赤峰综合新闻频道",
    "China Weather Channel": "中国天气频道", "Chuxiong News Channel": "楚雄新闻频道",
    "Chuzhou News Channel": "滁州新闻频道", "Chuzhou Public Channel": "滁州公共频道",
    "Chuzhou Science & Education Channel": "滁州科教频道", "Documentary Humanities Channel": "纪录人文频道",
    "Dongguan Comprehensive News Channel": "东莞综合新闻频道", "Dunhuang TV": "敦煌电视台",
    "Fengshang Shopping Channel": "风尚购物频道", "Fujian Comprehensive Channel": "福建综合频道",
    "Golden Eagle Cartoon": "金鹰卡通", "Guangzhou TV": "广州电视台",
    "Harbin Comprehensive News Channel": "哈尔滨综合新闻频道", "Harbin Movie Channel": "哈尔滨电影频道",
    "Hebi News Channel": "鹤壁新闻频道", "Hezheng TV": "和政电视台", "High Channel TV": "高清频道",
    "HomePlus": "合家购物", "Hunan Economy Channel": "湖南经济频道", "Hunan News Channel": "湖南新闻频道",
    "Hunan Politics & Law Channel": "湖南政法频道", "Hunan Womens Channel": "湖南女性频道",
    "Jiangsu City Channel": "江苏城市频道", "Jiangsu Educational Channel": "江苏教育频道",
    "Jiangsu Movie Channel": "江苏电影频道", "Jiangsu Public & News Channel": "江苏公共新闻频道",
    "Jiangsu Sports & Leisure Channel": "江苏体育休闲频道", "Jiangsu Variety Channel": "江苏综艺频道",
    "Jiangxi Children's Channel": "江西少儿频道", "Jiangxi City Channel": "江西南昌频道",
    "Jiangxi Economy & Life Channel": "江西经济生活频道", "Jiangxi Movie Channel": "江西电影频道",
    "Jiangxi Public & Agriculture Channel": "江西公共农业频道", "Jilin City Channel": "吉林市频道",
    "Jilin Lifestyle Channel": "吉林生活频道", "Jilin Movie Channel": "吉林电影频道",
    "Jilin Rural Channel": "吉林乡村频道", "Jiuquan TV News Comprehensive Channel": "酒泉新闻综合频道",
    "Lanzhou Comprehensive News Channel": "兰州综合新闻频道", "Lanzhou Culture & Tourism Channel": "兰州文旅频道",
    "Liangshan TV": "凉山电视台", "Nanchang News & Generalist Channel": "南昌新闻综合频道",
    "Pingxiang TV News Channel": "萍乡电视新闻频道",
    "QTV-1": "青岛电视台1套", "QTV-2": "青岛电视台2套", "QTV-3": "青岛电视台3套",
    "QTV-4": "青岛电视台4套", "QTV-5": "青岛电视台5套", "QTV-6": "青岛电视台6套",
    "Shandong TV Agricultural Science Channel": "山东电视农科频道",
    "Shandong TV Children's Channel": "山东电视少儿频道",
    "Shandong TV Life Channel": "山东电视生活频道", "Shandong TV Qilu Channel": "山东电视齐鲁频道",
    "Shandong TV Sports Channel": "山东电视体育频道", "Shandong TV Variety Channel": "山东电视综艺频道",
    "Sichuan TV Women and Children Channel": "四川电视妇女儿童频道", "Siping TV": "四平电视台",
    "TV BRICS Chinese": "TV BRICS中国频道", "Tonghua TV": "通化电视台", "VoA TV China": "美国之音中国频道",
    "Xi'an Business Information Channel": "西安商务资讯频道", "Xi'an Silk Road Channel": "西安丝路频道",
    "Xuzhou Economic Life Channel": "徐州经济生活频道", "You Man Cartoon Channel": "优漫卡通频道",
    "CHC Action": "CHC动作电影", "CHC Home Theater": "CHC家庭影院",
    "CND Film Discovery Channel": "CND电影发现频道", "CND Film Middle School Channel": "CND电影中学频道",
    "BabyFirst": "宝贝第一台", "8TV": "八频道",
    # 频道品牌缩写 -> 中文全称
    "CHC动作电影": "央视电影·动作电影", "CHC家庭影院": "央视电影·家庭影院",
    "CHC影迷电影": "央视电影·影迷电影",
    "CND电影发现频道": "中国教育电视台·电影发现", "CND电影中学频道": "中国教育电视台·电影中学",
    "TV BRICS中国频道": "金砖国家·中国频道", "ABN中国频道": "亚洲广播新闻网·中国频道",
    "BTV卡酷": "北京卫视·卡酷少儿", "TVB星河": "香港无线·星河频道",
    "IPTV热播剧场": "网络电视·热播剧场",
    # 国际/港澳台主流品牌 -> 中文
    "HBO": "HBO 好莱坞", "HBO Family": "HBO家庭频道", "HBO Hits": "HBOHits剧场",
    "HBO Signature": "HBO Signature  Signature",
    "CINEMAX": "Cinemax 动作电影", "Discovery": "探索频道·Discovery",
    "Eurosport 1": "欧洲体育1", "Eurosport 2": "欧洲体育2",
    "Eurosport 3": "欧洲体育3", "Eurosport 4": "欧洲体育4",
    "TVB1": "无线电视·翡翠台", "TVB Drama": "无线电视·剧集台", "TVB Plus": "无线电视·加映台",
    "TVB 功夫台": "无线电视·功夫台", "TVB 星河台": "无线电视·星河台",
    "TVBS亚洲": "TVBS亚洲台", "ViuTV": "ViuTV 无线电视", "Viutv": "ViuTV 无线电视",
    "ViuTVsix": "ViuTVsix 六台", "RTHK 31": "港台电视31", "RTHK 32": "港台电视32",
    "RTHK 33": "港台电视33", "RTHK31": "港台电视31", "RTHK32": "港台电视32",
    "RTHK33": "港台电视33", "Now新闻台": "Now新闻台", "Now直播台": "Now直播台",
    "Now财经台": "Now财经台", "Now Sports 精选": "Now Sports 体育精选",
    "HOY TV": "HOY TV 电视", "HOY 国际财经台": "HOY国际财经台", "HOY 资讯台": "HOY资讯台",
    "J2": "J2 电视", "Astro AOD": "Astro 资讯台", "Astro 欢喜台": "Astro 欢喜台",
    "CATCHPLAY 电影": "Catchplay 电影", "BBC Earth": "BBC地球频道", "BBC Lifestyle": "BBC生活频道",
    "DayStar": "DayStar 频道", "AM864": "AM864 电台", "CINEMAX 电影": "Cinemax 电影",
    "SPOTV": "SPOTV 体育", "SPOTV 2": "SPOTV 2 体育", "MCE 我的欧洲电影": "MCE我的欧洲电影",
    "amc电影台": "AMC电影台", "iQIYI": "爱奇艺", "DAZN 1": "DAZN体育1", "DAZN 2": "DAZN体育2",
    "Love Nature": "自然纪录片频道", "CinemaWorld": "CinemaWorld 电影世界",
    "DreamWorks 梦工厂动画": "梦工厂动画频道", "Channel 5": "第五频道", "Channel 8": "第八频道",
    "Channel U": "U频道", "CN卡通": "中国教育电视台·卡通", "IPTV经典电影": "网络电视·经典电影",
    "PopC": "PopC 频道", "RTHK 港台": "港台电视", "Hub Sports 1": "Hub体育1",
    "Hub Sports 2": "Hub体育2", "Hub Sports 3": "Hub体育3", "Hub Sports 4": "Hub体育4",
    "Hub Sports 5": "Hub体育5", "Hub Sports 6": "Hub体育6", "Hub Sports 7": "Hub体育7",
    "Hub Sports 8": "Hub体育8",
    "Hub Premier 1": "Hub Premier 1 频道", "Hub Premier 2 UHD": "Hub Premier 2 超高清",
    "Hub Premier 3": "Hub Premier 3 频道", "Hub Premier 4": "Hub Premier 4 频道",
    "Hub Premier 5": "Hub Premier 5 频道", "Hub Premier 6": "Hub Premier 6 频道",
    "TNT Sport 1": "TNT体育1", "TNT Sport 2": "TNT体育2", "TNT Sport 3": "TNT体育3",
    "TNT Sport 4": "TNT体育4", "TSN 1": "TSN体育1", "TSN 2": "TSN体育2",
    "TSN 3": "TSN体育3", "TSN 4": "TSN体育4", "TSN 5": "TSN体育5",
    "beIN Sports 1": "beIN体育1", "beIN Sports 2": "beIN体育2", "beIN Sports 3": "beIN体育3",
    "beIN Sports 4": "beIN体育4", "beIN Sports 5": "beIN体育5",
    "FIGHT SPORTS": "格斗体育频道",
}

# ============ 统一分类体系（所有源共用，避免分组过碎）============
# 顺序即 TVBox 里的显示顺序：央视永远第一
CAT_ORDER = ["央视", "4K·8K", "卫视", "地方台", "影视剧场", "体育", "少儿动漫",
             "综艺音乐", "资讯纪实", "购物生活", "港澳台", "国际", "其他"]

# 各源原始分组 -> 统一大类
GROUP_MAP = {
    # --- 央视系：合并成一个"央视"，不再细分 ---
    "央视": "央视", "央视频道": "央视", "央视IPV4": "央视",
    "央视·综合": "央视", "央视·新闻": "央视", "央视·综艺": "央视", "央视·电视剧": "央视",
    "央视·电影": "央视", "央视·体育": "央视", "央视·科教": "央视", "央视·少儿": "央视",
    "央视·纪录": "央视", "央视·戏曲": "央视", "央视·军事": "央视", "央视·法治": "央视",
    "央视·农业": "央视", "央视·奥运": "央视", "央视·国际": "央视", "央视·超高清": "央视",
    "央视·高清": "央视", "央视·其他": "央视",
    "教育": "央视",
    "中国教育台·一套": "央视", "中国教育台·二套": "央视", "中国教育台·三套": "央视",
    "中国教育台·四套": "央视",
    "历年春晚": "央视",
    # --- 4K/8K 独立 ---
    "4K·8K": "4K·8K", "4K8K频道": "4K·8K", "高清频道": "4K·8K",
    # --- 卫视 ---
    "卫视": "卫视", "卫视频道": "卫视", "卫视IPV4": "卫视",
    # --- 地方台（Guovin 按省份、mzky 地方频道等）---
    "地方": "地方台", "地方频道": "地方台", "其他频道": "地方台", "数字频道": "地方台",
    # --- 影视/剧场 ---
    "影视": "影视剧场", "影视频道": "影视剧场", "电影": "影视剧场", "Movies": "影视剧场",
    "Classic": "影视剧场", "家庭影院": "影视剧场", "剧集": "影视剧场",
    "剧场": "影视剧场", "热播剧场": "影视剧场", "经典电影": "影视剧场", "IPTV经典电影": "影视剧场",
    "CND电影中学频道": "影视剧场", "CND电影发现频道": "影视剧场",
    "网络电视·经典电影": "影视剧场",
    # --- 体育 ---
    "体育": "体育", "体育频道": "体育", "Sports": "体育", "赛事": "体育",
    # --- 少儿/动漫 ---
    "少儿": "少儿动漫", "少儿动画": "少儿动漫", "卡通": "少儿动漫", "卡通频道": "少儿动漫",
    "Kids": "少儿动漫", "Animation": "少儿动漫", "金鹰卡通": "少儿动漫",
    "优漫卡通频道": "少儿动漫", "中国教育电视台·卡通": "少儿动漫",
    # --- 综艺/音乐 ---
    "综艺": "综艺音乐", "综艺频道": "综艺音乐", "Entertainment": "综艺音乐",
    "Variety": "综艺音乐", "娱乐综艺": "综艺音乐", "Music": "综艺音乐",
    "MTV综合台": "综艺音乐", "央视·综艺": "央视",
    # --- 资讯/纪实 ---
    "新闻": "资讯纪实", "资讯": "资讯纪实", "News": "资讯纪实",
    "Documentary": "资讯纪实", "纪实": "资讯纪实", "纪实科教": "资讯纪实",
    "求索纪录": "资讯纪实", "金鹰纪实": "资讯纪实", "中国天气": "资讯纪实",
    "中国交通": "资讯纪实", "证券服务": "资讯纪实", "Weather": "资讯纪实",
    # --- 购物/生活 ---
    "生活": "购物生活", "Lifestyle": "购物生活", "综合": "购物生活",
    "General": "购物生活", "购物": "购物生活", "Shop": "购物生活",
    "风尚购物频道": "购物生活", "合家购物": "购物生活", "生活休闲": "购物生活",
    # --- 港澳台 ---
    "港澳台": "港澳台", "香港": "港澳台", "台湾": "港澳台", "港澳台频道": "港澳台",
    "咪咕中转·中国": "央视", "咪咕中转·咪视": "综艺音乐", "咪咕中转·台湾": "港澳台",
    "咪咕中转·体育": "体育", "咪咕中转·综合": "资讯纪实",
    "温馨提示": "其他",
    # --- 国际 ---
    "国际": "国际", "CGTN": "国际", "China International Television": "国际",
    # --- 其它 ---
    "宗教": "其他", "Religious": "其他", "科学": "其他", "Science": "其他",
    "Education": "其他", "Lifestyle;Science": "其他", "生活;科学": "其他",
    "Weather;Outdoor": "资讯纪实", "自然": "其他", "Travel": "其他",
    "Culture": "其他", "文化": "其他", "法治": "资讯纪实", "Legislative": "资讯纪实",
    "家庭": "其他", "Family": "其他", "教育;生活;科学": "其他", "教育;户外": "其他",
    "Outdoor": "其他", "Undefined": "其他", "其他": "其他",
    "通用": "其他", "高清": "其他",
    # --- Guovin 专用（去 emoji 后）---
    "卫视频道": "卫视", "央视频道": "央视", "央视付费频道": "央视",
    "其他频道": "地方台", "地方频道": "地方台", "数字频道": "地方台",
    "电影频道": "影视剧场", "影视频道": "影视剧场", "剧场": "影视剧场",
    "经典剧场": "影视剧场", "高清剧场": "影视剧场", "热播剧场": "影视剧场",
    "体育频道": "体育", "动画频道": "少儿动漫", "卡通频道": "少儿动漫",
    "少儿频道": "少儿动漫", "音乐频道": "综艺音乐", "综艺频道": "综艺音乐",
    "新闻频道": "资讯纪实", "纪录频道": "资讯纪实", "纪实频道": "资讯纪实",
    "教育频道": "央视", "科教频道": "央视", "生活频道": "购物生活",
    "生活时尚": "购物生活", "购物频道": "购物生活", "美食频道": "购物生活",
    "港·澳·台": "港澳台", "港澳台频道": "港澳台", "国际频道": "国际",
    "游戏频道": "其他", "游戏": "其他", "宗教频道": "其他",
    "4K频道": "4K·8K", "8K频道": "4K·8K", "超高清频道": "4K·8K",
    "历年春晚": "央视", "春晚": "央视",
}

# 常见地方台前缀 -> 地方台（Guovin 省份频道等）
_PROVINCES = [
    "浙江", "河南", "江苏", "广东", "河北", "四川", "上海", "福建", "湖北", "安徽",
    "黑龙江", "湖南", "广西", "海南", "山东", "北京", "青海", "陕西", "甘肃", "新疆",
    "云南", "辽宁", "山西", "天津", "内蒙古", "吉林", "重庆", "贵州", "宁夏", "西藏",
    "深圳", "厦门", "青岛", "大连", "苏州", "杭州", "宁波", "温州", "无锡", "济南",
    "长春", "哈尔滨", "石家庄", "太原", "福州", "南昌", "昆明", "贵阳", "兰州", "西宁",
    "银川", "乌鲁木齐", "呼和浩特", "拉萨", "海口", "三沙", "台北", "高雄",
]

DROP_NAME = re.compile(r'^\d{4}-\d{2}-\d{2}[_ ]\d{2}:\d{2}:\d{2}$')
DROP_GROUP = {"更新时间"}

PAREN = re.compile(r'\(([^)]*)\)')
NOTE = re.compile(r'\[[^\]]*\]')
INLINE_HDSD = re.compile(r'\s+\b(HD|SD)\b', re.I)
INLINE_RES = re.compile(r'\s+\b(8K|4K|2K|2160p|1440p|1080p|1080i|960p|900p|720p|576p|576i|540p|600p|480p|406p|404p|400p|180p|HDTV)\b', re.I)


def map_res(tok):
    if re.search(r'8K|4320p', tok, re.I): return '8K'
    if re.search(r'4K|2160p', tok, re.I): return '4K'
    if re.search(r'2K|1440p', tok, re.I): return '2K'
    if re.search(r'1080p|1080i|960p|900p', tok, re.I): return '高清'
    if re.search(r'720p', tok, re.I): return '高清'
    if re.search(r'576p|576i|540p|600p|480p|406p|404p|400p|180p', tok, re.I): return '标清'
    if re.search(r'\bHD\b', tok, re.I): return '高清'
    if re.search(r'\bSD\b', tok, re.I): return '标清'
    return ''


def detect_and_strip(name):
    """返回 (基础名, 分辨率标签)"""
    res = ''
    work = t2s(name)          # 先转简体，避免繁体字残留在标记/后缀里
    # 去掉「Relay」「Juli」等来源标记后缀
    work = re.sub(r'[「『]\s*(Relay|Juli|relay|juli)\s*[」』]\s*$', '', work)
    # 去掉「ofiii」「WebVTT字幕」「字幕」等技术标记后缀
    work = re.sub(r'[「『]\s*(ofiii|WebVTT字幕|字幕|官方)\s*[」』]\s*$', '', work)
    m = PAREN.search(work)
    if m:
        r = map_res(m.group(1))
        if r:
            res = r
        work = work[:m.start()] + work[m.end():]
    work = NOTE.sub('', work)
    work = INLINE_HDSD.sub('', work)
    work = INLINE_RES.sub('', work)
    base = re.sub(r'\s+', ' ', work).strip()
    if not res:
        if re.search(r'\bHD\b', name, re.I) and not re.search(r'[248]K', name, re.I):
            res = '高清'
        elif re.search(r'\bSD\b', name, re.I):
            res = '标清'
    return base, res


RE_CCTV = re.compile(r'^CCTV[\s\-_]?(\d{1,2})(?![0-9K])', re.I)
RE_CCTV_K = re.compile(r'^CCTV[\s\-_]?(4K|8K|2K)\b', re.I)
RE_CCTV_PLAIN = re.compile(r'^CCTV\s*(超高清|超高清\s*频道)?$', re.I)
RE_CCTV_PLUS = re.compile(r'^CCTV\+\s*(\d)$', re.I)
RE_CETV = re.compile(r'^CETV[\s\-_]?(\d)$', re.I)
RE_CGTN = re.compile(r'^CGTN[\s\-_]?(\S*)$', re.I)
CGTN_LANG = {
    "": "中国国际电视台", "俄语": "中国国际电视台·俄语", "法语": "中国国际电视台·法语",
    "纪录": "中国国际电视台·纪录", "英语": "中国国际电视台·英语", "西语": "中国国际电视台·西班牙语",
    "西班牙语": "中国国际电视台·西班牙语", "阿语": "中国国际电视台·阿拉伯语",
    "阿拉伯语": "中国国际电视台·阿拉伯语", "中文": "中国国际电视台·中文",
}


def translate_name(base):
    """把基础台名翻成中文；返回 (中文名, 分类 或 None)
    分类只做粗分：央视 / 4K·8K / 卫视，其余靠 group-title 归类。"""
    s = base

    m = RE_CCTV_PLUS.match(s)
    if m:
        return f"央视+{m.group(1)}", "央视"

    # CCTV 4K / 8K / 2K（必须在普通数字之前匹配）
    m = RE_CCTV_K.match(s)
    if m:
        k = m.group(1).upper()
        label = {'4K': "央视·4K超高清", '8K': "央视·8K超高清", '2K': "央视·2K超高清"}[k]
        return label, "4K·8K" if k in ('4K', '8K') else "央视"

    # 单独一个 CCTV（yang 的 "CCTV 超高清"）
    if RE_CCTV_PLAIN.match(s):
        if '超高清' in s:
            return "央视·超高清", "4K·8K"
        return "央视一套·综合", "央视"

    m = RE_CETV.match(s)
    if m:
        n = int(m.group(1))
        return CETV_STD.get(n, f"中国教育台·{n}套"), "央视"

    m = RE_CGTN.match(s)
    if m:
        key = t2s(m.group(1))
        return CGTN_LANG.get(key, "中国国际电视台"), "国际"

    m = RE_CCTV.match(s)
    if m:
        num = int(m.group(1))
        tail = s[m.end():]
        if tail.lstrip().startswith('+') or re.match(r'^\s*\+', tail):
            return "央视·体育赛事", "央视"
        std, cat = CCTV_STD.get(num, (None, None))
        if std:
            return std, "央视"
        return f"央视{num}套", "央视"

    if s in TR:
        return TR[s], None

    # 名称里带 4K/8K 的卫视（如"东方卫视4K"）
    if re.search(r'[248]K', s, re.I):
        return s, "4K·8K"
    # 名称里带"卫视"
    if '卫视' in s:
        return s, "卫视"
    return s, None


def process_name(name):
    m = re.search(r'([一-龥])(4k|8k|2k)\b', name, re.I)
    if m:
        name = name[:m.start(2)] + m.group(2).upper() + name[m.end(2):]
    base, res = detect_and_strip(name)
    zh, cat = translate_name(base)

    if '8K' in zh: res = '8K'
    elif '4K' in zh: res = '4K'
    elif '2K' in zh: res = '2K'
    if not res and m:
        res = m.group(2).upper()
    out = f"{zh}〔{res}〕" if res else zh
    return out, cat


def translate_group_name(raw):
    """原始 group-title -> 统一大类。支持多标签(A;B)与 •xxx「Relay」 形式。"""
    if not raw:
        return "其他"
    # 1) 拆多标签：取第一个能识别的
    if ';' in raw:
        parts = [translate_group_name(p) for p in raw.split(';')]
        parts = [p for p in parts if p and p != "其他"]
        return parts[0] if parts else "其他"
    # 2) 规范化：去首部 •、去 「…」 后缀、去空格、去 emoji 与装饰符号
    norm = raw.strip()
    norm = re.sub(r'^[•·\s]+', '', norm)
    norm = re.sub(r'[「『\[].*?[」』\]]\s*$', '', norm)
    # 去掉任意 emoji / 装饰符（☘️🏀🎬🌊💰🪁🎮🏛🎵 等，含变体选择符 U+FE0F）
    norm = re.sub(r'[\U0001F000-\U0001FAFF☀-➿️\U0001F1E6-\U0001F1FF\U00002700-\U000027BF\s]+', '', norm)
    norm = norm.strip()
    if not norm:
        return "其他"
    # 3) 繁体转简体后查表
    simp = t2s(norm)
    for key in (norm, simp):
        if key in GROUP_MAP:
            return GROUP_MAP[key]
    # 4) 省份/地方台前缀
    for p in _PROVINCES:
        if norm.startswith(p) or simp.startswith(p):
            return "地方台"
    # 5) 名字里含"卫视"
    if '卫视' in simp or '衛視' in norm:
        return "卫视"
    # 6) 名字里含"央视"/"CCTV"
    if '央视' in simp or '央視' in norm or norm.upper().startswith('CCTV'):
        return "央视"
    # 7) 4K/8K
    if '4K' in norm.upper() or '8K' in norm.upper():
        return "4K·8K"
    # 8) 兜底：繁体转简体，否则归"其他"
    if simp != norm and re.search(r'[一-鿿]', simp):
        return "其他"
    return "其他"


def clean_m3u(text, group_map=True):
    """清洗并按分类重排：央视 -> 4K·8K -> 卫视 -> 其它，保证央视在最前。"""
    lines = text.splitlines()

    # 0) 保留原始文件头（#EXTM3U 及其属性行）
    header = []
    for ln in lines:
        if ln.startswith('#EXTM3U'):
            header.append(ln)
        elif ln.startswith('#EXT-X-') and not header:
            header.append(ln)
        else:
            break

    # 1) 完整提取每个条目：EXTINF 行 + 中间附加行 + URL 行
    items = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith('#EXTINF'):
            i += 1
            continue
        j = i + 1
        extra = []
        while j < len(lines) and lines[j].startswith('#EXT') and not lines[j].startswith('#EXTINF'):
            extra.append(lines[j])
            j += 1
        if j < len(lines) and not lines[j].startswith('#EXTINF'):
            items.append((lines[i], extra, lines[j]))
            i = j + 1
        else:
            i += 1

    # 2) 逐条清洗
    final = []
    for ext, extra, url in items:
        idx = ext.rfind(',')
        if idx == -1:
            continue
        head, disp = ext[:idx], ext[idx+1:].strip()
        if DROP_NAME.match(disp):
            continue
        newdisp, ccat = process_name(disp)
        gm = re.search(r'group-title="([^"]*)"', head)
        grp = gm.group(1) if gm else ""
        if grp in DROP_GROUP:
            continue
        newgrp = translate_group_name(grp) if group_map else grp
        # 台名推断的分类优先级高于原始分组（央视台不管在哪个组都归央视）
        if ccat:
            newgrp = ccat
        if gm:
            head = head[:gm.start()] + f'group-title="{newgrp}"' + head[gm.end():]
        final.append((newgrp, head + ',' + newdisp, extra, url))

    # 3) 按分类顺序重排（央视最前）
    def cat_key(item):
        c = item[0]
        return CAT_ORDER.index(c) if c in CAT_ORDER else len(CAT_ORDER)
    final.sort(key=cat_key)

    result = []
    for h in header:
        result.append(h)
    for cat, ext, extra, url in final:
        result.append(ext)
        result.extend(extra)
        result.append(url)
    return '\n'.join(result) + '\n'


def main():
    jobs = [
        ("cn_raw.m3u",        "cn_clean.m3u",        True),
        ("guovin_raw.m3u",    "guovin_clean.m3u",    True),
        ("mzky_raw.m3u",      "mzky_clean.m3u",      True),
        ("yuechan_raw.m3u",   "yuechan_clean.m3u",   True),
        ("yang_raw.m3u",      "yang_clean.m3u",      True),
        ("kimentanm_raw.m3u", "kimentanm_clean.m3u", True),
    ]
    for src, dst, gm in jobs:
        p = os.path.join(HERE, src)
        if not os.path.exists(p):
            print(f"跳过 {src}（不存在）")
            continue
        with open(p, encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        out = clean_m3u(txt, group_map=gm)
        dp = os.path.join(LIVES, dst)
        with open(dp, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"{dst}: {out.count('#EXTINF')} 个台  ({len(out.encode('utf-8'))} 字节)")


if __name__ == "__main__":
    main()
