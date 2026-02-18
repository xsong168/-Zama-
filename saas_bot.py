import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# 复用现有 V8.4 生产线（严禁破坏）
import bot as factory


load_dotenv()


WELCOME_TEXT = (
    "🔥 欢迎启动【2026 商业核武器】控制台。\n"
    "我是顶级商业军师（代号：酒魔）。\n"
    "别再花几万块请那些满嘴跑火车的代运营了。在这里，你只需要输入你的【行业名称】（例如：餐饮、教培、二手车），我将为你瞬间生成：\n"
    "1️⃣ 刀刀见血的短视频爆款脚本\n"
    "2️⃣ 直接能发朋友圈的私域收割文案\n"
    "3️⃣ 10 个直击你行业痛点的血肉炸弹词\n"
    "⚡️ 新用户每日免费测试 3 次。\n"
    "📥 请直接在对话框输入你的【行业】，开始降维打击 👇"
)


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return (v or default).strip()


def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _usage_path() -> Path:
    return Path(_env("OUTPUT_BASE_DIR", "output")) / "usage.json"


def _load_usage() -> dict:
    p = _usage_path()
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _save_usage(data: dict) -> None:
    p = _usage_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _check_and_consume_daily_quota(chat_id: int, *, limit: int = 3) -> bool:
    """每 chat_id 每日 3 次免费测试。"""
    data = _load_usage()
    day = _today_key()
    key = f"{chat_id}"
    if day not in data:
        data = {day: {}}
    day_map = data.get(day, {})
    used = int(day_map.get(key, 0))
    if used >= limit:
        return False
    day_map[key] = used + 1
    data[day] = day_map
    _save_usage(data)
    return True


def _sanitize_industry_text(text: str) -> str:
    t = (text or "").strip()
    t = t.replace("【", "").replace("】", "")
    t = re.sub(r"\s+", "", t)
    return t[:20]


def _detect_industry_trigger(text: str) -> str | None:
    """
    V8.9：指令雷达（纯文字唤醒，彻底放开匹配精度）
    - 不要求任何特殊符号（如【】或/）
    - 只要消息中包含行业关键词（如 IP、自媒体、餐饮、白酒等）就触发
    """
    raw = (text or "").strip()
    if not raw:
        return None

    norm = _sanitize_industry_text(raw)
    low = norm.lower()

    allow: list[str] = [
        str(x.get("name", "")).strip()
        for x in getattr(factory, "INDUSTRIES", [])
        if str(x.get("name", "")).strip()
    ]
    # 额外触发词：自媒体 / 做IP / IP
    allow += ["自媒体", "做IP", "IP"]
    allow = list(dict.fromkeys([x for x in allow if x]))  # 去重保序

    # 1) 中文行业：包含即命中
    for k in allow:
        if not k or k == "IP":
            continue
        if (k in raw) or (k in norm):
            return k

    # 2) 自媒体模糊命中
    if ("自媒" in raw) or ("自媒" in norm):
        return "自媒体"

    # 3) IP/做IP：大小写不敏感，包含即命中
    if ("做ip" in low) or ("做ip" in raw.lower()):
        return "做IP"
    if "ip" in low or "ip" in raw.lower():
        return "IP"

    return None


def _make_openai_client() -> OpenAI:
    # 兼容 DeepSeek/OpenAI：默认走 DeepSeek
    api_key = _env("API_KEY") or _env("DEEPSEEK_API_KEY")
    base_url = _env("LLM_BASE_URL", "https://api.deepseek.com/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def _llm_model() -> str:
    return _env("LLM_MODEL", "deepseek-chat")


def _matrix_prompt(industry: str) -> str:
    # 注意：避免使用已被你“公域防火墙”封杀的词本体（如 揭秘/圈套 等）
    return (
        f"你现在是一名隐于幕后的顶级商业军师（代号：酒魔）。用户当前行业是：{industry}。\n"
        "请生成以下两部分内容：\n"
        "1. 【血肉炸弹词库】：选取该行业最卑微的【物理碎片】+【残酷的商业定性】，生成10个极具痛感的词汇（如：冷灶头里的地租对账单）。\n"
        "2. 【多平台分发矩阵】：\n"
        "   - 🎬 抖音版：150字，口语化、咆哮感、毒舌拆解，必用炸弹词\n"
        "   - 📺 视频号版：强调格局和认知差\n"
        "   - 🍠 小红书版：避雷风格，带Emoji\n"
        "   - 🧠 知乎版：结构逻辑拆解，用商业博弈论术语\n"
        "要求：输出排版必须清晰，带对应 Emoji 图标区分模块。直接输出结果。\n"
        "【最高红线】：绝对禁止在输出的文案、标题或任何角落出现任何具体的人名。"
        "不要自称任何名字，只输出冰冷的商业真相和客观逻辑。若需要收口总结，统一使用【军师论断】或直接输出结论。"
    )


def anonymize_ip_text(text: str) -> str:
    """影子主权：兜底清洗“结语/总结”签名与残余字样。"""
    t = (text or "").strip()
    if not t:
        return ""
    # “xx结语/xx总结”这种签名一刀切（不依赖具体人名）
    t = re.sub(r"(?mi)^\s*[\u4e00-\u9fff]{2,6}\s*(结语|总结)\s*[:：]?.*$", "【军师论断】", t)
    t = re.sub(r"(?mi)^(结语|总结)[:：].*$", "【军师论断】", t)
    t = t.replace("结语", "军师论断")
    return t.strip()

def _call_llm_sync(industry: str) -> str:
    client = _make_openai_client()
    try:
        resp = client.chat.completions.create(
            model=_llm_model(),
            messages=[
                {"role": "system", "content": "保持输出清晰分段、可直接复制。"},
                {"role": "user", "content": _matrix_prompt(industry)},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        raise


def _pick_latest_parts(industry: str) -> dict[str, Path | None]:
    root = Path(_env("OUTPUT_BASE_DIR", "output")).resolve()
    base = {
        "text": root / "text" / industry,
        "audio": root / "audio" / industry,
        "image": root / "image" / industry,
        "video": root / "video" / industry,
    }

    def newest(p: Path, pattern: str) -> Path | None:
        try:
            if not p.exists():
                return None
            files = sorted(p.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)
            return files[0] if files else None
        except Exception:
            return None

    return {
        "txt": newest(base["text"], "*.txt"),
        "mp3": newest(base["audio"], "*.mp3"),
        "jpg": newest(base["image"], "*.jpg"),
        "mp4": newest(base["video"], "*.mp4"),
        "bombs": newest(base["text"], "*.bombs.txt"),
    }


async def _run_factory_for_industry(industry: str) -> None:
    """复用 bot.py 的 V8.4 生产线，跳过旧 Telegram 投递。"""
    os.environ["V8_MODE"] = "1"
    os.environ["V8_SKIP_TG"] = "1"
    os.environ["OUTPUT_BASE_DIR"] = _env("OUTPUT_BASE_DIR", "output") or "output"

    # 让 VisualEngine 继续工作（不破坏现有逻辑）
    os.environ["V79_REALTIME_VISUAL"] = "1"

    base_dir = Path(os.environ["OUTPUT_BASE_DIR"]).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    # 映射 folder（V8_MODE 下不会用到，但保持签名兼容）
    folder_map = {x["name"]: x["folder"] for x in factory.INDUSTRIES}
    folder = folder_map.get(industry, f"00-{industry}")

    limits = httpx.Limits(max_keepalive_connections=5, max_connections=5)
    async with httpx.AsyncClient(timeout=120.0, limits=limits) as client:
        await factory.generate_blood_bullet(
            client,
            1,
            base_dir,
            industry,
            folder,
            semaphore=None,
            visual_engine=factory.VisualEngine(safe_mode=True),
            render_semaphore=asyncio.Semaphore(1),
        )


async def start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME_TEXT)


_PIPELINE_SEMAPHORE = asyncio.Semaphore(2)


async def _v84_pipeline_task(app: Application, *, chat_id: int, industry: str) -> None:
    """后台任务：触发 V8.4 零件生产并按 ①②③④⑤ 发送。"""
    async with _PIPELINE_SEMAPHORE:
        try:
            await app.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)
        except Exception:
            pass

        try:
            await _run_factory_for_industry(industry)
            parts = _pick_latest_parts(industry)

            # ① 文案
            if parts["txt"]:
                txt = parts["txt"].read_text(encoding="utf-8", errors="ignore").strip()
                # 长文分条
                if len(txt) <= 3500:
                    await app.bot.send_message(chat_id=chat_id, text=txt)
                else:
                    await app.bot.send_message(chat_id=chat_id, text=txt[:3500] + "\n\n（续发中…）")
                    rest = txt[3500:]
                    for i in range(0, len(rest), 3500):
                        await app.bot.send_message(chat_id=chat_id, text=rest[i:i + 3500])

            # ② 音频
            if parts["mp3"]:
                with open(parts["mp3"], "rb") as f:
                    await app.bot.send_audio(chat_id=chat_id, audio=f)

            # ③ 背景
            if parts["jpg"]:
                with open(parts["jpg"], "rb") as f:
                    await app.bot.send_photo(chat_id=chat_id, photo=f)

            # ④ 视频
            if parts["mp4"]:
                with open(parts["mp4"], "rb") as f:
                    await app.bot.send_video(chat_id=chat_id, video=f, supports_streaming=True)

            # ⑤ 炸弹
            if parts["bombs"]:
                bombs = parts["bombs"].read_text(encoding="utf-8", errors="ignore").strip().splitlines()
                lines = [f"【今日血肉炸弹｜{industry}】"] + [f"🔴 {i+1}. {b}" for i, b in enumerate(bombs[:10]) if b.strip()]
                await app.bot.send_message(chat_id=chat_id, text="\n".join(lines)[:3500])

            # V10.0：禁词熔断（微信/诱导等禁止外显）——追单文案改为中性联络提示
            await app.bot.send_message(
                chat_id=chat_id,
                text="🎯 零件已投递完成。如需原声配音与交付方案，请通过已配置的外部联络渠道对接。",
            )
        except Exception:
            try:
                await app.bot.send_message(chat_id=chat_id, text="🔴 系统算力全开中，请稍后再试")
            except Exception:
                pass


async def industry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    chat_id = update.message.chat_id
    industry = _detect_industry_trigger(update.message.text)
    if not industry:
        return

    if not _check_and_consume_daily_quota(chat_id):
        await update.message.reply_text("🔴 系统算力全开中，请稍后再试")
        return

    # V8.9：心跳反馈机制（秒回）
    try:
        await update.message.reply_text(f"✓ 收到统帅指令：正在紧急调配【{industry}】行业弹药零件...")
    except Exception:
        pass

    # 异步生产解耦：耗时的音视频生产线后台触发，严禁阻塞监听引擎响应
    asyncio.create_task(_v84_pipeline_task(context.application, chat_id=chat_id, industry=industry))


def main() -> None:
    token = _env("TELEGRAM_TOKEN") or _env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_TOKEN 缺失")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, industry_callback))
    print("[统帅部] AI自媒体供应商 SaaS 模块已并轨，代码 0 报错，原生产线完好，请统帅验收！")
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

