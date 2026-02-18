import argparse
import os
import random
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


FINAL_OUT_DIR = Path(r"C:\Users\GIGABYTE\Desktop\Junshi_Bot冷酷军师\Final_Out").resolve()


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
        tail = (r.stderr or "")[-400:]
        raise RuntimeError(f"ffprobe 失败: {p} {tail}")
    s = (r.stdout or "").strip()
    if not s:
        raise RuntimeError(f"ffprobe 无时长输出: {p}")
    return max(0.1, float(s))


def _wrap_lines(s: str, *, width: int = 18, max_lines: int = 2) -> list[str]:
    s = (s or "").strip()
    if not s:
        return [""]
    s = re.sub(r"\s+", "", s)
    out: list[str] = []
    while len(s) > width and len(out) < max_lines - 1:
        out.append(s[:width])
        s = s[width:]
    if s:
        out.append(s[:width])
    return out[:max_lines]


def _split_script(script_text: str) -> list[str]:
    """
    将 script_text 按句子切分，供 drawtext 分段烧录。
    """
    t = (script_text or "").strip()
    if not t:
        return []
    # 去掉常见元数据标签行
    t = re.sub(r"(?m)^\s*【[^】]+】\s*$", "", t).strip()
    # 句子切分
    parts = re.split(r"[。！？!?；;]\s*", t)
    parts = [p.strip() for p in parts if p.strip()]
    # 再兜底：按换行切
    if not parts:
        parts = [x.strip() for x in t.splitlines() if x.strip()]
    return parts


def _escape_drawtext_text(s: str) -> str:
    """
    ffmpeg drawtext text= 的转义：
    - 反斜杠、冒号、单引号、百分号需要转义
    - 换行用 \\n
    """
    x = (s or "")
    x = x.replace("\\", "\\\\")
    x = x.replace(":", r"\:")
    x = x.replace("'", r"\'")
    x = x.replace("%", r"\%")
    x = x.replace("\n", r"\n")
    return x


def _pick_fontfile() -> str | None:
    env_font = os.getenv("WATERMARK_FONT")
    candidates: list[str] = []
    if env_font:
        candidates.append(env_font)
    candidates.extend(
        [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
        ]
    )
    for fp in candidates:
        try:
            if fp and os.path.exists(fp):
                return fp
        except Exception:
            continue
    return None


def _ff_filter_path(path: str) -> str:
    # ffmpeg filter 参数里用 /，盘符冒号要转义
    s = str(path).replace("\\", "/")
    return s.replace(":", "\\:")


class VideoSynthesizer:
    """
    V13.1 工业化缝合引擎
    输入：audio_path, script_text, material_folder
    输出：Final_Out/output_{timestamp}.mp4
    """

    def __init__(self, *, audio_path: str | Path, script_text: str, material_folder: str | Path):
        self.audio_path = Path(audio_path).resolve()
        self.script_text = (script_text or "").strip()
        self.material_folder = Path(material_folder).resolve()

        if not self.audio_path.exists():
            raise FileNotFoundError(f"找不到音频: {self.audio_path}")
        if not self.script_text:
            raise ValueError("script_text 为空")
        if not self.material_folder.exists():
            raise FileNotFoundError(f"找不到素材目录: {self.material_folder}")

    def probe_audio_duration(self) -> float:
        return _ffprobe_duration_seconds(self.audio_path)

    def list_materials(self) -> list[Path]:
        exts = {".mp4", ".mov", ".m4v", ".webm"}
        out: list[Path] = []
        for p in self.material_folder.rglob("*"):
            try:
                if p.is_file() and p.suffix.lower() in exts:
                    out.append(p)
            except Exception:
                continue
        return out

    def _pick_nonrepeating_cycle(self, items: list[Path]) -> Iterable[Path]:
        """
        不重复抽取素材；若素材不足以覆盖总时长，则循环使用（按要求）。
        """
        if not items:
            return []
        pool = items[:]
        random.shuffle(pool)
        i = 0
        while True:
            yield pool[i]
            i += 1
            if i >= len(pool):
                random.shuffle(pool)
                i = 0

    def build_segments(self, *, total_duration: float) -> list[Segment]:
        mats = self.list_materials()
        if not mats:
            raise FileNotFoundError(f"素材为空: {self.material_folder}")

        # 探测素材时长（用于随机 start；失败则视为 0）
        dur_map: dict[Path, float] = {}
        for p in mats:
            try:
                dur_map[p] = _ffprobe_duration_seconds(p)
            except Exception:
                dur_map[p] = 0.0

        segs: list[Segment] = []
        t = 0.0
        chooser = self._pick_nonrepeating_cycle(mats)
        guard = 0
        while t < total_duration - 0.05 and guard < 5000:
            guard += 1
            dur = random.uniform(3.0, 5.0)
            rem = total_duration - t
            if dur > rem:
                dur = max(0.6, rem)

            src = next(chooser)
            sd = dur_map.get(src, 0.0)

            if sd <= 0.0:
                start = 0.0
            elif sd > dur + 0.8:
                start = random.uniform(0.0, max(0.0, sd - dur - 0.2))
            else:
                # 素材太短：后面用 -stream_loop -1 自动循环
                start = 0.0

            segs.append(Segment(src=src, start=float(start), dur=float(dur)))
            t += dur
            if len(segs) >= 120:
                break
        return segs

    def _segment_filter(self) -> str:
        """
        核平去重滤镜链（逐段强制执行）：
        - hflip
        - scale=1.2*iw:-1,crop=iw/1.2:ih/1.2（放大+中心裁剪）
        - eq=contrast=1.3:saturation=0.5:brightness=-0.05（冷酷氛围）
        额外：统一输出 1080x1920，避免 concat 不同尺寸炸膛
        """
        # 用 trunc 确保偶数像素，避免 x264 / crop 报错
        scale = "scale=trunc(1.2*iw/2)*2:trunc(1.2*ih/2)*2"
        crop = "crop=trunc(iw/1.2/2)*2:trunc(ih/1.2/2)*2:(iw-ow)/2:(ih-oh)/2"
        eq = "eq=contrast=1.3:saturation=0.5:brightness=-0.05"
        out = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
        return f"hflip,{scale},{crop},{eq},{out},fps=30,format=yuv420p"

    def _build_drawtext_chain(self, *, total_duration: float, subtitle_lines: list[str]) -> str:
        """
        drawtext 硬烧录：底部居中白字 + 黑色半透明描边/背景
        将字幕均匀分配在 [0, T] 时间轴上。
        """
        fontfile = _pick_fontfile()
        if fontfile:
            ff_fontfile = _ff_filter_path(fontfile)
            font_part = f"fontfile='{ff_fontfile}':"
        else:
            # 兜底用字体名
            font_part = "font='Microsoft YaHei':"

        n = max(1, len(subtitle_lines))
        step = total_duration / n if n > 0 else total_duration

        chain = "[vcat]"
        for i, s in enumerate(subtitle_lines):
            start = i * step
            end = min(total_duration, (i + 1) * step)
            # 字幕两行以内
            lines = _wrap_lines(s, width=18, max_lines=2)
            text = _escape_drawtext_text("\n".join(lines))

            draw = (
                "drawtext="
                f"{font_part}"
                f"text='{text}':"
                "x=(w-text_w)/2:"
                "y=h-(text_h)-120:"
                "fontsize=44:"
                "fontcolor=white:"
                "borderw=3:"
                "bordercolor=black@0.90:"
                "box=1:"
                "boxcolor=black@0.35:"
                "boxborderw=18:"
                f"enable='between(t,{start:.3f},{end:.3f})'"
            )
            chain = f"{chain}{draw},"
        chain = chain.rstrip(",")
        chain += "[vout]"
        return chain

    def synthesize(self, *, out_dir: str | Path = FINAL_OUT_DIR) -> Path:
        out_dir = Path(out_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        total_dur = self.probe_audio_duration()
        segs = self.build_segments(total_duration=total_dur)
        if not segs:
            raise RuntimeError("未构建任何素材切片")

        ts = int(time.time())
        out_path = out_dir / f"output_{ts}.mp4"

        subtitle_units = _split_script(self.script_text)
        if not subtitle_units:
            subtitle_units = [self.script_text]

        # 构建 ffmpeg：每段素材单独输入，允许循环（素材不足自动循环）
        cmd: list[str] = ["ffmpeg", "-y", "-hide_banner"]
        for seg in segs:
            cmd += [
                "-stream_loop",
                "-1",
                "-ss",
                f"{seg.start:.3f}",
                "-t",
                f"{seg.dur:.3f}",
                "-i",
                str(seg.src),
            ]
        # 音频输入
        cmd += ["-i", str(self.audio_path)]

        # filter_complex：逐段滤镜 -> concat -> drawtext
        vfc: list[str] = []
        for i in range(len(segs)):
            vfc.append(f"[{i}:v]{self._segment_filter()}[v{i}]")
        concat_in = "".join([f"[v{i}]" for i in range(len(segs))])
        vfc.append(f"{concat_in}concat=n={len(segs)}:v=1:a=0[vcat]")
        vfc.append(self._build_drawtext_chain(total_duration=total_dur, subtitle_lines=subtitle_units))

        filter_complex = ";".join(vfc)
        audio_idx = len(segs)

        cmd += [
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            f"{audio_idx}:a",
            "-t",
            f"{total_dur:.3f}",
            "-shortest",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(out_path),
        ]

        print(f"[V13.1] 音频时长 T={total_dur:.2f}s 段数={len(segs)}")
        print(f"[V13.1] 素材目录: {self.material_folder}")
        print(f"[V13.1] 输出: {out_path}")

        r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="ignore")
        if r.returncode != 0:
            tail = (r.stderr or "")[-1400:]
            raise RuntimeError(f"FFmpeg 合成失败（尾部）:\n{tail}")
        return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="V13.1 工业化缝合引擎（文案-音频-素材 物理缝合）")
    parser.add_argument("--audio", "-a", required=True, help="输入 audio.mp3 路径")
    parser.add_argument("--text", "-t", required=True, help="输入文案 txt 路径")
    parser.add_argument("--materials", "-m", required=True, help="素材目录 material_folder（包含 mp4）")
    parser.add_argument("--out-dir", default=str(FINAL_OUT_DIR), help="输出目录（默认 Final_Out）")
    parser.add_argument("--seed", type=int, default=0, help="随机种子（默认 0=当前时间）")
    args = parser.parse_args()

    seed = int(args.seed) if int(args.seed) != 0 else int(time.time())
    random.seed(seed)

    txt_path = Path(args.text).resolve()
    if not txt_path.exists():
        raise SystemExit(f"找不到文案文件: {txt_path}")
    script_text = txt_path.read_text(encoding="utf-8", errors="ignore")

    synth = VideoSynthesizer(audio_path=args.audio, script_text=script_text, material_folder=args.materials)
    synth.synthesize(out_dir=args.out_dir)


if __name__ == "__main__":
    main()

