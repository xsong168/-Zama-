import argparse
import os
import random
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


FACTORY_ROOT = Path(r"C:\Users\GIGABYTE\Desktop\Junshi_Bot冷酷军师\Jiumo_Auto_Factory").resolve()
FINAL_OUT_DIR = Path(r"C:\Users\GIGABYTE\Desktop\Junshi_Bot冷酷军师\Final_Out").resolve()


LIQUOR_KEYWORDS = ["酒", "窖", "挂杯"]
MEDIA_KEYWORDS = ["认知", "流量", "博弈"]


@dataclass(frozen=True)
class Segment:
    src: Path
    start: float
    dur: float


def _ffprobe_duration_seconds(p: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(p),
        ],
        capture_output=True,
        timeout=15,
        encoding="utf-8",
        errors="ignore",
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {p} {r.stderr[-300:]}")
    s = (r.stdout or "").strip()
    if not s:
        raise RuntimeError(f"ffprobe 无时长输出: {p}")
    return max(0.1, float(s))


def _pick_bucket(script_text: str) -> str:
    t = (script_text or "")
    if any(k in t for k in LIQUOR_KEYWORDS):
        return "liquor"
    if any(k in t for k in MEDIA_KEYWORDS):
        return "media"
    # 默认：media（更通用的抽象素材）
    return "media"


def _list_video_assets(asset_dir: Path) -> list[Path]:
    exts = {".mp4", ".mov", ".m4v", ".webm"}
    if not asset_dir.exists():
        return []
    out: list[Path] = []
    for p in asset_dir.rglob("*"):
        try:
            if p.is_file() and p.suffix.lower() in exts:
                out.append(p)
        except Exception:
            continue
    return out


def _build_segments(*, audio_dur: float, assets: list[Path], cut_min: float, cut_max: float) -> list[Segment]:
    if not assets:
        return []

    # 缓存素材时长，避免重复探测
    dur_map: dict[Path, float] = {}

    segs: list[Segment] = []
    t = 0.0
    guard = 0
    while t < audio_dur - 0.05 and guard < 5000:
        guard += 1
        dur = random.uniform(cut_min, cut_max)
        rem = audio_dur - t
        if dur > rem:
            dur = max(0.6, rem)

        src = random.choice(assets)
        if src not in dur_map:
            try:
                dur_map[src] = _ffprobe_duration_seconds(src)
            except Exception:
                dur_map[src] = 0.0
        sd = dur_map[src]
        if sd < dur + 0.8:
            # 换一个更长的素材
            continue

        start = random.uniform(0.0, max(0.0, sd - dur - 0.2))
        segs.append(Segment(src=src, start=float(start), dur=float(dur)))
        t += dur

        # 防止超长音频导致输入过多
        if len(segs) >= 80:
            break
    return segs


def _split_script_to_chunks(text: str, *, target_chunks: int) -> list[str]:
    """
    把文案切成 N 段字幕块：优先按中文标点切，再做短行折叠。
    """
    t = (text or "").strip()
    if not t:
        return [""]

    # 去掉元数据标签行
    t = re.sub(r"(?m)^\s*【[^】]+】\s*$", "", t).strip()
    # 用标点切句
    parts = re.split(r"[。！？!?；;]\s*", t)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        parts = [t]

    # 目标：尽量均匀分配到 target_chunks
    if target_chunks <= 1:
        return ["\n".join(_wrap_lines(parts[0], width=18))]

    chunks: list[str] = []
    buf: list[str] = []
    # 简单按句子累积，接近均分
    approx = max(1, int(len(parts) / target_chunks))
    for i, p in enumerate(parts, 1):
        buf.append(p)
        if len(buf) >= approx:
            chunks.append("\n".join(_wrap_lines("。".join(buf), width=18)))
            buf = []
    if buf:
        chunks.append("\n".join(_wrap_lines("。".join(buf), width=18)))

    # 仍不足则补齐空
    while len(chunks) < target_chunks:
        chunks.append(chunks[-1] if chunks else "")
    return chunks[:target_chunks]


def _wrap_lines(s: str, *, width: int = 18) -> list[str]:
    s = (s or "").strip()
    if not s:
        return [""]
    s = re.sub(r"\s+", "", s)
    out: list[str] = []
    while len(s) > width:
        out.append(s[:width])
        s = s[width:]
    if s:
        out.append(s)
    return out[:3]


def _ass_time(t: float) -> str:
    # H:MM:SS.cs
    if t < 0:
        t = 0.0
    cs = int(round((t - int(t)) * 100))
    s = int(t)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"


def _write_ass_subtitles(path: Path, *, total_dur: float, segments: list[Segment], script_text: str) -> None:
    """
    生成 ASS：底部居中白字 + 黑色半透明背景（压迫感）
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # 每个切片对应一条字幕
    chunks = _split_script_to_chunks(script_text, target_chunks=max(1, len(segments)))

    header = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding",
            # BackColour: &HAABBGGRR  AA=80 半透明黑
            "Style: Bottom,Microsoft YaHei,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,3,0,0,2,80,80,90,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )

    lines = [header]
    t = 0.0
    for i, seg in enumerate(segments):
        start = t
        end = min(total_dur, t + seg.dur)
        t = end
        txt = chunks[i] if i < len(chunks) else (chunks[-1] if chunks else "")
        txt = txt.replace("\n", r"\N")
        # 轻微压迫感：固定前后空格
        event = f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Bottom,,0,0,0,,{txt}"
        lines.append(event)

    path.write_text("\n".join(lines), encoding="utf-8")


def _ff_filter_path(p: Path) -> str:
    # ffmpeg filter 参数里要用 / 且要转义盘符冒号
    s = str(p).replace("\\", "/")
    return s.replace(":", "\\:")


def _v11_4_filter_chain() -> str:
    """
    V11.4 滤镜：镜像翻转 + 冷色调偏移（压迫感）
    """
    # scale/crop 到 1080x1920 + hflip + 冷色偏移 + 对比锐化
    return (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "hflip,"
        "eq=contrast=1.18:brightness=-0.04:saturation=0.85,"
        "colorbalance=rs=-0.05:gs=-0.03:bs=0.10,"
        "unsharp=5:5:0.8:5:5:0.0"
    )


def synthesize(*, audio: Path, script_text: str, out_dir: Path) -> Path:
    audio = audio.resolve()
    if not audio.exists():
        raise FileNotFoundError(f"找不到音频: {audio}")
    if not script_text.strip():
        raise ValueError("文案为空，无法烧录字幕")

    out_dir.mkdir(parents=True, exist_ok=True)

    audio_dur = _ffprobe_duration_seconds(audio)
    bucket = _pick_bucket(script_text)
    asset_dir = FACTORY_ROOT / bucket
    assets = _list_video_assets(asset_dir)
    if not assets:
        raise FileNotFoundError(f"素材为空: {asset_dir}（请放入纵向视频素材）")

    segs = _build_segments(audio_dur=audio_dur, assets=assets, cut_min=3.0, cut_max=5.0)
    if not segs:
        raise RuntimeError("未能构建任何可用镜头切片（素材过短或探测失败）")

    ts = int(time.time())
    out_path = out_dir / f"v13_{audio.stem}_{ts}.mp4"
    ass_path = out_dir / f"v13_{audio.stem}_{ts}.ass"
    _write_ass_subtitles(ass_path, total_dur=audio_dur, segments=segs, script_text=script_text)

    # 组装 ffmpeg：N 个视频输入 + 1 个音频输入
    # 每个视频输入用 -ss/-t 截取随机片段
    cmd: list[str] = ["ffmpeg", "-y", "-hide_banner"]
    for s in segs:
        cmd += ["-ss", f"{s.start:.3f}", "-t", f"{s.dur:.3f}", "-i", str(s.src)]
    cmd += ["-i", str(audio)]

    # filter_complex：对每路视频套 V11.4，再 concat
    vfc = []
    for i in range(len(segs)):
        vfc.append(f"[{i}:v]{_v11_4_filter_chain()},fps=30,format=yuv420p[v{i}]")
    concat_in = "".join([f"[v{i}]" for i in range(len(segs))])
    vfc.append(f"{concat_in}concat=n={len(segs)}:v=1:a=0[vcat]")

    # 字幕烧录（ASS）
    sub = _ff_filter_path(ass_path)
    vfc.append(f"[vcat]subtitles='{sub}'[vout]")

    filter_complex = ";".join(vfc)

    # 视频：vout；音频：最后一个输入
    audio_in_idx = len(segs)
    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        f"{audio_in_idx}:a",
        "-t",
        f"{audio_dur:.3f}",
        "-shortest",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "24",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(out_path),
    ]

    print(f"[V13] 音频时长 T={audio_dur:.2f}s 切片数={len(segs)} 素材桶={bucket}")
    print(f"[V13] 素材目录: {asset_dir}")
    print(f"[V13] 输出: {out_path}")

    r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="ignore")
    if r.returncode != 0:
        tail = (r.stderr or "")[-1200:]
        raise RuntimeError(f"FFmpeg 合成失败（尾部）:\n{tail}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="V13.0 文案驱动视频合成（本地FFmpeg）")
    parser.add_argument("--audio", "-a", required=True, help="输入音频 mp3 路径（统帅生成）")
    parser.add_argument("--text", "-t", required=True, help="输入文案 txt 路径（对应音频）")
    parser.add_argument("--out-dir", default=str(FINAL_OUT_DIR), help="输出目录（默认 Final_Out）")
    parser.add_argument("--seed", type=int, default=0, help="随机种子（默认 0=用当前时间）")
    args = parser.parse_args()

    seed = int(args.seed)
    if seed == 0:
        seed = int(time.time())
    random.seed(seed)

    audio = Path(args.audio)
    txt_path = Path(args.text)
    if not txt_path.exists():
        raise SystemExit(f"找不到文案文件: {txt_path}")
    script_text = txt_path.read_text(encoding="utf-8", errors="ignore")

    out_dir = Path(args.out_dir)
    synthesize(audio=audio, script_text=script_text, out_dir=out_dir)


if __name__ == "__main__":
    main()

