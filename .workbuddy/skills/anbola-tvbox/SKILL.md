---
name: anbola-tvbox-maintainer
description: 维护 GitHub 仓库 anbola/tvbox（TVBox / MyTV 自维护「直播+点播」配置，陕西移动宽带优化版）。当用户要更新直播源、改点播采集站、部署到 GitHub、排查配置报错、或问「这个项目是干嘛的 / 连哪个仓库 / 怎么操作 / 之前发生了什么」时使用。内含当前架构快照、部署方式（含「本机 git 被墙 → 走 GitHub Contents API」）、本机网络限制、归档去重纪律、回退陷阱、已知坑。
---

# 项目：anbola/tvbox 自维护配置

> 本 SKILL 是「跨电脑记忆」：clone 仓库 `anbola/tvbox` 并在 WorkBuddy 打开，本文件会自动加载，
> 让新会话立刻知道「在干嘛、连哪个仓库、怎么操作」。最后更新：2026-11-03。

## 0. 一句话定位
为「陕西商洛 · 中国移动宽带 · 电视端 TVBox」定制的影视源。直播全部走**陕西移动 IPTV 官方 CDN**（`dbiptv.sn.chinamobile.com`），按用户自家宽带实测码率排序；点播是 35 个采集站里实测挑出的 4 个。

## 1. 关键地址（写死，别猜）
| 项 | 值 |
|---|---|
| 仓库 | `https://github.com/anbola/tvbox`（分支 `main`） |
| 页面 | `https://anbola.github.io/tvbox/` |
| **用户唯一订阅入口** | `https://anbola.github.io/tvbox/tvbox_clean.json` |
| 直播内嵌在上面的 json 里（`lives` 指向 `lives/main.m3u`），TVBox「直播源」框**留空** |
| GitHub 令牌 | 本地 `~/.workbuddy/secrets/anbola_github_token.txt`（PAT，`ghp_` 开头）；仓库内另有 `anbola_token.txt` 也被 .gitignore 屏蔽。**绝不入库** |
| 历史变更日志 | **不存在**（README §7 写的 `history/CHANGELOG.md` 是悬空引用，目前没有这个文件——别去找） |

## 2. 当前架构快照（2026-11-03，仓库共 21 个文件）
```
tvbox_clean.json          ★唯一配置（4 个点播站 + 1 个直播）
lives/main.m3u            ★直播源：88 频道 / 154 线路，100% 移动 CDN（约 22KB）
lives/pool.m3u            候选池（1.3MB，云端每周扩充，本地测速从这里挑）
refresh.bat               ★一键刷新（双击，本地跑）
README.md                 用户手册（详尽，给人看的）
.github/workflows/refresh.yml   云端：每周六 21:30 抓候选池 + 结构校验
tools/ (9):
  fetch_sources.py  抓社区候选源
  merge_pool.py     候选源去重合并进 pool.m3u（云端用）
  speedtest.py      ★直播测速：下载真实 TS 分片算码率
  codec_probe.py    解析 PAT/PMT/SPS：编码+分辨率（HEVC 会崩 / 576p 是 4:3）
  build_live.py     按码率排序生成 main.m3u
  vod_probe.py      ★点播体检：35 站 × 4 项指标
  build_config.py   生成 tvbox_clean.json
  refresh_all.py    串起全流程
  deploy_clean.py   发布到 GitHub（令牌只从环境变量/本地文件读）
```
**4 个点播站（type:1，api 裸地址，无 ext，ac=videolist 不焊死）**：360（360zyzz.com）、量子（cj.lziapi.com）、暴风（bfzyapi.com）、非凡（cj.ffzyapi.com）。

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
- ⚠️ README 小矛盾（待修）：① 目录结构漏列已存在的 `codec_probe.py`，却列了仓库里**不存在**的 `live_expand.py`（refresh_all.py 里它 `optional=True`，缺失会被跳过）；② §7 引用了不存在的 `history/CHANGELOG.md`。

## 8. 当前健康度（2026-11-03 复测）
- 4 个点播 API 全部 200，返回真实数据（360/量子/暴风/非凡，分类 31~51 个）。
- `lives/main.m3u`、`pool.m3u`、`tvbox_clean.json` 全部 200。
- 已去重：删掉 `lives/fast.m3u`、`lives/cn_clean.m3u`（与 main.m3u 同 MD5）、`tvbox_multisource.json`（与 tvbox_clean.json 完全相同）。
- 工作流 `refresh.yml` 状态 active。

## 9. 接手清单（换电脑/新会话第一件事）
1. 读本 SKILL + 仓库 `README.md`（人看的手册，最全）。
2. 确认令牌就位（本地 secrets 文件或 `export ANBOLA_TOKEN=...`），否则无法部署。
3. 若用户说「源慢了/台失效」→ 让他双击 `refresh.bat`（本地跑测速）。
4. 若要改仓库文件 → 用第 3.3 节的 Contents API，别用 git。
5. 任何改动收尾 → 走第 5 节归档去重纪律 + 第 6 节回退检查。
