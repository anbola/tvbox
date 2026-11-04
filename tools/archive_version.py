#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本归档与整理（半自动，默认 dry-run，加 --apply 才动手）

对应 history/README.md 的规范。三个子命令：

  python tools/archive_version.py archive v3.1 --note "改了什么" --milestone --apply
      把当前在用版本完整快照到 history/<版本>_<YYYYMMDD>/，
      生成 MANIFEST.md（版本号/时间/变更说明/有效性/里程碑/MD5/保留策略）
      + manifest.json（机器可读），并自动追加 CHANGELOG.md 和 INDEX.md 条目。

  python tools/archive_version.py tidy --apply
      把散落在 history/ 顶层、不符合命名规范的旧文件归位到分组目录，
      重命名为 <原文件名>_v<版本>_<YYYYMMDD-HHmm>.<ext>，补台账与索引。

  python tools/archive_version.py clean-cache --apply
      删除 tools/__pycache__/ 与 tools/*.pyc（Python 字节码缓存，无保留价值）。

设计原则：history/ 只进不出；不硬删任何历史版本；
过期版本先由 history/README.md 的策略判断，清理一律走软删除到 _trash/。
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "history")
SUBSCRIBE_URL = "https://anbola.github.io/tvbox/tvbox_clean.json"

# 每次发布要归档的「当前在用版本」完整快照
FILES = [
    "tvbox_clean.json",
    "lives/main.m3u",
    "lives/public.m3u",
    "README.md",
    "status.json",
    "tools/tv_speedtest.py",
    "tools/optimize_tv.py",
    "tools/build_config.py",
    "tools/build_live.py",
    "tools/build_public.py",
    "tools/check_address.py",
    "tools/address.py",
    "tools/healthcheck.py",
    "tools/deploy_clean.py",
    "tools/archive_version.py",
    "tools/tidy_history_once.py",
    ".github/workflows/refresh.yml",
    ".github/workflows/keepalive.yml",
    ".github/workflows/healthcheck.yml",
    ".workbuddy/skills/anbola-tvbox/SKILL.md",
]

GROUP_OF = {"README": "README", "refresh": "refresh"}


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def flat_name(rel):
    return rel.replace("/", "__").replace("\\", "__")


def cmd_archive(args):
    stamp = datetime.now()
    day = stamp.strftime("%Y%m%d")
    dest = os.path.join(HIST, f"{args.version}_{day}")
    rows, missing = [], []
    for rel in FILES:
        src = os.path.join(ROOT, rel)
        if not os.path.exists(src):
            missing.append(rel)
            continue
        rows.append({"source": rel, "archived": flat_name(rel),
                     "size": os.path.getsize(src), "md5": md5(src)})
    print(f"[archive] {args.version} → {os.path.relpath(dest, ROOT)}")
    print(f"          收录 {len(rows)} 个文件" +
          (f"，缺失 {len(missing)}: {missing}" if missing else ""))
    if not args.apply:
        for r in rows:
            print("   +", r["archived"])
        return

    os.makedirs(dest, exist_ok=True)
    for r in rows:
        shutil.copy2(os.path.join(ROOT, r["source"]),
                     os.path.join(dest, r["archived"]))

    now = stamp.strftime("%Y-%m-%d %H:%M:%S")
    status = "✅ 有效" if not args.superseded else "❌ 已被取代"
    milestone = "⭐ 长期保留" if args.milestone else "普通版本"
    manifest = {
        "version": args.version, "archived_at": now,
        "status": "valid" if not args.superseded else "invalid",
        "milestone": bool(args.milestone),
        "note": args.note, "subscription": SUBSCRIBE_URL,
        "superseded_by": args.superseded or None,
        "files": rows,
    }
    with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    lines = [
        f"# {args.version} 快照 —— {stamp.strftime('%Y-%m-%d')}", "",
        f"归档时间：{now}", f"状态：**{status}**", f"里程碑：**{milestone}**",
        f"订阅地址：`{SUBSCRIBE_URL}`（永久固定，归档不影响线上）", "",
        "## 本次变更说明", "", args.note or "（未填写）", "",
        "## 文件清单（含 MD5，可校验）", "",
        "| 原路径 | 大小 | MD5 |", "|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| `{r['source']}` | {r['size']}B | `{r['md5']}` |")
    lines += ["", "## 保留与回退", "",
              "- 里程碑快照永久保留，不参与 `prune` 清理；普通版本按 history/README.md 策略处理。",
              "- 回退：把本目录对应文件复制回原路径（文件名里的 `__` 还原为 `/`）。",
              "- `manifest.json` 为机器可读台账：version / archived_at / status / "
              "milestone / note / size / md5 / superseded_by。", ""]
    with open(os.path.join(dest, "MANIFEST.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # CHANGELOG：插到第一个 ## 之前
    cp = os.path.join(HIST, "CHANGELOG.md")
    txt = io.open(cp, encoding="utf-8").read() if os.path.exists(cp) else "# 变更记录 (CHANGELOG)\n\n"
    block = (f"## {args.version} — {now}"
             f"（{'✅ 当前有效' if not args.superseded else '❌ 已取代'}"
             f"{' · ⭐里程碑' if args.milestone else ''}）\n\n"
             f"**线上订阅地址不变**：`{SUBSCRIBE_URL}`\n\n"
             f"{args.note or '（未填写）'}\n\n"
             f"归档实体：`history/{os.path.basename(dest)}/`（{len(rows)} 文件 + "
             f"MANIFEST.md + manifest.json）\n\n")
    m = re.search(r"^## ", txt, re.M)
    txt = (txt[:m.start()] + block + txt[m.start():]) if m else (txt + "\n" + block)
    with open(cp, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)

    # INDEX：插到表格最后一行之后
    ip = os.path.join(HIST, "INDEX.md")
    itxt = io.open(ip, encoding="utf-8").read() if os.path.exists(ip) else ""
    row = (f"| 全量快照 | {args.version} | {now} | "
           f"{'✅有效' if not args.superseded else '❌已取代'} | "
           f"{'⭐' if args.milestone else ''} | {args.note or ''} | "
           f"`history\\{os.path.basename(dest)}\\MANIFEST.md` |")
    ls = itxt.splitlines()
    last = max((i for i, l in enumerate(ls) if l.startswith("|")), default=-1)
    ls.insert(last + 1, row) if last >= 0 else ls.append(row)
    with open(ip, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(ls) + "\n")
    print(f"          已写 MANIFEST.md / manifest.json / CHANGELOG / INDEX")


def cmd_tidy(args):
    pat = re.compile(r"^(\d{8})_v([\d.]+)_([A-Za-z0-9_\-]+)\.(\w+)$")
    found = []
    for fn in sorted(os.listdir(HIST)):
        m = pat.match(fn)
        if not m or not os.path.isfile(os.path.join(HIST, fn)):
            continue
        date, ver, stem, ext = m.groups()
        p = os.path.join(HIST, fn)
        ts = datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y%m%d-%H%M")
        group = GROUP_OF.get(stem, "legacy")
        newname = f"{stem}_v{ver}_{ts}.{ext}"
        found.append((fn, group, newname, date, ver, ts, p))
    print(f"[tidy] history/ 顶层散落旧文件 {len(found)} 个")
    for fn, group, newname, *_ in found:
        print(f"   {fn}  →  history/{group}/{newname}")
    if not args.apply or not found:
        return

    for fn, group, newname, date, ver, ts, src in found:
        gd = os.path.join(HIST, group)
        os.makedirs(gd, exist_ok=True)
        dst = os.path.join(gd, newname)
        if os.path.exists(dst):
            print("   ! 已存在，跳过:", dst)
            continue
        shutil.move(src, dst)
        mp = os.path.join(gd, "manifest.json")
        data = json.load(io.open(mp, encoding="utf-8")) if os.path.exists(mp) else []
        if isinstance(data, dict):
            # 老台账可能是单条 dict 或 {"versions":[...]}，绝不能丢原有记录
            data = data.get("versions") or ([data] if data else [])
        data.append({"version": f"v{ver}",
                     "archived_at": f"{date[:4]}-{date[4:6]}-{date[6:]} {ts[-4:-2]}:{ts[-2:]}",
                     "file": newname, "size": os.path.getsize(dst), "md5": md5(dst),
                     "status": "invalid", "milestone": False,
                     "note": "由 history/ 顶层散落文件批量归位", "source_path": fn})
        with open(mp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    # INDEX 追加归位条目
    ip = os.path.join(HIST, "INDEX.md")
    itxt = io.open(ip, encoding="utf-8").read() if os.path.exists(ip) else ""
    ls = itxt.splitlines()
    last = max((i for i, l in enumerate(ls) if l.startswith("|")), default=-1)
    for fn, group, newname, date, ver, ts, _ in found:
        row = (f"| {group} | v{ver} | {date[:4]}-{date[4:6]}-{date[6:]} | ❌已取代 |  | "
               f"散落文件归位 | `history\\{group}\\{newname}` |")
        last += 1
        ls.insert(last, row)
    with open(ip, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(ls) + "\n")
    print("          已归位并补 manifest.json / INDEX.md")


def cmd_clean_cache(args):
    targets = []
    pc = os.path.join(ROOT, "tools", "__pycache__")
    if os.path.isdir(pc):
        targets += [os.path.join(pc, f) for f in os.listdir(pc) if f.endswith(".pyc")]
    td = os.path.join(ROOT, "tools")
    targets += [os.path.join(td, f) for f in os.listdir(td) if f.endswith(".pyc")]
    print(f"[clean-cache] Python 字节码缓存 {len(targets)} 个"
          + ("（__pycache__ 目录将一并移除）" if os.path.isdir(pc) else ""))
    if not args.apply:
        return
    for p in targets:
        os.remove(p)
    if os.path.isdir(pc) and not os.listdir(pc):
        os.rmdir(pc)
    print("          已清理")


def main():
    ap = argparse.ArgumentParser(description="版本归档与整理")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("archive", help="归档当前在用版本")
    a.add_argument("version", help="如 v3.1")
    a.add_argument("--note", default="", help="变更说明")
    a.add_argument("--milestone", action="store_true", help="标为里程碑，永久保留")
    a.add_argument("--superseded", default="", help="被哪个版本取代")
    a.add_argument("--apply", action="store_true")
    t = sub.add_parser("tidy", help="归位 history/ 顶层散落旧文件")
    t.add_argument("--apply", action="store_true")
    c = sub.add_parser("clean-cache", help="清理 tools 下 pyc 缓存")
    c.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    {"archive": cmd_archive, "tidy": cmd_tidy,
     "clean-cache": cmd_clean_cache}[args.cmd](args)
    if not args.apply:
        print("\n（dry-run，未改动任何文件；确认无误后加 --apply）")


if __name__ == "__main__":
    main()
