---
name: anbola-tvbox-maintainer
description: 维护 GitHub 仓库 anbola/tvbox（TVBox / MyTV 自维护「直播+点播」配置，陕西移动宽带优化版）。当用户要更新直播源、改点播采集站、部署到 GitHub、排查配置报错、或问「这个项目是干嘛的 / 连哪个仓库 / 怎么操作 / 之前发生了什么」时使用。内含当前架构快照、部署方式（含「本机 git 被墙 → 走 GitHub Contents API」）、本机网络限制、归档去重纪律、回退陷阱、已知坑。
---

# 项目：anbola/tvbox 自维护配置

> 本 SKILL 是「跨电脑记忆」：clone 仓库 `anbola/tvbox` 并在 WorkBuddy 打开，本文件会自动加载，
> 让新会话立刻知道「在干嘛、连哪个仓库、怎么操作」。最后更新：**2026-11-04（v3.0）**。

## 0. 一句话定位
为「陕西商洛 · 中国移动宽带 · 电视端 TVBox / 影视仓」定制的影视源。
- **直播**：`main.m3u` = 陕西移动 IPTV 内网 CDN（家里电视最快，103 频道/170 线路）；
  `public.m3u` = 实测可用的纯公网 IPv4 线路（手机蜂窝/外网用，42 频道/55 线路）。
  配置里是 **3 个 `lives` 对象**，用户在直播页下拉切换。
  ⭐ **2026-11-04 19:42 用户拍板「电视绝对优先」**：`lives[0]` 必须是内网极速 `main.m3u`。
  曾把公网挪到默认想让手机零操作，但电视 106 台→43 台、起播 0.1s→2~8s，影响过大已恢复。
  手机改为「直播页切 ③ 一次（App 记住）」或独立「直播地址」框填 `public.m3u`。订阅地址一字未改。
- **点播**：28 站候选经 **3 轮稳定性采样**精选出 **6 个**（全部 3/3 轮成功）：
  **量子 / 360新 / 非凡5 / 电影天堂 / 速播 / 天涯**。

## 1. 关键地址（写死，别猜）
| 项 | 值 |
|---|---|
| 仓库 | `https://github.com/anbola/tvbox`（分支 `main`） |
| 页面 | `https://anbola.github.io/tvbox/` |
| **唯一订阅入口（永久固定）** | `https://anbola.github.io/tvbox/tvbox_clean.json` —— ⛔ **2026-11-04 用户拍板：此网址永不变，禁止改动、禁止让用户重填/换地址**；更新只覆盖该文件内容 |
| 应急备用（平时不用） | `https://testingcf.jsdelivr.net/gh/anbola/tvbox@main/tvbox_clean.json`、`https://cdn.jsdmirror.com/gh/anbola/tvbox/tvbox_clean.json`（仅主地址连续多日打不开才临时用，有缓存滞后） |
| 线上健康状态 | `https://anbola.github.io/tvbox/status.json`（每日健康检查产出） |
| 直播 | 内嵌在 json 的 **`lives` 数组 3 个对象**（① 内网极速〔电视默认〕 / ② 国内镜像 / ③ 公网通用〔手机切这个〕），TVBox「直播源」框**留空**；⚠️ **绝对不要在 lives 对象里写 `url2`**（见 §7） |
| GitHub 令牌 | 本地 `~/.workbuddy/secrets/anbola_github_token.txt`（PAT，`ghp_` 开头）；仓库内另有 `anbola_token.txt` 也被 .gitignore 屏蔽。**绝不入库** |
| 本地历史索引 | `history/INDEX.md`（2026-11-04 起有，含 43 个历史版本台账 + 里程碑标记） |

⛔ **订阅地址铁律（2026-11-04 用户明确要求「每次不要变那个网址」）**：
`SUBSCRIBE_URL` 以 `tools/address.py` 为唯一权威；`tools/check_address.py` 在 CI 里强制校验
配置 / README / status.json / healthcheck / SKILL 里的地址一致。**以后任何更新都只改文件内容，
不改 URL、不给用户新地址、不写「请改用 XXX 地址」的文案。** 以前那些「换镜像主用 / 换 pages.dev /
换七牛域名」的建议全部作废（`TVBox_CDN与部署修复方案.md` 顶部已标历史记录）。
若主地址真的连续多日不可用，先修它（Pages/仓库/健康检查），**而不是让用户改地址**。

## 2. 当前架构快照（2026-11-04 v3.0）
```
tvbox_clean.json          ★唯一配置（6 个点播站 + 3 个 lives 对象）
lives/main.m3u            ★内网极速（103 频道/170 线路，死链+纯 HEVC 已剔除）
lives/public.m3u          ★公网通用（42 频道/55 线路，手机/外网用）
lives/pool.m3u            候选池（1MB，云端每周扩充）
status.json               每日健康检查产物
refresh.bat               ★一键刷新（双击，本地跑）
README.md                 用户手册（§9 点播精选 / §10 持续可用 / §11 归档规范）
.github/workflows/
  refresh.yml     每周六 21:30 抓候选池 + 结构校验（含 lives 规范断言）
  keepalive.yml   ★每月 1/15 保活，防 GitHub 60 天无活动禁用定时任务
  healthcheck.yml ★每天 08:20 全链路体检，异常自动开 issue
tools/ (13):
  fetch_sources.py   抓社区候选源（含 zhi35/hacks/myIPTV 公网源）
  merge_pool.py      去重合并进 pool.m3u（云端用）
  speedtest.py       ★直播测速：下载真实 TS 分片算码率
  codec_probe.py     解析 PAT/PMT/SPS：编码+分辨率
  live_expand.py     补 1080p 备选线路
  build_live.py      生成 main.m3u
  build_public.py    ★抓公网订阅→过滤 IPv6/内网→实测→生成 public.m3u
  vod_probe.py       点播单次体检（被 vod_stable 复用 check()）
  vod_stable.py      ★点播 3 轮稳定性采样 + 综合评分 + 同族去重
  build_config.py    生成 tvbox_clean.json（优先读 vod_stable.json）
  healthcheck.py     ★线上全链路体检，写 status.json
  refresh_all.py     串起全流程（⑦ 发布后自检）
  deploy_clean.py    发布到 GitHub（Contents API）
  tidy_history_once.py  history/ 一次性批量归位
# 兼容镜像层（deploy 自动同步，防老客户端 404，勿单独删）：
#   lives/fast.m3u = lives/main.m3u ; lives/cn_clean.m3u = lives/main.m3u ; tvbox_multisource.json = tvbox_clean.json
```
**点播精选规则（v3.0）**：`build_config.py` 优先读 `_probe/vod_stable.json`，按 `qualify`
（成功率≥2/3 且码率中位数≥1200kbps）+ `score` 降序取前 6，并**同族去重**
（`re.sub(r"(新|\d+)$","",name)`：量子/量子1、非凡/非凡5/非凡1、360/360新 是同一资源池不同域名）。
无稳定性榜单才回退到旧的 `vod_final.json` / `vod_report.json`。

## 3. 怎么操作（两套路径，别混）
### 3.1 本地刷新（必须在本机/电视同网下跑，测速才有意义）
GitHub 服务器在国外，从那边测中国移动 IPTV 毫无意义，所以**测速只能在用户家跑**。
```
双击 refresh.bat
# 或：python tools/refresh_all.py --deploy        （全流程，含部署）
# 只更新直播：python tools/refresh_all.py --no-vod --deploy
# 不重新抓取：python tools/refresh_all.py --skip-fetch --deploy
```
`refresh.bat` 默认带 `--deploy`，会自动推 GitHub。

> ⚠️ **开局会"卡"住几分钟是正常的，不是死机**：第 ① 步抓取候选源（`fetch_sources.py`）要从 7 个上游拉清单，多个走 `gh-proxy.com`，每个 `timeout=35s × 2 次重试`，且**只有失败才打印**。前几个上游若慢/不通，cmd 窗口会长时间无输出——等它过了抓取阶段就会开始逐条打印「✓/✗ 源名」和测速进度。总流程约 5–15 分钟（② 逐条测速最久）。

### 3.2 云端 CI（GitHub Actions，不用管）
`refresh.yml` 每周六 21:30（北京时间 UTC 13:30）+ push 触发。**只**抓候选池进 `pool.m3u` + 校验结构，**绝不**改 `main.m3u` / `tvbox_clean.json` / 不测速。状态查：`https://github.com/anbola/tvbox/actions`。

### 3.3 改仓库文件 / 部署（⚠️ 本机 git 被墙，走 API 不用 git）
**本 WorkBuddy 机器不能 `git clone`/`git push` github.com（连接被重置）**。改或新增仓库文件一律用 **GitHub Contents API**：
```bash
TOK=$(cat ~/.workbuddy/secrets/anbola_github_token.txt | tr -d '\r\n')
# 写/更新一个文件（已存在的要先拿 sha）：
python - <<'PY'
import base64,json,urllib.request,os
TOK=open(os.path.expanduser("~/.workbuddy/secrets/anbola_github_token.txt")).read().strip()
path=".workbuddy/skills/anbola-tvbox/SKILL.md"   # 目标路径
local="SKILL.md"                                  # 本地内容文件
content=open(local,"rb").read()
api="https://api.github.com/repos/anbola/tvbox/contents/"+urllib.parse.quote(path,safe="")
req=urllib.request.Request(api,headers={"Authorization":"token "+TOK,"Accept":"application/vnd.github+json"})
try:
    sha=json.load(urllib.request.urlopen(req,timeout=60)).get("sha")
except Exception:
    sha=None
body={"message":"chore: 更新 SKILL","content":base64.b64encode(content).decode()}
if sha: body["sha"]=sha
req2=urllib.request.Request(api,data=json.dumps(body).encode(),
      headers={"Authorization":"token "+TOK,"Content-Type":"application/json"},method="PUT")
print(json.load(urllib.request.urlopen(req2,timeout=60)).get("commit",{}).get("sha","ERR"))
PY
```
删除文件同理：`method="DELETE"` 且 body 带 `"sha"`。

## 4. 本机网络限制（实测，重要）
- `raw.githubusercontent.com` 与 `cdn.jsdelivr.net` **被墙**（返回 000）—— 本机测不出 raw/直链在用户家的真实速度，速度对比必须在用户电视/网络实测。
- **`github.com` 的 git 协议被重置** —— 不能 clone/push，文件操作走上面的 Contents API。
- `api.github.com` **极慢（单次 15~60s）** —— curl 必须 `--max-time` 60 起，urllib 要设 timeout 且别一次性发起几十个请求。
- 只有 `anbola.github.io` 直连通畅。

## 5. 归档去重纪律（用户通用铁律，长期习惯）
1. **新做/最终产物留在根目录**；中间物、旧版、旧验证 JSON、临时脚本 → 移入 `archive/`（按 `raw-sources/`、`old-*/` 分类）。收尾后根目录一眼能看懂「现在用啥」。
2. **删文件前必查引用**：`grep` 全仓（含 `.github/workflows/*.yml`、`tools/*.py`、`README.md`）看有没有人引用它。**工作流 `git add` 不存在的路径会直接 CI 失败**；`autoheal`/`refresh` 类脚本若 `open()` 了被删文件会 FileNotFoundError 崩。务必先改引用再删。
3. **字节级重复直接删**：同 MD5 的文件留一份（权威），其余删（删前本地备份到 `archive/` 可逆）。
4. 收尾用 **MD5 三方对比**（本地 root / 本地 tools / 线上）消除分叉——避免「改到备份副本上」的坑。

## 6. 回退陷阱（部署前必做）
- 本地工作区可能残留**旧版/分叉**文件（如曾经有 14 源、19 源配置）。**部署前先 diff 本地 vs 线上**，确认本地是正确新版再覆盖，**绝不盲覆盖**正确版本。
- 上次（2026-10-28）就吃过亏：本地是 14 源旧版、线上是 5 源正确版，差点把对的覆盖成错的。

## 7. 已知坑（TVBox 配置层）
- **`playerType: "1"` 必须给直播**：这批移动源音频是 MP3，微鲸电视（Android 5.0.2 / MStar）的 EXO 硬解会在 `CHECK_EQ(AudioMp3)` 处 `abort()` 进程（点直播闪退退首页）。IJK 软解才稳。
- **点播站缺 `key`/`type`/`api` 任一** → TVBox 静默跳过该站（首页少站、不报错）。`type` 必须为 1；不能有 `ext`；`api` 不焊死 `ac=videolist`。
- **采集站「电影/电视剧」主分类服务器端是 0 条**，片源都在子分类。配置列的是真有货的分类（每站 14 个），播放器默认开第一个分类会空白——点一下标签就有。
- **移动源 720×576 标清流**靠 VUI/DAR 标 16:9，但 IJK 不读该标记会铺成 4:3 方屏。根治：给频道排一条真 1080p 线路（main.m3u 排序规则已 1080p 优先）。
- ⭐ **「点播正常、直播空白」根因（2026-11-04 确诊，最高频坑）**：`lives` 对象里写了
  `url2`（**TVBox 根本没有这个字段**）+ `playerType` 写成字符串 `"1"` + 缺 `type:0`，
  会让 TVBox / 影视仓把**整段 lives 解析丢弃** → 点播站正常显示、直播页完全空白。
  **官方规范**（ShellTV 语法文档 / 恩山 / CSDN 多处一致）：
  ```json
  "lives": [
    {"name":"主", "type":0, "url":"...m3u", "playerType":1},
    {"name":"备", "type":0, "url":"...m3u", "playerType":1}
  ]
  ```
  · `type` 必须**显式整数 0**（0=M3U，1=TXT；缺省虽是 0，但不少分支缺省时直接丢整段）
  · `playerType` 必须**整数**（字符串会让 Gson 严格解析抛错）
  · **备用源靠数组放多个对象**，不是写 `url2`；多个 lives 在直播页下拉切换
  · `healthcheck.py` + `refresh.yml` 已加断言，写出非法字段会被 CI 拦下
- ⭐ **手机直播空白第二层根因（2026-11-04）**：`main.m3u` 全是 `dbiptv.sn.chinamobile.com`
  等**陕西移动 IPTV 内网/组播地址**，只在家里移动宽带内网可达。手机用蜂窝/外面 WiFi
  时频道即使列出也全部连不上 → 看起来"空的"。解法：`build_public.py` 从 zhi35 /
  hacks / zbds / myIPTV 抓公网源，**过滤 IPv6 字面量 `[2409:...]` 和 otttv/PLTV 组播**，
  逐条实测可达后生成 `lives/public.m3u`，作为第 3 个 lives 对象供手机切换。
- ⭐⭐ **手机直播空白第三层根因 = 默认项选错（2026-11-04）**：TVBox / 影视仓
  **默认加载 `lives[0]`**，而 lives[0] 是内网 `main.m3u`。即使配置完全合法、公网源也做好了，
  手机填完那**唯一一个**订阅地址后依旧空白 —— 多数用户找不到直播页「切换源」下拉。
  19:30 曾把公网挪到 lives[0] 让手机零操作 → **19:42 用户否决，已恢复电视第一**（理由见下条）。
- ⭐⭐ **「能不能自动区分电视/手机」架构结论（2026-11-04，别再尝试）**：
  在「一个固定静态订阅地址」约束下**做不到**。GitHub Pages 无后端、TVBox 不执行 JS、
  请求里没有任何设备/网络标识；手机连自家 WiFi 时出口 IP 与电视完全相同，按 IP 也分不开；
  TVBox 原生没有「按网络自动选 lives 源」的开关。
  唯一近似方案是把公网线路作为「第二线路」并进 `main.m3u`、靠 App 播放失败自动换源，
  但依赖各分支实现、要让周更脚本跟着改、且部分壳会把同名多线路显示成重复频道
  （反而伤电视体验）→ **不采用**。
  ✅ 采纳：**电视默认内网**；手机「直播页切 ③ 一次（App 记住）」或独立「直播地址」框
  直接填 `public.m3u`（一次配好永久生效）。订阅地址一字未改。
  `check_address.py` 已加断言钉死「首项必须是内网极速」，防止以后被"优化"回去。
  **影响量化**：`main.m3u` 106 台/174 线路/首包 0.05~0.14s
  vs `public.m3u` 43 台/56 线路/部分 2~8s 且民间小站易失效 —— 电视影响大，必须优先。
  排查手机端残留旧配置：清缓存 → 配置页点确定重新加载 → 强制停止重开 →
  确认直播入口未被「首页显示」关掉。
- ⭐ **电视端提速的空间在哪（2026-11-04 20:40 实测）**：`tv_speedtest.py` 3 轮×24 并发
  量了 174 线路 + 6 API，点播 API 另做 **9 轮 P75 采样**。**直播已接近物理极限**
  （每频道首条中位 70.5ms，106 台/172 可达），重排最多省 11ms 却会破坏 1080p 优先 → 不动；
  真正瓶颈是**点播搜索并发**（等待 = 最慢那个站）。原按评分给虎牙 P75 1739 + 暴风 1892，
  改成按 9 轮 P75 给 **索尼 836 + 360 1147** → 尾部 1.89s→1.15s、最坏 5.5s→1.2s。
  ⚠️ **判据必须是 P75 不是中位数**：3 轮中位数曾挑出量子 808 + 虎牙 842，
  复测时量子跳到 3468ms、虎牙最差 5470ms。两个脚本都带内置 P75 兜底值，
  测速文件丢失也不退回「评分前 2」。另剔除 3 轮全失败死链 2 条（174→172）。
  优化已固化进 `build_config.py` / `build_live.py`，别再为零几毫秒去重排线路。
- ⭐⭐ **v3.2 已推翻「海南/西藏保持慢线」结论（2026-11-04 晚）**：v3.1 用手写 TS
  解析器只筛 58 条 IPv4 候选就判定无合格替代。v3.2 改用**本机 ffprobe**
  （`D:\GREENSOFT\ffmpeg-master-latest-win64-gpl-shared\bin\ffprobe.exe`）对 674 条候选
  做真实画质探测，找到 97ms / 108ms 的 1920×1080 16:9 H.264 线路并已上线。
  以后判断画质**只用 ffprobe**，别再用手写解析器下「无替代」的结论。
- ⭐⭐ **画质盲区才是 v3.1 最大的问题**：旧 `_probe/codecs*.json` 只覆盖 74 条，
  且家里电视实际走的 `dbiptv` 内网线几乎全缺 → `build_live.py` 的 prefer() 拿不到
  分辨率，就把 720×576 的 4:3 线当「无数据」排到第一，**105 台里 37 台是方屏**。
  v3.2 补上 `lives/quality_map.json`（219 条 ffprobe 真实画质）后，首条 16:9 高清 AVC
  **57→75 台**，首包中位数仅 **70→74ms**（几乎无损）。`build_live.py` 只给已验证高清线
  加 `pinned` 标记，没有 pinned 的频道排序规则完全不变。
  ⚠️ 三个数据文件 `lives/quality_map.json` / `lives/hd_picks.json` /
  `tools/vod_picks.json` **必须随仓库部署**，否则 CI 周更会把 4:3 带回来。
- ⭐⭐ **点播两个速度维度都要看（v3.2）**：API 首包（搜索/列表）+ 视频分片（播放）。
  光速站 API P75 1624ms 但分片只有 64/191/351kbps → 剔除；补测的最大/森林/樱花/天涯
  分片同样不达标。定稿 **5 站**（非凡5/索尼/量子/360/电影天堂），API P75 676~1615ms、
  分片 1081~1984kbps，quickSearch = 非凡5 + 量子。TVBox 搜索会并发所有站，
  硬凑第 6 个慢站反而更慢。
  ⚠️ `build_config.py` 会 `force_https`，**必须用 https 同场次 A/B 测速**；
  http 榜单不作数（电影天堂 http 675ms → https 1615ms）。
  新工具：`tools/stream_probe.py`（ffprobe 画质）、`tools/vod_rank.py`（3轮粗筛+9轮P75）。
- ⭐ **点播单次测速不可信（2026-11-04）**：同一站不同时刻 360=7290↔620kbps、
  电影天堂 1862kbps↔断连、速播 0↔1902kbps。**必须 3 轮采样取中位数 + 成功率加权**
  （`vod_stable.py`），否则选出来的"优质站"几天就废。这是"用一段时间用不了"的主因之一。
- ⭐ **「用一段时间突然不更新」机制性真因**：GitHub 会在仓库 **60 天无 push 活动**后
  自动 **disable 所有 schedule 工作流**，无任何通知。`keepalive.yml` 每月 1/15 提交心跳防住；
  `healthcheck.yml` 每天体检（配置/lives 规范/m3u/点播 API/订阅地址），异常自动开 issue。
- README 目录结构、`history/CHANGELOG.md` 悬空引用等旧矛盾已在 v3.0 修正。
- **「CDN加载失败，请检查网络」根因（2026-11-03 确诊）**：配置 JSON 与内嵌 `lives/main.m3u` 原先都挂在 GitHub 设施上，而 GitHub 系在大陆要么被墙（`cdn.jsdelivr.net` 主域、`raw.githubusercontent.com` 连接重置）要么慢到触发 TVBox 加载超时（`anbola.github.io` 高峰家宽超时、`fastly/gcore.jsdelivr.net` 实测 13~16s）。**直播流本身是国内地址**（`dbiptv.sn.chinamobile.com` 陕西移动 IPTV 官方 CDN + 直连 IP），不依赖 GitHub——所以这是"取配置的门"单点故障，换地址即让 4 站点播 + 88 台直播全恢复。修复已落地：订阅入口**维持 `anbola.github.io` 主用**（用户拍板，更稳更熟悉），备用通道改为 `lives` 数组里的第二个对象（testingcf 镜像）。⚠️ 早期版本写的是 `url2`，那是**非法字段**，11-04 已废除，详见下一条。详见仓库根 `TVBox_CDN与部署修复方案.md`。**永久根治**= 把配置+直播源部署到国内托管（七牛/又拍云对象存储+CDN 实名永久免费额度，或 Cloudflare Pages 自动部署），已有 `tools/deploy_qiniu.py` 一键推送七牛。

- ⚠️ **refresh.bat「卡住」根因与修复（2026-11-03 确诊+已修+本轮验证通过）**：① 进度盲区——`speedtest.py` 原只在「每 200 条」打印一次，最后 <200 条不再打印，看着像死机，其实在跑；② 真卡死风险——最后一批是非移动 CDN 外部源，碰到「失效域名 + DNS 解析挂起」时，Python `urlopen(timeout)` **拦不住 DNS 阶段**，线程无限阻塞 → 窗口真死。已修：`speedtest.py`/`vod_probe.py`/`codec_probe.py`/`build_config.py`/`live_expand.py` 全部去掉 `with ThreadPoolExecutor` 的隐式 `shutdown(wait=True)`，改为 `socket.setdefaulttimeout` 全局兜底 + `as_completed(timeout=300)` 强制收尾 + `os._exit(0)` 利落退出；`refresh_all.py` 的 `print("▶")` 改 `sys.stdout.reconfigure(encoding='utf-8')` 避开 GBK 崩溃。**2026-11-03 重跑验证：总用时 1124s 全程跑完、未挂起，超时兜底在第 ② 步优雅触发（1249/1256 条后停止等待，已测照常入库），证明卡死已根治。**

## 8. 当前健康度（2026-11-04 v3.0，部署后以 status.json 为准）
- **直播内网版**：`main.m3u` = **103 频道 / 170 线路**（死链剔除、13 个纯 HEVC 频道剥离防微鲸崩）。
- **直播公网版**：`public.m3u` = **42 频道 / 55 条实测可用线路**（2411 条候选 → 过滤 IPv6/内网
  后 309 条 → 实测 56 条可用）。央视 15 / 卫视 26 / 陕西本地 1。
- **点播**：28 站 × 3 轮采样 → 8 站达标 → 同族去重取 **6 站**：
  量子(3635k) / 360新(1606k) / 非凡5(1488k) / 电影天堂(1912k) / 速播(1914k) / 天涯(1269k)，
  **6 站全部 3/3 轮成功**。
- **配置**：6 sites + 3 lives 对象，`type:0` / `playerType` 整数 / 无 `url2`。
- **持续可用**：refresh.yml（周更+规范断言）、keepalive.yml（保活）、
  healthcheck.yml + healthcheck.py（每日体检 + 异常开 issue + status.json）。
- **归档**：`history/` 43 个历史版本已规范命名，6 份 `manifest.json` +
  `INDEX.md` + `README.md`；本次 v3.0 已登记为有效里程碑 ⭐。
- **3 个「兼容镜像」文件** `lives/fast.m3u`、`lives/cn_clean.m3u`、`tvbox_multisource.json`
  由 `deploy_clean.py` 自动同步（别名层，防老客户端 404）。别单独删，删了下次 refresh 会复活。
- 已装且适用的技能：`file-version-archive`（归档）、`github-pages-deploy`（Pages/保活）。
  SkillHub 无 IPTV/TVBox 对口技能（4 组关键词全部 score≤0.05），不必另装。
- ⭐ **每次发布后的归档一条命令（v3.1 起）**：
  `python tools/archive_version.py archive vX.Y --note "改了什么" --milestone --apply`
  → 自动全量快照到 `history/vX.Y_YYYYMMDD/`（MANIFEST.md + manifest.json：
  版本号/时间/变更说明/有效性/里程碑/MD5）+ 追加 CHANGELOG.md 与 INDEX.md。
  默认 dry-run，`--apply` 才动手。另有 `tidy`（顶层散落文件归位）与
  `clean-cache`（清 pyc）子命令。规范见 `history/README.md`。
  ⚠️ 改台账时别丢原有 dict 记录，时间戳用 `ts[-4:-2]:ts[-2:]`（曾误写成 `-1:53`）。

## 9. 接手清单（换电脑/新会话第一件事）
1. 读本 SKILL + 仓库 `README.md`（人看的手册，最全）。
2. 确认令牌就位（本地 secrets 文件或 `export ANBOLA_TOKEN=...`），否则无法部署。
3. 若用户说「源慢了/台失效」→ 让他双击 `refresh.bat`（本地跑测速）。
4. 若要改仓库文件 → 用第 3.3 节的 Contents API，别用 git。
5. 任何改动收尾 → 走第 5 节归档去重纪律 + 第 6 节回退检查。
