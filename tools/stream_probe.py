# -*- coding: utf-8 -*-
"""直播线路真实画质探测（ffprobe）——电视端 16:9 / 高清优选的数据底座。

为什么需要它：
  仓库原有的 `_probe/codecs2.json` 只覆盖 74 条线路，且大多是公网 9901 线路；
  家里电视实际走的 `dbiptv.sn.chinamobile.com` 内网极速线几乎没被探过，
  于是 build_live.py 里 "1080p / avc 优先" 的排序对这些线路等于没生效。
  本工具用本机 ffprobe 逐条拉流，拿到真实宽高、显示宽高比、编码、帧率、音频编码。

用法：
  python tools/stream_probe.py                       # 探 lives/main.m3u 全部线路
  python tools/stream_probe.py lives/public.m3u     # 探指定文件
  python tools/stream_probe.py --urls u1 u2 ...     # 探指定 URL
  python tools/stream_probe.py --workers 24 --timeout 14

输出：_probe/stream_quality.json  {url: {codec,w,h,dar,fps,audio,ok,hd169,score,...}}
判定口径（电视优先，与项目约定一致）：
  - 16:9：显示宽高比 >= 1.65（16:9=1.778）；4:3=1.333 视为不合格（会出方屏）
  - 高清：高 >= 720（1080p 最佳）
  - 编码：avc/h264 优先；hevc 降级（部分老盒子不支持）；排除未知
  - 音频：含 mp3 降级（微鲸盒子 MP3 有解码器闪退历史）
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import io
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_probe", "stream_quality.json")
FFPROBE = os.environ.get(
    "FFPROBE", r"D:\GREENSOFT\ffmpeg-master-latest-win64-gpl-shared\bin\ffprobe.exe"
)
WORKERS = 20
TIMEOUT = 14


def urls_from_m3u(path: str) -> list[str]:
    with io.open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    out, seen = [], set()
    for l in lines:
        u = l.strip()
        if u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def classify(v: dict) -> dict:
    w, h = v.get("w"), v.get("h")
    dar = v.get("dar") or ""
    ratio = None
    if ":" in dar:
        try:
            a, b = dar.split(":")[:2]
            ratio = float(a) / float(b)
        except (ValueError, ZeroDivisionError):
            ratio = None
    if ratio is None and w and h:
        ratio = w / h
    codec = (v.get("codec") or "").lower()
    audio = [str(a).lower() for a in (v.get("audio") or [])]
    is169 = ratio is not None and ratio >= 1.65
    is_hd = bool(h and h >= 720)
    is_avc = codec in ("h264", "avc", "avc1")
    is_hevc = codec in ("hevc", "h265")
    no_mp3 = not any("mp3" in a for a in audio)
    # 打分只用于同一频道内排序，越大越好
    score = 0
    score += 1000 if is169 else 0
    score += 600 if h and h >= 1080 else (400 if is_hd else 0)
    score += 300 if is_avc else (50 if is_hevc else 0)
    score += 200 if no_mp3 else 0
    score += min(int(h or 0), 2160) / 100.0
    return {
        "ratio": round(ratio, 3) if ratio else None,
        "hd169": bool(is169 and is_hd),
        "is_169": bool(is169),
        "is_hd": is_hd,
        "is_avc": is_avc,
        "no_mp3": no_mp3,
        "score": round(score, 1),
    }


def probe_one(url: str, timeout: int) -> dict:
    t0 = time.time()
    cmd = [
        FFPROBE, "-v", "error",
        "-probesize", "1500000", "-analyzeduration", "3000000",
        "-i", url,
        "-show_entries",
        "stream=codec_type,codec_name,width,height,display_aspect_ratio,r_frame_rate",
        "-show_entries", "format=bit_rate",
        "-of", "json",
    ]
    rec = {"url": url, "ok": False, "probe_ms": None}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        rec["probe_ms"] = round((time.time() - t0) * 1000)
        if r.returncode != 0:
            rec["err"] = (r.stderr or "").strip()[:160] or f"rc={r.returncode}"
            return rec
        d = json.loads(r.stdout or "{}")
        streams = d.get("streams") or []
        vs = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not vs:
            rec["err"] = "无视频流"
            return rec
        rec.update({
            "ok": True,
            "codec": vs.get("codec_name"),
            "w": vs.get("width"), "h": vs.get("height"),
            "dar": vs.get("display_aspect_ratio"),
            "fps": vs.get("r_frame_rate"),
            "audio": [s.get("codec_name") for s in streams
                      if s.get("codec_type") == "audio"],
            "bitrate": (d.get("format") or {}).get("bit_rate"),
        })
        rec.update(classify(rec))
    except subprocess.TimeoutExpired:
        rec["probe_ms"] = round((time.time() - t0) * 1000)
        rec["err"] = "timeout"
    except Exception as e:
        rec["err"] = f"{type(e).__name__}:{str(e)[:100]}"
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="m3u/m3u8/txt 文件（相对项目根）")
    ap.add_argument("--urls", nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--timeout", type=int, default=TIMEOUT)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--append", action="store_true", help="与已有结果合并")
    a = ap.parse_args()

    if not os.path.isfile(FFPROBE):
        print(f"! 找不到 ffprobe: {FFPROBE}（可用 FFPROBE 环境变量指定）")
        return 2
    files = a.files or [os.path.join(ROOT, "lives", "main.m3u")]
    urls, seen = [], set()
    for p in files:
        fp = p if os.path.isabs(p) else os.path.join(ROOT, p)
        for u in urls_from_m3u(fp):
            if u not in seen:
                seen.add(u); urls.append(u)
    for u in a.urls:
        if u not in seen:
            seen.add(u); urls.append(u)

    old = {}
    if a.append and os.path.exists(a.out):
        try:
            old = json.load(io.open(a.out, encoding="utf-8"))
        except Exception:
            old = {}
    todo = [u for u in urls if u not in old]
    print(f"待探测 {len(todo)} 条（已有 {len(old)} 条）| 并发 {a.workers} | 超时 {a.timeout}s", flush=True)
    if not todo:
        print("无新增线路，直接复用已有结果")
        return 0

    res = dict(old)
    ex = cf.ThreadPoolExecutor(max_workers=a.workers)
    fut = {ex.submit(probe_one, u, a.timeout): u for u in todo}
    done = 0
    try:
        for f in cf.as_completed(fut, timeout=len(todo) * a.timeout / a.workers + 180):
            u = fut[f]
            try:
                res[u] = f.result()
            except Exception as e:
                res[u] = {"url": u, "ok": False, "err": f"{type(e).__name__}:{e}"}
            done += 1
            if done % 20 == 0 or done == len(todo):
                ok = sum(1 for v in res.values() if v.get("ok"))
                print(f"  进度 {done}/{len(todo)} | 成功 {ok}", flush=True)
    except cf.TimeoutError:
        print("! 整体超时，收尾已完成任务", flush=True)
    finally:
        # 关键：不用 with，避免 shutdown(wait=True) 被挂起的 ffprobe 拖死
        ex.shutdown(wait=False, cancel_futures=True)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with io.open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    ok = [v for v in res.values() if v.get("ok")]
    hd = [v for v in ok if v.get("hd169")]
    sq = [v for v in ok if not v.get("is_169")]
    print(f"\n探测完成：{len(res)} 条 | 成功 {len(ok)} | 16:9高清 {len(hd)} | 非16:9 {len(sq)}")
    print(f"结果 -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
