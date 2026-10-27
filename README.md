# TVBox 自维护配置仓库（anbola/tvbox）

> 一套「点播 + 直播 + 解析」全自维护的 TVBox / 影视仓 / MyTV（我的电视）配置。
> 所有资源经真实请求验证，直播源每日自愈刷新，点播源逐分类实测收录。
> 项目主页（GitHub Pages，所有地址均以此为基础）：**`https://anbola.github.io/tvbox/`**

---

## 一、所有源地址一览（先看这里，防止混淆）

> 下面把**每一个源**的地址单独列清。复制时请整行复制，注意结尾不要带多余空格。

### 1. 点播源（影视 · **精选 5 个**，粘贴进「点播源 / 配置地址」框）

| 序号 | 名称 | API 地址 | 实测（2026-10-27） |
|------|------|----------|--------------------|
| VOD01 | 🎬非凡┃极速·资源 | `https://ffzy5.tv/api.php/provide/vod?ac=videolist` | API **685ms** · 片库 9.9 万 |
| VOD02 | 🎬火狐┃采集 | `https://hhzyapi.com/api.php/provide/vod/?ac=videolist` | API 1086ms · 片库 11.6 万 |
| VOD03 | 🎬金鹰┃资源 | `https://jyzyapi.com/api.php/provide/vod?ac=videolist` | API 2470ms · **播放首字节 188ms** |
| VOD04 | 🎬豆瓣┃资源 | `https://dbzy.tv/api.php/provide/vod?ac=videolist` | API 2841ms · 片库 14.8 万 · 响应最轻 |
| VOD05 | 🎬暴风┃采集 | `https://bfzyapi.com/api.php/provide/vod?ac=videolist` | API 3158ms · **片库 16.7 万** |

> **精选说明（宁精勿滥）**：原 14 源经实测**去重 + 剔慢源**后仅留 5 个，按 API 中位速度排序：
> - **重复源剔除**：非凡/非凡2/非凡3 内容完全相同；量子/量子2 也相同（字节数与片库一致）。
> - **慢源剔除**：量子 14.3s（响应 927KB 超重）、虎牙 9.3s、极速/闪电 7.7s、索尼/百度/360 5s 级。
> - **失效剔除**：光速、卧龙、华为、哔嘀、快车、天空、无尽、红牛、影视工厂、超级（域名已死）。
> - 5 源**总片库约 64.6 万部**，API 全部 ≤3.2s、封面 20/20 齐全、响应轻量（最快 60KB）。
> - 全部为 `type:1` 纯采集接口、`spider` 留空 —— **不依赖加密 jar，从源头避免「导入报错」**。

> 这 5 个源已经打包在下面的「完整配置 / 点播专用 / 订阅聚合」里，**无需逐个手动添加**；此处列出仅供核对出处。

### 2. 直播源（电视频道 · 10 个 .m3u，粘贴进「直播源」框）

| 序号 | 名称 | 地址 |
|------|------|------|
| LIVE01 | CCSH 自动采集（2811 台） | `https://anbola.github.io/tvbox/lives/ccsh_clean.m3u` |
| LIVE02 | BigBig 聚合源（1956 台） | `https://anbola.github.io/tvbox/lives/bigbig_clean.m3u` |
| LIVE03 | Guovin 中国 IPTV（1618 台） | `https://anbola.github.io/tvbox/lives/guovin_clean.m3u` |
| LIVE04 | Vamoschuck·TV（896 台） | `https://anbola.github.io/tvbox/lives/vamos_clean.m3u` |
| LIVE05 | 咪咕中转·央视卫视（620 台） | `https://anbola.github.io/tvbox/lives/mzky_clean.m3u` |
| LIVE06 | 直播帝·IPV4（506 台） | `https://anbola.github.io/tvbox/lives/zbds4_clean.m3u` |
| LIVE07 | Yang·咪咕移动（338 台） | `https://anbola.github.io/tvbox/lives/yang_clean.m3u` |
| LIVE08 | 央视·卫视精选（149 台） | `https://anbola.github.io/tvbox/lives/cn_clean.m3u` |
| LIVE09 | YangGather·聚合（123 台） | `https://anbola.github.io/tvbox/lives/yanggather_clean.m3u` |
| LIVE10 | Kimentanm·IPTV（120 台） | `https://anbola.github.io/tvbox/lives/kimentanm_clean.m3u` |

### 3. MyTV（我的电视 · 〇）直播源（2 个 .m3u，MyTV 里填「自定义直播源 / 远程配置」）

| 名称 | 地址 | 说明 |
|------|------|------|
| 精简版（**推荐手机**） | `https://anbola.github.io/tvbox/mytv_lite.m3u` | 央视+卫视+4K·8K+港澳台+体育+少儿+影视+综艺，约 3800 台，体积小、秒开不卡 |
| 全量版 | `https://anbola.github.io/tvbox/mytv.m3u` | 含地方台/其他等全部，约 7900 台，体积较大 |

> ⚠️ MyTV **只认 `.m3u` 结尾**的地址；`tvbox_lives.json`（见下）是 TVBox 专用，填进 MyTV 会「识别 10 个源却无频道」。

### 4. 订阅聚合入口（★推荐：一个地址同时配好「点播 + 直播」）

- `https://anbola.github.io/tvbox/tvbox_subscription.json`

> 在 TVBox「设置 → 配置地址」填入这一个即可，会自动合并 5 个精选点播源 + 10 个直播源 + 解析接口。

### 5. 完整配置文件（按需直接粘贴）

| 文件 | 地址 | 用途 |
|------|------|------|
| 全量配置（点播+直播+解析） | `https://anbola.github.io/tvbox/tvbox_curated.json` | 一次性配置全部功能 |
| 点播专用 | `https://anbola.github.io/tvbox/tvbox_sites.json` | 只要点播（无直播）的客户端 |
| 多源配置 | `https://anbola.github.io/tvbox/tvbox_multisource.json` | 多源/多仓版本客户端 |
| 直播专用（TVBox 直播框） | `https://anbola.github.io/tvbox/tvbox_lives.json` | 只填进「直播源」框，含 10 个 m3u |

### 6. 解析接口（看 VIP / 收费剧用）

- 阿雪解析：`https://jx.xmflv.com/?url=`

---

## 二、项目简介

本仓库把「TVBox 点播接口 + IPTV 直播源 + 视频解析」三类资源做成**可自动维护**的配置：

- **点播**：精选 **5 个**高速采集站 API（实测去重/剔慢源，总片库约 64.6 万部），逐个分类实测有内容才收录，封面/详情由源站直出。
- **直播**：每日从 19 个公开 IPTV 源里探测、清洗、取最健康的 10 个，输出标准 `.m3u`。
- **解析**：内置阿雪解析，配合 `rules` 自动识别各大平台 VIP 线路。
- **自愈**：直播源每天 05:30（北京时间）自动重跑；点播配置每天 06:00 重新实测收录。

---

## 三、文件结构

```
anbola/tvbox
├── tvbox_subscription.json   # 订阅聚合入口（推荐）
├── tvbox_curated.json        # 全量配置（点播+直播+解析）
├── tvbox_sites.json          # 点播专用（仅 sites）
├── tvbox_multisource.json    # 多源/多仓配置
├── tvbox_lives.json          # 直播专用（TVBox 直播框）
├── mytv.m3u                  # MyTV 全量直播源（≈7900 台）
├── mytv_lite.m3u             # MyTV 精简直播源（≈3800 台，手机推荐）
├── lives/                    # 清洗后的直播源 m3u（被上面的地址引用）
│   ├── ccsh_clean.m3u
│   ├── bigbig_clean.m3u
│   ├── ...（共 10 个聚合源）
│   └── fast.m3u              # 极速版（国内 CDN 流 + 砍境外台标/境外流，≈1000 台，卡顿首选）
├── tools/                    # CI 脚本
│   ├── autoheal_lives.py     # 直播源自愈（探测→清洗→取 TOP10）
│   ├── build_curated.py      # 点播源实测收录 + 生成各配置文件
│   └── make_mytv.py          # 合并 10 源 → mytv.m3u / mytv_lite.m3u
└── .github/workflows/
    ├── update-lives.yml      # 每日 05:30 自愈直播源
    ├── verify-curated.yml    # 每日 06:00 重新实测点播源
    └── discover-sources.yml  # 每周一发现新源
```

---

## 四、使用方法

### TVBox / 影视仓（Android / 盒子 / PC）
1. 打开 App → 设置 → 配置地址。
2. **最省事**：只填 `https://anbola.github.io/tvbox/tvbox_subscription.json` 一个地址，重启即生效（点播+直播+解析全有）。
3. **想分开配**：
   - 点播/配置地址填 `https://anbola.github.io/tvbox/tvbox_curated.json`
   - 直播源框单独填 `https://anbola.github.io/tvbox/mytv_lite.m3u`（直接填 m3u 最稳，比填 `tvbox_lives.json` 兼容性更好）

4. **想要极速、不卡（手机 / 老旧设备首选）**：
   - 配置地址填 `https://anbola.github.io/tvbox/tvbox_sites.json`（只要 5 个精选点播 + 解析，**不含**那近 9000 台直播，列表秒开）
   - 直播源框填 `https://anbola.github.io/tvbox/lives/fast.m3u`（约 1000 台，全是国内 CDN 流、台标只走国内 gitee、已剔除境外流，换台即播）

> ⚠️ **「直播源」框只填 `.m3u` 或 `tvbox_lives.json`，绝不填完整配置 JSON**（如 `tvbox_curated.json`/`tvbox_subscription.json`）。把完整配置填进直播源框会弹「配置解析失败」且直播空白。若只想用一份配置搞定全部，直接把 `tvbox_subscription.json` 填进「配置地址」并**留空直播源框**即可。

### MyTV（我的电视 · 〇）
1. 进入「自定义直播源 / 远程配置」。
2. 填入 `https://anbola.github.io/tvbox/mytv_lite.m3u`（或全量 `mytv.m3u`）。
3. **不要**把 `tvbox_lives.json` 填进 MyTV——那是 TVBox 的 `{"lives":[...]}` 格式，MyTV 无法解析，会显示「识别 10 个源但无频道」。

---

## 五、常见问题排查

### Q1. 点播界面能出列表、能播放，但**封面全是一片灰/不显示**
**根因**：点播源的 `api` 原本用的是 `?ac=list`，该接口只返回摘要、**不含 `vod_pic` 封面字段**；视频能播是因为播放地址是另一个字段，与封面无关。
**修复**：已把所有站点 `api` 统一改为 `?ac=videolist`（该接口在列表里直接带回 `vod_pic`）。
**你这边要做**：
1. 重新加载配置（设置 → 清除缓存 → 重新填入上面的地址 → 重启 App）。
2. 若仍不显示，90% 是 App 缓存了旧地址，清除缓存并强制刷新即可。
3. 个别源的海报图床若在你网络下被墙，可给该站点加 `pic` 图片代理（见下）。

> 关于 `pic` 图片代理（可选）：TVBox 支持在站点配置里加 `"pic": "https://你的图片代理/"`，会把所有 `vod_pic` 前缀代理。仅在「列表/播放正常、唯独图片灰块」且确认是图床被墙时才需要。本项目默认不启用，避免引入不稳定第三方代理。

### Q2. 直播源导入后**列表空白 / 没有频道**
按症状对号入座：
- **「识别出 10 个源，但点进去啥都没有」** → 多半是把 `tvbox_lives.json` 填进了 MyTV 或填错了位置。MyTV 请用 `mytv.m3u`/`mytv_lite.m3u`；TVBox 直播框请直接填 `mytv_lite.m3u`（单个 m3u 兼容性最好）。
- **「直播页完全空白，连分组都没有」** → 检查直播地址是否以 `.m3u` 结尾、是否整行无空格；`tvbox_lives.json` 必须填进「直播源」框而非「配置地址」框。
- **「有分组、频道列表空」** → 源站临时抽风，等次日自愈（每天 05:30 自动刷新）或换填另一个 `lives/*.m3u` 直链。

### Q2-1. 每次弹「配置解析失败」，退出后点播正常、直播空白
**这是把「完整配置 JSON」误填进「直播源」框导致的，不是软件 / 直播源 / 脚本的毛病。**
- TVBox 的「**配置地址**」框才吃完整配置（`tvbox_curated.json` / `tvbox_subscription.json`，内含 点播+直播+解析）；
- 「**直播源**」框只认**纯直播内容**：要么直接是 `.m3u`（如 `mytv_lite.m3u`），要么是 `{"lives":[...]}` 这种纯直播 JSON（如 `tvbox_lives.json`）。
- 一旦把含 `sites`/`parses`/`rules` 的完整配置 JSON 塞进「直播源」框，TVBox 解析失败 → 弹「配置解析失败」；你点掉后，「配置地址」框里那份正确配置照常加载点播，但「直播源」框已经废了 → 直播空白。

**正确导入直播源的两种方式（任选其一）：**
1. **最省事（推荐）**：只填「配置地址」为 `tvbox_subscription.json`（或 `tvbox_curated.json`），**「直播源」框留空**。这两个完整配置已内置 10 个已验证可达的直播源，重启即见直播，且不会弹窗。
2. **想要更大的直播列表**：「配置地址」填 `tvbox_curated.json`，「直播源」框填 `https://anbola.github.io/tvbox/mytv_lite.m3u`（一个干净自包含的 m3u，≈3800 台，比 JSON 兼容性更好，绝不弹「配置解析失败」）。

> ⚠️ 切记：「直播源」框里只放 `.m3u` 或 `tvbox_lives.json` 这种纯直播 JSON，**不要放任何完整配置 JSON**（`tvbox_curated.json` / `tvbox_subscription.json` / `tvbox_sites.json` / `tvbox_multisource.json`），否则必弹「配置解析失败」。

### Q2-2. 直播能出频道了，但**换台 / 播放特别卡、半天不动**
这是「源太多 + 台标/流绕了境外」导致，**不是软件问题**：
- 默认 `tvbox_curated.json` / `tvbox_subscription.json` 自带 10 个直播源、合计近 **9000 台**，直播页一打开要解析近万条，列表本身就卡；
- 大量台标走境外图床（imgur、tvchinese、泽西岛 `.je` 等），划台时每个台都在等境外图；
- 部分流地址本身是境外 IP，从国内连自然慢。

**极速方案（已为你做好 `lives/fast.m3u`）**：
- 配置地址填 `tvbox_sites.json`（只要 5 个精选点播 + 解析，**不带**那近 9000 台直播，列表秒开）；
- 直播源框填 `https://anbola.github.io/tvbox/lives/fast.m3u`（约 1000 台，全是国内 CDN 流、台标只走国内 gitee、且已剔除境外流）。
这样直播页秒开、换台即播。若个别台仍缓冲，是免费 IPTV 源本身过载，属正常，换个台即可。

> 想要台多就填 `mytv_lite.m3u` 或用 `tvbox_curated.json`，但台越多越卡，自行取舍。

### Q3. 配置地址填了但首页空白
- 多半地址末尾多了空格，或填成了介绍页网页而非 `.json` 直链。请整行复制「一、源地址一览」里的地址。
- 老旧 Android 5 电视若报证书错误，可把 `https://` 换成 `http://`（仅当该服务器支持时）。

### Q4. 导入配置弹「导入配置错误」，而且**时好时坏**
已逐项排查，**结论：配置文件本身没问题**：

| 检查项 | 结果 |
|--------|------|
| 格式（是否合法 JSON） | ✅ 4 个配置全部合法 |
| 编码（UTF-8 / BOM） | ✅ UTF-8，**无 BOM** |
| 响应头 Content-Type | ✅ `application/json; charset=utf-8` |
| 一致性（连续抓取） | ✅ 大小完全一致，无截断/半包 |

真实原因集中在三点：
1. **Pages 重建 / CDN 窗口（最常见）**：仓库每次更新后，GitHub Pages 要几十秒~几分钟重建并刷新 CDN。你若正好在这个窗口导入，就会拿到未就绪或旧内容 → 报错，过一会儿再试又成功。**对策：刚更新完等 2–3 分钟再导入。**
2. **国内访问 `github.io` 不稳定**：时快时慢、偶发超时。**对策：换下面的镜像地址。**
3. **`stores` 字段兼容性**：`tvbox_subscription.json` 原先只靠 `stores` 间接加载、自身没有 `sites`，部分 TVBox 分支不支持 `stores` → 必然或不稳定失败。**已修复：现改为自包含**（自带 14 站点 + 10 直播 + 解析 + 规则，不再依赖 `stores`）。

**导入前先自检（成功/失败都有明确反馈）**：打开 <https://anbola.github.io/tvbox/status.html>，
会逐项显示每个配置是否生效、能否解析、大小与更新时间。**全绿再导入**即可避开上述问题。

**镜像备选**（整条填进「配置地址」，哪个快用哪个）：
- jsDelivr：`https://cdn.jsdelivr.net/gh/anbola/tvbox@main/tvbox_curated.json`
- fastly：`https://fastly.jsdelivr.net/gh/anbola/tvbox@main/tvbox_curated.json`
- ghfast：`https://ghfast.top/https://raw.githubusercontent.com/anbola/tvbox/main/tvbox_curated.json`

> 镜像同步有延迟；若镜像缺最新改动，回到 `anbola.github.io` 即可。

---

## 六、自动更新机制

| 工作流 | 频率（北京时间） | 动作 |
|--------|------------------|------|
| `update-lives.yml` | 每日 05:30 | 自愈直播源：探测 19 源 → 清洗 → 取最健康 10 源 → 重写 `lives/*.m3u` 与各配置 → 生成 `mytv.m3u`/`mytv_lite.m3u` |
| `verify-curated.yml` | 每日 06:00 | 重新实测点播 API：分类有内容才收录，重建 `tvbox_curated.json`/`tvbox_sites.json` |
| `discover-sources.yml` | 每周一 13:00 | 扫描新公开源，写入 `probe_new_sources.json` 供人工复核 |

所有工作流使用仓库 `GITHUB_TOKEN`（Workflow 权限已设为 read/write），无需任何手动干预。

---

## 七、本地二次开发

```bash
# 重新生成点播配置（会实时请求各 API 实测）
python3 tools/build_curated.py

# 手动触发直播源自愈
python3 tools/autoheal_lives.py

# 重新合并 MyTV 直播源
python3 tools/make_mytv.py
```

> 注意：`build_curated.py` 生成的站点 `api` 已内置 `fix_api()` 统一追加 `?ac=videolist`，**请勿改回 `ac=list`**，否则封面会再次消失。

---

*本仓库仅聚合公开资源索引，所有播放内容版权归原平台所有；请遵守当地法律法规，仅访问你有权使用的资源。*
