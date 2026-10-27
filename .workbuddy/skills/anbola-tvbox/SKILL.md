---
name: anbola-tvbox-maintainer
description: 维护 GitHub 仓库 anbola/tvbox 的 TVBox/MyTV 自维护配置（点播精选5源+直播10源+解析+每日CI自愈）。当用户要改动配置、重新部署、新增/替换点播或直播源、排查「导入配置错误/封面不显示/卡顿/没频道」时使用。也用于跨电脑继续本项目时快速了解背景。
---

# anbola/tvbox 配置维护 Skill

本 Skill 固化项目背景与操作规范，使新会话/换电脑也能像老手一样直接上手。完整说明见仓库根目录 `维护手册.md`，这里给高频速查。

## 仓库与访问
- 仓库：`https://github.com/anbola/tvbox`（分支 `main`）
- Pages：`https://anbola.github.io/tvbox/`
- Token（PAT）：`~/.workbuddy/secrets/anbola_github_token.txt`（本地持有，勿提交）
- 一键订阅地址：`https://anbola.github.io/tvbox/tvbox_subscription.json`

## 当前形态（2026-10 起）
- **点播 5 源**（type:1 明文、spider 留空，避免加密 jar 导入报错）：非凡 ffzy5.tv / 火狐 hhzyapi.com / 金鹰 jyzyapi.com / 豆瓣 dbzy.tv / 暴风 bfzyapi.com。`build_curated.py` 的 `CAND_APIS` 必须等于这 5 个，否则次日 CI 会用旧 14/19 源回退线上。
- **直播 10 源**：`lives/*_clean.m3u`（清洗版，每日 05:30 自愈）。
- **分类**：学习导向（科普/纪录片→动漫→电影→少儿→剧集→综艺→体育→成人垫底），成人关键词已剔除。

## 核心脚本（在仓库根目录）
- `build_curated.py`：生成各 `tvbox_*.json`（精选5源 + 学习导向分类）。`fix_api()` 统一 `?ac=videolist`（有海报）；暴风分类回退 `ac=list`。
- `clean_lives.py` / `tools/autoheal_lives.py`：直播源清洗与每日自愈。
- `deploy_anbola.py`：**部署**到 GitHub（Contents API）。运行：`export ANBOLA_TOKEN=... && python3 deploy_anbola.py`。更新已存在文件须带 blob `sha`。

## 必读踩坑
1. `ac=list` 无海报 → 必须用 `ac=videolist`。
2. 暴风只在 `ac=list` 返回 `class`。
3. **本机出口屏蔽 `raw.githubusercontent.com` 与 `cdn.jsdelivr.net`**，只能直连 `anbola.github.io`；在这台机器测不出 raw/直链在你电视上的速度——测速请去用户电视实测。
4. 本机调 `api.github.com` 极慢（~15s），`curl --max-time` 至少 30–40s。
5. 旧账号遗留 `cn.m3u` 实际是 `cn_clean.m3u`，直接填会 404。

## 归档规范（每次收尾）
根目录只留「新做的」最终产物+核心脚本+文档；中间物/旧版/日志进 `archive/`（按 raw-sources、old-verify、old-deploy、old-*-scripts 分类）；日志与浏览器缓存可删；**绝不提交 token**。

## 常见任务 SOP
- **重新部署**：改完配置 → `export ANBOLA_TOKEN=... && python3 deploy_anbola.py`。
- **新增点播源**：先 `python3 probe_new_sources.py` 验证可用 → 改 `build_curated.py` 的 `CAND_APIS`（保持 5 源精选原则，去慢源/失效源）→ 重跑 build → 部署。
- **直播源变少/失效**：`python3 clean_lives.py` 重新探测清洗 → 部署 `lives/*`。
- **导入报错/封面灰/卡顿**：按 `维护手册.md` 第九节速查表定位。

## 操作纪律
- 增量更新：只改指定文件，不动其他辅助/索引文件。
- 每次部署后确认线上（Pages HTTP 200，且 `sites=5、lives=10、parses=1`）与健康。
- 不要为了"本地最新"盲目覆盖线上——先对比本地与线上，确认本地是正确新版再部署（曾发生本地是旧 14 源版、线上才是正确 5 源版，盲覆盖会回退）。
