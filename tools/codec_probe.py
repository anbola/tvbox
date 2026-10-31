#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探测每条直播流的真实编码（H.264 / H.265）与分辨率。

为什么要做：微鲸 WTV55K1（Android 5.0.2 / MStar muji）在解「高清2K」这类
H.265 高码率流时，MediaCodec 会直接 SIGABRT 把整个 App 干掉（实测崩溃日志
Fatal signal 6 in tid MediaCodec_loop）。所以必须按「设备真实能解」来筛。

做法：下载 m3u8 的第一个 TS 分片 → 对齐 188 字节包 → 解析 PAT/PMT 拿
stream_type（0x1B=H.264, 0x24=H.265）→ 对 H.264 再解 SPS 拿分辨率。

输入：_probe/speeds.json（speedtest.py 产出，含可播流列表）
输出：_probe/codecs.json  [{url,name,kbps,codec,w,h,ok}]
"""
import json
import os
import re
import ssl
import struct
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = "okhttp/3.15.0"
AUDIO_NAME = {0x03: "mp3", 0x04: "mp3", 0x0F: "aac", 0x11: "aac-latm",
              0x81: "ac3", 0x87: "eac3"}


def fetch(url, limit=1500000, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read(limit)


def first_segment(m3u8_url):
    txt = fetch(m3u8_url, 60000).decode("utf-8", "ignore")
    for line in txt.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            base = m3u8_url.rsplit("/", 1)[0]
            return base + "/" + line
    return None


def align_ts(buf):
    """TS 包未必从边界开始，先找到第一处连续 3 个 0x47 相隔 188 的位置。"""
    for i in range(0, min(len(buf) - 376, 188 * 4)):
        if (buf[i] == 0x47 and buf[i + 188] == 0x47 and buf[i + 376] == 0x47
                and (i + 564 >= len(buf) or buf[i + 564] == 0x47)):
            return buf[i:]
    return None


def packets(buf):
    for i in range(0, len(buf) - 187, 188):
        if buf[i] == 0x47:
            yield buf[i:i + 188]


def payload_of(p):
    afc = (p[3] >> 4) & 0x3
    off = 4
    if afc in (2, 3):
        off = 5 + p[4]
    if off >= 188:
        return b"", False
    pusi = (p[1] >> 6) & 1
    if pusi:
        ptr = p[off]
        return p[off + 1 + ptr:], True
    return p[off:], False


def parse_pat(buf):
    for p in packets(buf):
        pid = ((p[1] & 0x1F) << 8) | p[2]
        if pid != 0:
            continue
        body, pusi = payload_of(p)
        if not pusi or len(body) < 12:
            continue
        slen = ((body[1] & 0x0F) << 8) | body[2]
        sec = body[3:3 + slen - 4]
        i = 0
        while i + 4 <= len(sec):
            prog = (sec[i] << 8) | sec[i + 1]
            pmt = ((sec[i + 2] & 0x1F) << 8) | sec[i + 3]
            if prog != 0:
                return pmt
            i += 4
    return None


def parse_pmt(buf, pmt_pid):
    for p in packets(buf):
        pid = ((p[1] & 0x1F) << 8) | p[2]
        if pid != pmt_pid:
            continue
        body, pusi = payload_of(p)
        if not pusi or len(body) < 16:
            continue
        slen = ((body[1] & 0x0F) << 8) | body[2]
        sec = body[0:3 + slen]        # 含 table_id 的完整 section
        if len(sec) < 16:
            continue
        pil = ((sec[10] & 0x0F) << 8) | sec[11]
        k = 12 + pil
        vid = None
        audios = []
        while k + 5 <= len(sec):
            st = sec[k]
            esil = ((sec[k + 3] & 0x0F) << 8) | sec[k + 4]
            if vid is None and st in (0x1B, 0x24):
                vid = st
            elif st in (0x03, 0x04, 0x0F, 0x11, 0x81, 0x87):
                audios.append(st)
            k += 5 + esil
        return vid, audios
    return None


def bs_read_sps(nal):
    """极简 Exp-Golomb：只取到分辨率为止（H.264 SPS）。"""
    bits = []
    for b in nal:
        bits.extend((b >> s) & 1 for s in range(7, -1, -1))
    pos = [0]

    def u(n):
        v = 0
        for _ in range(n):
            if pos[0] >= len(bits):
                raise ValueError
            v = (v << 1) | bits[pos[0]]
            pos[0] += 1
        return v

    def ue():
        z = 0
        while pos[0] < len(bits) and bits[pos[0]] == 0:
            z += 1
            pos[0] += 1
        if pos[0] >= len(bits):
            raise ValueError
        pos[0] += 1
        return (1 << z) - 1 + u(z)

    def se():
        k = ue()
        return (k + 1) // 2 if k % 2 else -(k // 2)

    u(8)                    # profile_idc
    u(8)                    # constraint flags
    u(8)                    # level_idc
    ue()                    # seq_parameter_set_id
    prof = nal[0] if nal else 0
    if prof in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135):
        chroma = ue()
        if chroma == 3:
            u(1)
        ue()
        ue()
        u(1)
        if u(1):
            n = 8 if chroma != 3 else 12
            for i in range(n):
                if u(1):
                    last = 8
                    nxt = 8
                    for _ in range(16 if i < 6 else 64):
                        if nxt:
                            nxt = (last + se() + 256) % 256
                        last = nxt if nxt else last
    ue()                    # log2_max_frame_num_minus4
    poc = ue()
    if poc == 0:
        ue()
    elif poc == 1:
        u(1)
        se()
        se()
        for _ in range(ue()):
            se()
    ue()                    # max_num_ref_frames
    u(1)                    # gaps_in_frame_num
    w_mbs = ue() + 1
    h_map = ue() + 1
    frame_mbs_only = u(1)
    if not frame_mbs_only:
        u(1)
    u(1)                    # direct_8x8
    if u(1):                # cropping
        l, r, t, b = ue(), ue(), ue(), ue()
    else:
        l = r = t = b = 0
    w = w_mbs * 16 - (l + r) * 2
    h = (2 - frame_mbs_only) * h_map * 16 - (t + b) * 2 * (2 - frame_mbs_only)
    return w, h


def sps_from_ts(buf, vid_type):
    """从 TS 负载里找 SPS。H.264: NAL 7；H.265: VPS/SPS(32/33) 暂不解，返回 None。"""
    if vid_type != 0x1B:
        return None
    for p in packets(buf):
        body, _ = payload_of(p)
        i = body.find(b"\x00\x00\x01")
        while i >= 0:
            if i + 3 < len(body) and (body[i + 3] & 0x1F) == 7:
                nal = body[i + 4:i + 200]
                # 去掉防竞争字节 00 00 03
                nal = nal.replace(b"\x00\x00\x03", b"\x00\x00")
                try:
                    return bs_read_sps(nal)
                except Exception:
                    return None
            i = body.find(b"\x00\x00\x01", i + 3)
    return None


def probe(item):
    url = item["url"]
    out = dict(name=item.get("name"), url=url, kbps=item.get("kbps"),
               codec=None, w=None, h=None, audio=[], ok=False)
    try:
        seg = first_segment(url)
        if not seg:
            return out
        data = align_ts(fetch(seg))
        if not data:
            return out
        pmt = parse_pat(data)
        if not pmt:
            return out
        res = parse_pmt(data, pmt)
        if not res:
            return out
        vid, audios = res
        if not vid:
            return out
        out["codec"] = {0x1B: "avc", 0x24: "hevc", 0x02: "mpeg2"}.get(vid, hex(vid))
        # 音频编码同样关键：MP3(0x03/0x04) 会让本机 ACodec 直接 abort（见 CHANGELOG v2.2）
        out["audio"] = [AUDIO_NAME.get(a, hex(a)) for a in sorted(set(audios))]
        wh = sps_from_ts(data, vid)
        if wh:
            out["w"], out["h"] = wh
        out["ok"] = True
        return out
    except Exception as e:
        out["err"] = type(e).__name__
        return out


def main():
    speed = json.load(open(os.path.join(ROOT, "_probe", "speeds.json"), encoding="utf-8"))
    items = [r for r in speed if r.get("ok")]
    print(f"待探测 {len(items)} 条流…")
    with ThreadPoolExecutor(max_workers=24) as ex:
        res = list(ex.map(probe, items))
    out = os.path.join(ROOT, "_probe", "codecs.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    ok = [r for r in res if r["ok"]]
    print(f"识别成功 {len(ok)}/{len(res)}")
    stat = {}
    for r in ok:
        k = f'{r["codec"]} {r["w"]}x{r["h"]} audio={",".join(r.get("audio") or [])}'
        stat[k] = stat.get(k, 0) + 1
    for k, v in sorted(stat.items(), key=lambda x: -x[1]):
        print(f"  {k:<20} {v} 条")
    print(f"已写入 {out}")


if __name__ == "__main__":
    main()
