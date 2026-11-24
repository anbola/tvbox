#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性批量整理 history/（2026-11-04）

为什么不直接用技能的 tidy --apply：
  技能会把每个文件移到 history/<clean_stem>/ 顶层新目录，会打乱本项目
  已有的按类型分组（lives / tools / tvbox_clean / ...），且对
  「20261031_v2.0_移动CDN-111流.m3u」这类前缀日期 + 中文说明的命名，
  clean_stem 得不到正确主名。故保留分组、就地规范命名 + 补台账。

做四件事（默认 dry-run，加 --apply 才动手）：
  1) 解析每个历史版本文件名 → 版本号 / 原文件名 / 变更说明 / 归档时间
  2) 就地重命名为规范格式  <原文件名>_v<版本>_<YYYYMMDD-HHmm>.<ext>
  3) 每个分组目录写 manifest.json：version / archived_at / note / status /
     md5 / size / source_path / superseded_by（可追溯 + 可判断是否有效）
  4) 生成全局 history/INDEX.md（一眼看清哪些还有效、哪些已取代）

命名规范（写进 history/README.md）：
  history/<分组>/<原文件名>_v<版本号>_<YYYYMMDD-HHmm>.<扩展名>
  版本号取原文件名里的 vX.Y；时间取文件 mtime；中文变更说明进 manifest 的 note。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "history")
INDEX = os.path.join(HIST, "INDEX.md")
SPEC = os.path.join(HIST, "README.md")

# 分组 → 该组默认原文件名（当文件名里看不出脚本名时用）
GROUP_STEM = {
    "lives": "main",
    "tools": "",            # tools 组必须从文件名里解析脚本名
    "tvbox_clean": "tvbox_clean",
    "tvbox_curated": "tvbox_curated",
    "tvbox_sites": "tvbox_sites",
    "tvbox_subscription": "tvbox_subscription",
    "legacy": "legacy",
}
# tools 组里已知的脚本名（长名优先，避免 build_config 被 build 截走）
KNOWN = ["deploy_clean", "build_config", "build_live", "build_curated",
         "build_final", "codec_probe", "probe_streams", "speedtest",
         "vod_probe", "fetch_sources", "merge_pool", "refresh_all",
         "refresh", "probe", "verify_categories", "archive"]

FILE_RE = re.compile(r"^(\d{8})_v([\d.]+)_(.+)$")


def md5_of(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def parse(fn, group):
    stem, ext = os.path.splitext(fn)
    m = FILE_RE.match(stem)
    if not m:
        return None
    date, ver, rest = m.group(1), m.group(2), m.group(3)
    note, orig = rest, GROUP_STEM.get(group, group)
    if group == "tools":
        for k in sorted(KNOWN, key=len, reverse=True):
            if rest.startswith(k):
                orig = k
                note = rest[len(k):].lstrip("_- ") or "（无说明）"
                break
    else:
        # 非 tools 组：rest 就是纯变更说明
        note = rest
    return {"date": date, "version": "v" + ver, "orig": orig,
            "note": note.replace("_", " "), "ext": ext}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    entries = []      # 全局索引行
    plans = []        # (src, dst, meta)

    print("=== history/ 一次性整理（%s）===\n" % ("执行" if a.apply else "预演 dry-run"))
    for group in sorted(os.listdir(HIST)):
        box = os.path.join(HIST, group)
        if not os.path.isdir(box) or group.startswith("_"):
            continue
        for fn in sorted(os.listdir(box)):
            src = os.path.join(box, fn)
            if not os.path.isfile(src) or fn in ("manifest.json", "README.md", "INDEX.md"):
                continue
            meta = parse(fn, group)
            if not meta:
                print(f"  ? 跳过（不符合命名格式）: {group}/{fn}")
                continue
            mt = datetime.fromtimestamp(os.path.getmtime(src))
            stamp = mt.strftime("%Y%m%d-%H%M")
            newfn = f'{meta["orig"]}_{meta["version"]}_{stamp}{meta["ext"]}'
            dst = os.path.join(box, newfn)
            n = 1
            while dst != src and os.path.exists(dst):
                dst = os.path.join(box, f'{meta["orig"]}_{meta["version"]}_{stamp}_{n}{meta["ext"]}')
                n += 1
            row = {
                "version": meta["version"],
                "archived_at": mt.strftime("%Y-%m-%d %H:%M:%S"),
                "source_path": os.path.relpath(src, ROOT),
                "file": os.path.relpath(dst, ROOT),
                "size": os.path.getsize(src),
                "md5": md5_of(src),
                "note": meta["note"],
                "status": "invalid",       # 历史版本默认"已被取代"
                "milestone": meta["version"] in ("v1.0", "v2.0"),  # 大版本长期保留
                "superseded_by": "",
                "_group": group,
            }
            plans.append((src, dst, row))

    print(f"可归位 {len(plans)} 个历史版本：")
    for src, dst, row in plans[:12]:
        print(f"  {os.path.basename(src):<46} -> {os.path.basename(dst)}")
    if len(plans) > 12:
        print(f"  … 其余 {len(plans)-12} 个")

    if not a.apply:
        print("\n这是预演，未改动任何文件。确认后加 --apply 执行。")
        return

    # ① 就地重命名
    for src, dst, row in plans:
        if src != dst:
            shutil.move(src, dst)

    # ② 每组写 manifest.json
    by_group = {}
    for _src, _dst, row in plans:
        by_group.setdefault(row["_group"], []).append(row)
    for group, rows in by_group.items():
        rows.sort(key=lambda r: (r["version"], r["archived_at"]))
        manifest = {"name": group,
                    "naming": "<原文件名>_v<版本号>_<YYYYMMDD-HHmm>.<扩展名>",
                    "note": "status=valid 仍有效 / invalid 已被取代；milestone 里程碑长期保留",
                    "entries": [{k: v for k, v in r.items() if k != "_group"} for r in rows]}
        with open(os.path.join(HIST, group, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        entries.extend(rows)

    # ③ 全局索引
    lines = ["# 历史版本索引（自动生成，勿手改）", "",
             f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
             f"共 {len(entries)} 个版本 / {len(by_group)} 个分组", "",
             "| 分组 | 原文件 | 版本 | 归档时间 | 是否仍有效 | 里程碑 | 变更说明 | 路径 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in sorted(entries, key=lambda x: (x["_group"], x["version"], x["archived_at"])):
        lines.append("| %s | %s | %s | %s | %s | %s | %s | `%s` |" % (
            r["_group"], os.path.basename(r["file"]).split("_v")[0], r["version"],
            r["archived_at"], "✅有效" if r["status"] == "valid" else "❌已取代",
            "⭐" if r["milestone"] else "", r["note"].replace("|", "/"), r["file"]))
    lines += ["", "## 保留与清理策略", "",
              "- **里程碑（v1.0 / v2.0）**：长期保留，不参与清理，⭐ 标注；",
              "- **普通版本**：只保留最近 5 个；已标记「已取代」且超过 90 天 → 清理候选；",
              "- 清理一律先 `prune` 预演列清单，确认后软删除进 `history/_trash/YYYY-MM-DD/`（可恢复），",
              "  只有明确 `--hard` 才真删；",
              "- 归档区**只进不出**，删前必查 `tools/`、`README.md`、`.github/workflows/` 的引用。", ""]
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ④ 规范文档
    spec = """# history/ 目录结构与归档规范

## 目录结构
```
history/
├─ INDEX.md              ← 全局索引（自动生成，一眼看清所有版本）
├─ README.md             ← 本文件（规范说明）
├─ _trash/YYYY-MM-DD/    ← 软删除落点（可恢复，非硬删）
└─ <分组>/               ← 按原文件类型分组
   ├─ manifest.json      ← 该组版本台账（版本号/时间/说明/是否有效/md5）
   └─ <原文件名>_v<版本号>_<YYYYMMDD-HHmm>.<扩展名>
```
现有分组：`lives`（main.m3u）、`tools`（各脚本）、`tvbox_clean`、
`tvbox_curated` / `tvbox_sites` / `tvbox_subscription`（旧配置）、`legacy`。

## 命名规范
`<原文件名>_v<版本号>_<YYYYMMDD-HHmm>.<扩展名>`
- 版本号：`v1` / `v2.2`，来自原文件名里的 `vX.Y`
- 时间戳：文件 mtime，放**最后**，天然按时间排序、不会重名
- 原文件名里的中文变更说明不再塞进文件名，改存 `manifest.json` 的 `note`

## 归档流程（半自动）
```bash
# 产出新版本后，把被取代的旧版归档
python ~/.workbuddy/skills/file-version-archive/scripts/archive.py archive 旧文件.md \\
  --root . --note "改了什么" --status invalid
# 重要节点标里程碑（长期保留）
python .../archive.py archive 里程碑.json --root . --version v3.0 --milestone --status valid
# 查看台账 / 清理预演
python .../archive.py list --root .
python .../archive.py prune --root .
```
本项目专用的一次性批量归位脚本：`python tools/tidy_history_once.py --apply`。

## 可追溯信息（manifest.json 每条）
`version` / `archived_at` / `source_path` / `file` / `size` + `md5` /
`note`（变更说明）/ `status`（valid 仍有效、invalid 已取代）/ `milestone` /
`superseded_by`（被谁取代）。

## 保留与清理策略
- 里程碑版本（v1.0 / v2.0 等大版本）**永久保留**，不参与清理
- 默认只保留最近 **5 个**普通版本
- 非里程碑 + 已标记 `invalid` + 超过 **90 天** → 清理候选
- 清理前必须 dry-run 列清单；默认**软删除**到 `history/_trash/YYYY-MM-DD/`，可恢复
- `history/` 只进不出；删除前 grep 全仓引用，避免 CI 引用了被删路径
"""
    with open(SPEC, "w", encoding="utf-8") as f:
        f.write(spec)

    print(f"\n完成：重命名 {len(plans)} 个文件，{len(by_group)} 份 manifest.json，"
          f"生成 INDEX.md 与 README.md")


if __name__ == "__main__":
    main()
