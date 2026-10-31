#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键刷新流水线：抓取 → 测速 → 生成直播源 → 点播体检 → 生成配置 → 发布

必须在【你自己的电脑/电视所在网络】上跑，测速结果才真实有效。
（GitHub 的服务器在国外，在那边测速对移动 IPTV 毫无意义）

用法：
  python tools/refresh_all.py              # 全流程（含测速，约 5-15 分钟）
  python tools/refresh_all.py --no-vod     # 只更新直播，不动点播
  python tools/refresh_all.py --deploy     # 完成后推送到 GitHub
  python tools/refresh_all.py --skip-fetch # 用已有候选池，不重新抓
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable or "python3"


def run(title, args, optional=False):
    print("\n" + "=" * 66)
    print(f"▶ {title}")
    print("=" * 66)
    t0 = time.time()
    p = subprocess.run([PY] + args, cwd=ROOT)
    dt = time.time() - t0
    if p.returncode != 0:
        print(f"✗ 失败（{dt:.0f}s，退出码 {p.returncode}）")
        if not optional:
            sys.exit(p.returncode)
        return False
    print(f"✓ 完成（{dt:.0f}s）")
    return True


def main():
    argv = sys.argv[1:]
    do_deploy = "--deploy" in argv
    skip_fetch = "--skip-fetch" in argv
    no_vod = "--no-vod" in argv

    t_all = time.time()
    print("TVBox 源刷新流水线")
    print(f"工作目录: {ROOT}")

    # ① 抓取候选源
    if not skip_fetch:
        run("① 抓取候选直播源", ["tools/fetch_sources.py"], optional=True)

    # ② 真实测速（核心）
    run("② 逐条测速（下载真实分片算码率）", ["tools/speedtest.py"])

    # ③ 按速度生成直播源
    run("③ 生成 lives/main.m3u（按实测速度排序）", ["tools/build_live.py"])

    # ④ 点播站体检
    if not no_vod:
        run("④ 点播站体检（API 延迟 + 视频分片测速）", ["tools/vod_probe.py"], optional=True)

    # ⑤ 生成最终配置
    run("⑤ 生成 tvbox_clean.json", ["tools/build_config.py"], optional=no_vod)

    # ⑥ 发布
    if do_deploy:
        run("⑥ 发布到 GitHub", ["tools/deploy_clean.py"], optional=True)
    else:
        print("\n（未发布。加 --deploy 可推送到 GitHub）")

    print(f"\n全部完成，总用时 {time.time()-t_all:.0f}s")


if __name__ == "__main__":
    main()
