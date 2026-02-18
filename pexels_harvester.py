import argparse
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


# === V12.0 自动捕食者：行业 -> 搜索词 ===
SEARCH_CONFIG: dict[str, str] = {
    "自媒体": "Glitch Art Dark",
    "白酒": "Liquid Macro Dark",
    "创业": "Dark Industry Architecture",
}

# === V12.8 搜索弹性化：行业 -> 关键词候选（按顺序降级） ===
SEARCH_FALLBACKS: dict[str, list[str]] = {
    # media（自媒体）：若 Glitch Art Dark 没结果，自动切换
    "自媒体": ["Glitch Art Dark", "Cyberpunk Dark", "Digital Noise", "Glitch Dark"],
}

# === V12.1 智能色调过滤：行业 -> 允许色调（Pexels 参数使用 gray，不是 grey）===
INDUSTRY_COLOR_POOL: dict[str, list[str]] = {
    "自媒体": ["blue", "black"],
    "创业": ["gray"],
    "白酒": ["brown", "black"],
}

# === V12.3 行业名容错映射（防终端输入乱码/别名）===
INDUSTRY_ALIASES: dict[str, str] = {
    "zimeiti": "自媒体",
    "zmt": "自媒体",
    "selfmedia": "自媒体",
    "baijiu": "白酒",
    "bj": "白酒",
    "chuangye": "创业",
    "cy": "创业",
}


PEXELS_VIDEOS_SEARCH_URL = "https://api.pexels.com/videos/search"


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return (v or default).strip()


def _read_env_file(env_path: Path) -> dict[str, str]:
    """
    读取同目录 .env（不依赖额外库）。
    只支持 KEY=VALUE 的简单格式，忽略注释与空行。
    """
    out: dict[str, str] = {}
    try:
        if not env_path.exists():
            return out
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            if k:
                out[k] = v
    except Exception:
        return out
    return out


def _get_pexels_api_key() -> str:
    """
    V12.7：能源主权自动激活（多级回退读取）
    顺序：
    1) os.getenv('PEXELS_API_KEY')
    2) 脚本同目录 .env

    注意：不在源码中硬编码真实密钥，避免泄露风险。
    """
    k = (os.getenv("PEXELS_API_KEY") or "").strip()
    if k:
        return k

    env_path = Path(__file__).parent / ".env"
    env_map = _read_env_file(env_path)
    k2 = (env_map.get("PEXELS_API_KEY") or "").strip()
    if k2:
        # 写回进程环境，后续逻辑统一读 env
        os.environ["PEXELS_API_KEY"] = k2
        return k2

    return ""


def _now_ts() -> str:
    return str(int(time.time()))

def _now_ts_ms() -> str:
    # 并发下载时避免同秒重名
    return str(int(time.time() * 1000))


def _factory_dir() -> Path:
    # V12.2：物理路径死锁（主权固化）
    # 默认下载根路径强制指向统帅指定的工厂仓库目录，不允许被环境变量覆盖。
    return Path(r"C:\Users\GIGABYTE\Desktop\Junshi_Bot冷酷军师\Jiumo_Auto_Factory").resolve()


def _downloaded_log_path(base: Path) -> Path:
    # 全局去重：同一个视频 ID 不重复抓取
    return base / "downloaded.log"


def _load_downloaded_ids(log_path: Path) -> set[str]:
    ids: set[str] = set()
    try:
        if not log_path.exists():
            return ids
        for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            # 格式：id \t industry \t filename \t url \t ts
            vid = line.split("\t", 1)[0].strip()
            if vid:
                ids.add(vid)
    except Exception:
        return ids
    return ids


def _append_download_log(log_path: Path, *, video_id: str, industry: str, filename: str, url: str) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        row = "\t".join([str(video_id), str(industry), str(filename), str(url), _now_ts()])
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(row + "\n")
    except Exception:
        return


@dataclass(frozen=True)
class VideoCandidate:
    video_id: str
    file_id: str
    link: str
    width: int
    height: int
    quality: str
    file_type: str

    @property
    def is_portrait(self) -> bool:
        return self.height >= self.width

    @property
    def score(self) -> tuple[int, int, int]:
        # 优先：portrait + 更高分辨率 + HD
        hd = 1 if str(self.quality).lower() == "hd" else 0
        return (hd, self.height, self.width)


def _pick_best_video_file(video: dict[str, Any]) -> VideoCandidate | None:
    vid = str(video.get("id") or "").strip()
    files = video.get("video_files") or []
    if not vid or not isinstance(files, list):
        return None

    cands: list[VideoCandidate] = []
    for f in files:
        if not isinstance(f, dict):
            continue
        link = str(f.get("link") or "").strip()
        file_type = str(f.get("file_type") or "").strip()
        quality = str(f.get("quality") or "").strip()
        try:
            width = int(f.get("width") or 0)
            height = int(f.get("height") or 0)
        except Exception:
            width, height = 0, 0

        if not link or "mp4" not in file_type.lower():
            continue
        file_id = str(f.get("id") or "").strip()

        cand = VideoCandidate(
            video_id=vid,
            file_id=file_id,
            link=link,
            width=width,
            height=height,
            quality=quality,
            file_type=file_type,
        )
        if cand.is_portrait:
            cands.append(cand)

    if not cands:
        return None
    cands.sort(key=lambda x: x.score, reverse=True)
    return cands[0]


async def _pexels_search(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    query: str,
    orientation: str,
    size: str,
    color: str | None,
    min_duration: int | None,
    max_duration: int | None,
    page: int,
    per_page: int,
) -> dict[str, Any]:
    headers = {"Authorization": api_key}
    params: dict[str, Any] = {
        "query": query,
        "orientation": orientation,
        "size": size,
        "page": page,
        "per_page": per_page,
    }
    if color:
        params["color"] = color
    if min_duration is not None:
        params["min_duration"] = int(min_duration)
    if max_duration is not None:
        params["max_duration"] = int(max_duration)

    r = await client.get(PEXELS_VIDEOS_SEARCH_URL, headers=headers, params=params, timeout=60.0)
    if r.status_code != 200:
        raise RuntimeError(f"Pexels API 失败: {r.status_code} {r.text[:200]}")
    try:
        return r.json()
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Pexels API 返回非 JSON: {e}")


def _normalize_color(c: str | None) -> str | None:
    if not c:
        return None
    x = str(c).strip().lower()
    if not x or x == "auto":
        return None
    if x == "grey":
        x = "gray"
    return x


def _fix_industry_input(s: str) -> str:
    """
    V12.3：行业名映射修复
    - 优先做中文原样保留
    - 若命中英文别名（zimeiti/baijiu/chuangye 等）则映射回中文
    - 对疑似乱码（包含替换符 �）做最小修复尝试
    """
    raw = (s or "").strip()
    if not raw:
        return ""

    # 疑似乱码：尝试一次 gbk/utf-8 互转（失败则忽略）
    if "�" in raw:
        try:
            raw2 = raw.encode("gbk", errors="ignore").decode("utf-8", errors="ignore").strip()
            if raw2:
                raw = raw2
        except Exception:
            pass

    # 归一化：去掉常见符号与空白
    norm = raw.replace("【", "").replace("】", "")
    norm = "".join(norm.split())
    low = norm.lower()

    if norm in SEARCH_CONFIG:
        return norm
    if low in INDUSTRY_ALIASES:
        return INDUSTRY_ALIASES[low]

    # 宽松命中：包含即可
    if "自媒" in norm:
        return "自媒体"
    if "白酒" in norm:
        return "白酒"
    if "创业" in norm:
        return "创业"

    return norm


def _pick_industry_color(industry: str, *, forced: str | None) -> str | None:
    fx = _normalize_color(forced)
    if fx:
        return fx
    pool = INDUSTRY_COLOR_POOL.get(str(industry).strip(), [])
    return random.choice(pool) if pool else None


async def search_videos(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    query: str,
    industry: str,
    color: str | None,
    page: int,
    per_page: int,
) -> tuple[dict[str, Any], str | None]:
    """
    V12.8：search_videos（显式暴露 color 动态传递 + 时长过滤）
    - orientation=portrait
    - size=large
    - color：由上层策略决定（行业配给 / 取消限制）
    - min_duration/max_duration：黄金剪辑片段
    """
    # V12.2：时长强硬裁剪（黄金剪辑片段）
    min_duration = 10
    max_duration = 30
    data = await _pexels_search(
        client,
        api_key=api_key,
        query=query,
        orientation="portrait",
        size="large",
        color=color,
        min_duration=min_duration,
        max_duration=max_duration,
        page=page,
        per_page=per_page,
    )
    return data, color


async def _download_file(
    client: httpx.AsyncClient,
    url: str,
    out_path: Path,
    *,
    display_name: str,
    print_lock: Any,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Pexels 直链通常可匿名下载
    async with client.stream("GET", url, timeout=120.0, follow_redirects=True) as r:
        r.raise_for_status()
        total = 0
        try:
            total = int(r.headers.get("Content-Length") or 0)
        except Exception:
            total = 0
        done = 0
        last_pct = -1
        async with print_lock:
            print(f"  [下载] {display_name} 0%")
        with open(out_path, "wb") as f:
            async for chunk in r.aiter_bytes(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if total > 0:
                        pct = int(done * 100 / total)
                        # 每 10% 打一次，避免刷屏
                        if pct // 10 != last_pct // 10 and pct < 100:
                            last_pct = pct
                            async with print_lock:
                                print(f"  [下载] {display_name} {pct}%")
        async with print_lock:
            print(f"  [下载] {display_name} 100%")


async def harvest(
    *,
    industries: list[str],
    limit_per_industry: int,
    color: str,
    per_page: int,
    dry_run: bool,
) -> None:
    api_key = _get_pexels_api_key()
    if not api_key:
        raise SystemExit(
            "缺少 PEXELS_API_KEY。请先去 Pexels 官网申请免费 API Key，并写入：\n"
            "1) 环境变量 PEXELS_API_KEY，或\n"
            "2) 在 pexels_harvester.py 同目录创建 .env，内容：PEXELS_API_KEY=你的Key\n"
        )

    base = _factory_dir()
    base.mkdir(parents=True, exist_ok=True)
    log_path = _downloaded_log_path(base)
    downloaded = _load_downloaded_ids(log_path)
    log_lock = __import__("asyncio").Lock()  # 避免并发写日志竞态
    # V12.2：多线程稳压（4K 大文件下载固定 5 并发，防带宽过载崩盘）
    download_sem = __import__("asyncio").Semaphore(5)
    print_lock = __import__("asyncio").Lock()  # 避免并发打印互相打断

    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    async with httpx.AsyncClient(limits=limits) as client:
        for industry in industries:
            industry = _fix_industry_input(industry)
            base_query = SEARCH_CONFIG.get(industry)
            if not base_query:
                print(f"[跳过] 未配置搜索词: {industry}")
                print(f"       可用行业: {list(SEARCH_CONFIG.keys())}")
                continue

            out_dir = base / industry
            out_dir.mkdir(parents=True, exist_ok=True)
            # V12.3：路径深度自检（必须打印绝对路径）
            print(f"正在向物理路径下载: {os.path.abspath(str(out_dir))}")

            need = max(0, int(limit_per_industry))
            got = 0
            reserved: set[str] = set()
            last_empty_payload: dict[str, Any] | None = None

            # 行业配给色调（V12.1）：auto 则按行业池挑选，否则强制覆盖
            picked_color = _pick_industry_color(industry, forced=color)

            queries = SEARCH_FALLBACKS.get(industry, [base_query])
            print(f"[扫描] 行业={industry} orientation=portrait size=large duration=10-30s 目标数量={need}")

            async def _download_and_log(best: VideoCandidate, out_path: Path) -> None:
                async with download_sem:
                    await _download_file(
                        client,
                        best.link,
                        out_path,
                        display_name=out_path.name,
                        print_lock=print_lock,
                    )
                async with log_lock:
                    _append_download_log(
                        log_path,
                        video_id=best.video_id,
                        industry=industry,
                        filename=str(out_path),
                        url=best.link,
                    )
                    downloaded.add(best.video_id)

            async def _run_search_pass(*, query: str, color_limit: str | None) -> None:
                nonlocal got, reserved, last_empty_payload
                page = 1
                while got < need:
                    data, effective_color = await search_videos(
                        client,
                        api_key=api_key,
                        query=query,
                        industry=industry,
                        color=color_limit,
                        page=page,
                        per_page=per_page,
                    )

                    videos = data.get("videos") or []
                    if not isinstance(videos, list) or not videos:
                        last_empty_payload = data if isinstance(data, dict) else None
                        break

                    tasks: list[Any] = []
                    for v in videos:
                        if got >= need:
                            break
                        if not isinstance(v, dict):
                            continue
                        vid = str(v.get("id") or "").strip()
                        if not vid:
                            continue
                        if vid in downloaded:
                            continue
                        if vid in reserved:
                            continue

                        best = _pick_best_video_file(v)
                        if not best:
                            continue

                        reserved.add(best.video_id)
                        ts = _now_ts_ms()
                        filename = f"{industry}_auto_{ts}.mp4"
                        out_path = out_dir / filename

                        async with print_lock:
                            ctag = effective_color or "all"
                            print(
                                f"  [命中] query='{query}' color={ctag} id={best.video_id} "
                                f"{best.width}x{best.height} quality={best.quality} -> {filename}"
                            )
                        if not dry_run:
                            tasks.append(_download_and_log(best, out_path))
                        got += 1

                    if tasks and not dry_run:
                        # 并发入库（固定 5 并发）
                        await __import__("asyncio").gather(*tasks)

                    page += 1

            # V12.8：关键词与色调弹性降级
            for q in queries:
                if got >= need:
                    break

                # Pass A：带色调限制（若有）
                ctag = picked_color or "all"
                print(f"  [检索] query='{q}' color={ctag}")
                await _run_search_pass(query=q, color_limit=picked_color)

                if got >= need:
                    break

                # Pass B：色调权重下放（不足则移除颜色限制补齐）
                if picked_color is not None:
                    print("  [降级] 色调限制不足，启动全色域补齐")
                    await _run_search_pass(query=q, color_limit=None)

            if got < need:
                # V12.3：调试日志（最终仍为空/不足时打印原始 JSON，提示更换关键词）
                payload = last_empty_payload or {}
                try:
                    raw = json.dumps(payload, ensure_ascii=False)
                except Exception:
                    raw = str(payload)
                print(f"  [调试] 未填满：已下载={got}/{need}。建议更换关键词或扩大 query 范围")
                print(f"  [调试] 原始JSON（截断）：{raw[:6000]}")

            print(f"[完成] 行业={industry} 本轮下载={got}，目录={out_dir}")


def main() -> None:
    print("[统帅部] 能源中枢已激活，正在使用战斗密钥执行捕食任务！")
    parser = argparse.ArgumentParser(description="V12.2 自动捕食者：Pexels 视频素材抓取（路径死锁+portrait+large+智能色调+强制10-30s+固定5并发）")
    parser.add_argument("--industry", "-i", action="append", default=[], help="指定行业，可重复，例如 -i 自媒体 -i 白酒")
    parser.add_argument("--limit", "-n", type=int, default=5, help="每个行业下载数量（默认 5）")
    parser.add_argument(
        "--color",
        "-c",
        type=str,
        default="auto",
        help="色调过滤：auto（按行业配给）或指定 black/blue/gray/grey/brown",
    )
    parser.add_argument("--per-page", type=int, default=20, help="每页数量（1-80，默认 20）")
    parser.add_argument("--dry-run", action="store_true", help="只打印命中，不实际下载")
    args = parser.parse_args()

    per_page = max(1, min(int(args.per_page), 80))
    industries = [_fix_industry_input(x) for x in (args.industry or []) if str(x).strip()]
    if not industries:
        industries = list(SEARCH_CONFIG.keys())

    import asyncio as _asyncio

    _asyncio.run(
        harvest(
            industries=industries,
            limit_per_industry=int(args.limit),
            color=str(args.color),
            per_page=per_page,
            dry_run=bool(args.dry_run),
        )
    )


if __name__ == "__main__":
    main()

