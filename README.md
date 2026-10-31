# TVBox 配置（anbola/tvbox）

## 唯一地址（就填这一个）

```
https://anbola.github.io/tvbox/tvbox_clean.json
```

- 填在 TVBox / 影视仓 的「**配置地址**」框；
- 「**直播源**」框**留空**（直播已内置在这一个文件里，填了反而可能报「配置解析失败」）；
- 本仓库**不再维护**其它配置地址（旧的 `tvbox_sites.json` / `tvbox_subscription.json` / `tvbox_curated.json`
  / `tvbox_multisource.json` 已全部删除，避免再混淆）。

---

## 里面有什么

### 点播：5 个采集站 × 10 个分类

每个站点保留的分类，都是**实测有内容**的（总量 ≥ 200 条；「电影/电视剧/动漫」等主分类门槛放宽到 30 条）：

| 站点 | API | 分类示例（括号为实际片量） |
|---|---|---|
| 🎬 非凡 | `ffzy5.tv` | 剧情片(19885)、国产剧(8377)、喜剧片(7190)、恐怖片(5140)… |
| 🎬 火狐 | `hhzyapi.com` | 剧情片(15267)、喜剧片(5809)、动作片(5287)、记录片(2462)… |
| 🎬 金鹰 | `jyzyapi.com` | 剧情片(16167)、喜剧片(5835)、动作片(5329)、记录片(2468)… |
| 🎬 豆瓣 | `dbzy.tv` | 剧情片(22568)、喜剧片(8673)、动作片(6868)、战争片(709)… |
| 🎬 暴风 | `bfzyapi.com` | 剧情片(18868)、喜剧片(7548)、动作片(5131)、纪录片(1725)… |

> **为什么主页没有「电影 / 电视剧」这两个总分类？**
> 实测（2026-10-31）这 5 个采集站的「电影」总分类片量为 0~14 条、「电视剧」为 0 条 ——
> 点进去就是空白或只有一两部。真正有片的全在子分类里（动作片 / 剧情片 / 喜剧片 / 恐怖片 / 战争片…）。
> 所以配置**故意不列出这些空分类**，避免「点进电影只有一部」。

### 直播：81 个频道 / 202 条流（逐条实测可播）

- 覆盖：央视 17 套 + 各卫视 + 部分专业频道；
- 生成方式：把历史汇总的 7747 条唯一流**逐条实测**（HTTP 200 且返回 m3u8），只保留能通的，
  每个频道取**响应最快的 3 条**做备份；
- 不带 tvg-logo（原台标走 `ghfast.top`，国内不可达，会拖慢列表加载）。

### 为什么以前的直播「看得到台名、播不了」

旧配置里 683 条流中，抽样 60 条只有 15 条能连上（75% 是运营商内网 IPTV 地址，
如 `121.19.134.x`，只在特定宽带/地区可播）。本仓库已整体替换为实测可播的流。

---

## 常见问题

**Q1. 导入后提示「配置解析失败」？**
- 确认只填了「配置地址」，且「直播源」框是**空的**；
- 确认地址是 `tvbox_clean.json`（不是旧的 `tvbox_sites.json` / `tvbox_curated.json`，那两个已删除）；
- 本配置已去掉 `wallpaper` / `logo` / `doh` / `ads` / `parses` / `spider` 等外部依赖，只留 `sites` + `lives`，
  是 TVBox 能接受的**最小配置**，理论上不会再因外部链接失败而报错。

**Q2. 直播还是慢 / 个别台打不开？**
- 每个频道有 3 条备用流，长按切换到下一条即可；
- 直播流会随时间失效，需要时重新体检一遍：`python tools/probe_streams.py && python tools/build_final.py`。

**Q3. 想自己加站点？**
- 编辑 `tvbox_clean.json` 的 `sites`，`api` 填**裸地址**（`.../api.php/provide/vod/`，**不要**带 `?ac=videolist`），
  **不要**写 `ext`，`categories` 填服务器上真实存在的分类名。

---

## 目录结构

```
tvbox_clean.json          # ★ 唯一配置（sites + lives），填这个地址
lives/main.m3u            # 直播源（81 台，实测可播）
lives/pool.m3u            # 候选中转池（7747 条唯一流，供重新体检用）
tools/probe_streams.py    # 并发实测直播流 -> _probe/working.json
tools/build_final.py      # 生成 lives/main.m3u + tvbox_clean.json
.github/workflows/refresh.yml  # 每周一自动体检并更新
```

## 本地重新生成

```bash
python tools/probe_streams.py    # 体检全部候选流（约 1 分钟）
python tools/build_final.py      # 重新生成 main.m3u 与 tvbox_clean.json
```

## 版本

变更记录见本地 `history/CHANGELOG.md`（v1.0 原版 → v1.1 修 doh/ads → v1.2 修分类 → v1.3 上线 → v1.4 直播重做）。
