#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布最终版到 anbola/tvbox：上传新文件 + 删除仓库里所有旧/多余文件。

令牌只从环境变量 ANBOLA_TOKEN 读取，绝不写入任何文件。
用法：ANBOLA_TOKEN=xxx python tools/deploy_clean.py
"""
import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.environ.get("TVBOX_REPO", "anbola/tvbox")
BRANCH = os.environ.get("TVBOX_BRANCH", "main")
MSG = "rebuild: 单一配置 + 逐条实测可播直播源；清理全部旧文件"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

TOK = os.environ.get("ANBOLA_TOKEN", "").strip()
if not TOK:
    # 允许从本地 token 文件读取（该文件已加入 .gitignore，不会进仓库）
    for cand in ("anbola_token.txt", ".anbola_token"):
        p = os.path.join(ROOT, cand)
        if os.path.exists(p):
            TOK = open(p, encoding="utf-8").read().strip()
            break
if not TOK:
    print("x 缺少令牌：请设置环境变量 ANBOLA_TOKEN，或在项目根目录放 anbola_token.txt")
    sys.exit(1)

# 需要上传的 (仓库路径, 本地路径)
UPLOAD = [
    ("tvbox_clean.json", "tvbox_clean.json"),
    ("lives/main.m3u", "lives/main.m3u"),
    ("lives/pool.m3u", "lives/pool.m3u"),
    ("tools/fetch_sources.py", "tools/fetch_sources.py"),
    ("tools/merge_pool.py", "tools/merge_pool.py"),
    ("tools/speedtest.py", "tools/speedtest.py"),
    ("tools/build_live.py", "tools/build_live.py"),
    ("tools/vod_probe.py", "tools/vod_probe.py"),
    ("tools/build_config.py", "tools/build_config.py"),
    ("tools/refresh_all.py", "tools/refresh_all.py"),
    ("tools/deploy_clean.py", "tools/deploy_clean.py"),
    ("refresh.bat", "refresh.bat"),
    ("README.md", "README.md"),
    (".github/workflows/refresh.yml", ".github/workflows/refresh.yml"),
    (".nojekyll", ".nojekyll"),
]

# 需要从仓库删除的旧文件
DELETE = [
    "tools/build_final.py", "tools/probe_streams.py",
    "tools/build_curated.py", "tools/clean_lives.py", "tools/fetch_raw.py",
    "tools/verify_categories.py", "tools/probe_new_sources.py", "tools/probe_lives.py",
    "tools/autoheal_lives.py", "tools/make_mytv.py", "tools/make_fast.py",
    ".github/workflows/discover-sources.yml",
    ".github/workflows/update-lives.yml",
    ".github/workflows/verify-curated.yml",
    "tvbox_sites.json", "tvbox_subscription.json", "tvbox_curated.json",
    "tvbox_multisource.json", "tvbox_lives.json",
    "mytv.m3u", "mytv_lite.m3u", "status.html", "probe_new_sources.json",
    "lives/bestfan_clean.m3u", "lives/bigbig_clean.m3u", "lives/ccsh_clean.m3u",
    "lives/cn_clean.m3u", "lives/fast.m3u", "lives/guovin_clean.m3u",
    "lives/kimentanm_clean.m3u", "lives/mzky_clean.m3u", "lives/vamos_clean.m3u",
    "lives/yang_clean.m3u", "lives/yanggather_clean.m3u", "lives/yuechan_clean.m3u",
    "lives/zbds4_clean.m3u", "维护手册.md",
    ".workbuddy/skills/anbola-tvbox/SKILL.md",
]


def api(method, path, data=None):
    url = path if path.startswith("http") else "https://api.github.com" + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": "Bearer " + TOK,
        "Accept": "application/vnd.github+json",
        "User-Agent": "tvbox-deployer",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=45, context=CTX) as r:
            b = r.read().decode("utf-8", "ignore")
            return r.getcode(), (json.loads(b) if b else {})
    except urllib.error.HTTPError as e:
        b = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(b)
        except Exception:
            return e.code, {"message": b[:200]}
    except Exception as e:
        return 0, {"message": "%s: %s" % (type(e).__name__, e)}


def get_sha(path):
    code, cur = api("GET", "/repos/%s/contents/%s?ref=%s" % (REPO, path, BRANCH))
    return cur.get("sha") if code == 200 else None


def main():
    code, me = api("GET", "/user")
    if code != 200:
        print("x 令牌无效:", me.get("message"))
        return 1
    print("身份:", me.get("login"), "| 仓库:", REPO, "| 分支:", BRANCH)

    print("\n[1/2] 上传:")
    ok = 0
    for remote, local in UPLOAD:
        lp = os.path.join(ROOT, local)
        if not os.path.exists(lp):
            print("  - %-32s 本地缺失，跳过" % remote)
            continue
        with open(lp, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        payload = {"message": MSG, "content": content, "branch": BRANCH}
        sha = get_sha(remote)
        if sha:
            payload["sha"] = sha
        code, res = api("PUT", "/repos/%s/contents/%s" % (REPO, remote), payload)
        if code in (200, 201):
            print("  v %-32s %8dB" % (remote, os.path.getsize(lp)))
            ok += 1
        else:
            print("  x %-32s %s" % (remote, str(res.get("message"))[:110]))

    print("\n[2/2] 删除旧文件:")
    deleted = 0
    for path in DELETE:
        sha = get_sha(path)
        if not sha:
            continue  # 本来就不存在
        code, res = api("DELETE", "/repos/%s/contents/%s" % (REPO, path),
                        {"message": MSG, "sha": sha, "branch": BRANCH})
        if code in (200, 201):
            print("  - %s" % path)
            deleted += 1
        else:
            print("  x %-40s %s" % (path, str(res.get("message"))[:90]))
    print("上传 %d 个，删除 %d 个" % (ok, deleted))

    print("\n等待 Pages 构建:")
    for i in range(40):
        time.sleep(8)
        code, b = api("GET", "/repos/%s/pages/builds/latest" % REPO)
        st = b.get("status", "?")
        if st == "built":
            print("  v 构建完成")
            break
        if st == "errored":
            print("  x 构建失败，手动重触发 ...")
            api("POST", "/repos/%s/pages/builds" % REPO)
        if i % 5 == 0:
            print("  ...", st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
