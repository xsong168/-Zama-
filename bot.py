#!/usr/bin/env python3
"""
冷酷军师·V3 自动进化系统

核心能力：
- httpx 异步请求
- 懒加载身份系统
- FFmpeg 视频自动缝合
- 物理断句武器
- V3 引擎 (eleven_v3)
- 双层物理隔离 (/音频库 + /视频库)
- 全自动净空模式
"""

import os
import asyncio
import httpx
import time
import random
import copy
import re
import subprocess
import json
import traceback
import gc
import shutil
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# V44.0：100 枚金句导弹词库（创始人主权 / 数字视觉霸权 / 实战逻辑清洗）
try:
    from bot_logic.lexicon import GOLDEN_SENTENCES_100
except Exception:
    GOLDEN_SENTENCES_100: list[str] = []

# python-telegram-bot (v20+)：SaaS 监听引擎（可选入口；缺依赖则在 main_saas 中报错）
try:
    from telegram import Update
    from telegram.constants import ChatAction
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
    _PTB_AVAILABLE = True
except Exception:
    Update = None  # type: ignore
    ChatAction = None  # type: ignore
    Application = None  # type: ignore
    CommandHandler = None  # type: ignore
    ContextTypes = None  # type: ignore
    MessageHandler = None  # type: ignore
    filters = None  # type: ignore
    _PTB_AVAILABLE = False

# Windows 控制台常见为 GBK，打印 Emoji 会触发 UnicodeEncodeError。
# 这里强制 stdout/stderr 使用 UTF-8，并用 replace 防止炸膛。
def _force_utf8_stdio() -> None:
    try:
        import sys
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


_force_utf8_stdio()

load_dotenv()

# V39.5：极简健康端口（避免云端因“进程退出/无端口”反复 Backoff）
_HEALTH_SERVER_STARTED = False


def _start_minimal_health_server() -> None:
    """在云端启动一个极简 HTTP 端口，保证服务存活可观测。"""
    global _HEALTH_SERVER_STARTED
    if _HEALTH_SERVER_STARTED:
        return
    # 不依赖 IS_CLOUD_ENV（该变量在后面才定义）
    if not (os.getenv("ZEABUR") == "1" or os.path.exists("/tmp")):
        return
    if (os.getenv("DISABLE_HEALTH_SERVER") or "").strip() == "1":
        return
    try:
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        port = int((os.getenv("PORT") or "8080").strip() or "8080")

        class _H(BaseHTTPRequestHandler):
            def do_GET(self):  # type: ignore
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"ok")
                except Exception:
                    pass

            def log_message(self, _format, *_args):  # type: ignore
                # 静默：避免刷屏
                return

        def _serve() -> None:
            try:
                HTTPServer(("0.0.0.0", port), _H).serve_forever()
            except Exception:
                return

        t = threading.Thread(target=_serve, daemon=True)
        t.start()
        _HEALTH_SERVER_STARTED = True
        print(f"[健康] health server 已启动: 0.0.0.0:{port}")
    except Exception:
        return


# === V8.8 风控异常 ===
class RiskAlertException(Exception):
    """检测到违禁词流弹，触发物理拦截。"""


class ElevenQuotaExceeded(Exception):
    """ElevenLabs 配额/额度熔断。"""
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# V26.0：Emergency Config - 紧急配置类（暴力自动读取）
class EmergencyConfig:
    """
    V26.0：紧急配置类 - 静默自动读取
    当环境变量缺失时，自动从 .env 文件或备份读取，严禁报错停机
    """
    @staticmethod
    def load_from_env_file() -> dict:
        """从 .env 文件暴力读取配置"""
        config = {}
        env_paths = [
            Path(".env"),
            Path(".env.local"),
            Path("../.env"),
        ]
        
        for env_path in env_paths:
            if env_path.exists():
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                config[key.strip()] = value.strip().strip('"').strip("'")
                    if config:
                        print(f"[紧急装填] 从 {env_path} 读取配置成功")
                        return config
                except Exception:
                    continue
        return config
    
    @staticmethod
    def get(key: str, default=None):
        """智能获取配置：环境变量 → .env 文件 → 默认值"""
        # 1. 优先环境变量
        value = os.getenv(key)
        if value:
            return value
        
        # 2. 从 .env 文件读取
        env_config = EmergencyConfig.load_from_env_file()
        if key in env_config:
            print(f"[紧急装填] {key} 已从本地 .env 自动装填")
            return env_config[key]
        
        # 3. 返回默认值
        return default


# === 核心配置（V26.0 暴力装填） ===
DEEPSEEK_API_KEY = EmergencyConfig.get("DEEPSEEK_API_KEY")
ELEVENLABS_API_KEY = EmergencyConfig.get("ELEVENLABS_API_KEY")
VOICE_ID = EmergencyConfig.get("VOICE_ID")
DEFAULT_BG_IMAGE = EmergencyConfig.get("DEFAULT_BG_IMAGE", "./assets/default_bg.jpg")
TELEGRAM_BOT_TOKEN = EmergencyConfig.get("TELEGRAM_BOT_TOKEN") or EmergencyConfig.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = EmergencyConfig.get("TELEGRAM_CHAT_ID")
# ElevenLabs 音频引擎主权：eleven_v3（最高宪法）
ELEVEN_STABILITY = 0.20
ELEVEN_SIMILARITY_BOOST = 1.0

# V26.0：云端环境检测（Zeabur / Linux）
IS_CLOUD_ENV = os.getenv("ZEABUR") == "1" or not os.path.exists("D:/")

# V26.0：暴力路径自愈（最高优先级执行）
if IS_CLOUD_ENV:
    try:
        critical_dirs = [
            "/tmp/assets",
            "/tmp/output",
            "/tmp/Final_Out",
            "/tmp/Junshi_Staging",
            "/tmp/Jiumo_Auto_Factory"
        ]
        for dir_path in critical_dirs:
            os.makedirs(dir_path, exist_ok=True)
            os.chmod(dir_path, 0o777)
        print("[路径自愈] 云端环境 /tmp 目录已全线通电")
    except Exception as e:
        # V27.0：权限降维自愈 - 使用系统临时目录
        print(f"[路径自愈] 警告: {e}")
        try:
            import tempfile

            temp_base = Path(tempfile.gettempdir())
            for dir_name in ["assets", "output", "Final_Out", "Junshi_Staging", "Jiumo_Auto_Factory"]:
                try:
                    (temp_base / dir_name).mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
            print(f"[降维自愈] 已切换到系统临时目录: {temp_base}")
        except Exception as e2:
            print(f"[严重警告] 降维自愈失败: {e2}")

# === 视觉引信物理路径硬连接（本地环境专用） ===
# V23.0：云端环境下禁用 D 盘逻辑，强制使用 /tmp
JIUMO_FACTORY_DIR_FALLBACK = Path("/tmp") if IS_CLOUD_ENV else Path(r"D:\Google 云端硬盘\Jiumo_Auto_Factory")

# V15.2：工厂根目录自动探测（缓存一次，避免反复扫盘）
_FACTORY_ROOT_CACHE: Path | None = None


def detect_jiumo_factory_root() -> Path:
    """
    V23.0：路径主权自动化（云端/本地双模式）
    - 云端环境：直接返回 /tmp（禁用 D 盘扫描）
    - 本地环境：优先环境变量 JIUMO_FACTORY_DIR，再扫描 G: 盘，最后回退 D 盘
    """
    global _FACTORY_ROOT_CACHE
    
    # V23.0：云端环境跳过 D 盘逻辑
    if IS_CLOUD_ENV:
        tmp_factory = Path("/tmp/Jiumo_Auto_Factory")
        tmp_factory.mkdir(parents=True, exist_ok=True)
        _FACTORY_ROOT_CACHE = tmp_factory
        return tmp_factory
    
    try:
        if _FACTORY_ROOT_CACHE and _FACTORY_ROOT_CACHE.exists() and _FACTORY_ROOT_CACHE.is_dir():
            return _FACTORY_ROOT_CACHE
    except Exception:
        pass

    # 1) 环境变量优先
    try:
        env = (os.getenv("JIUMO_FACTORY_DIR") or "").strip().strip('"').strip("'")
        if env:
            p = Path(env).resolve()
            if p.exists() and p.is_dir():
                _FACTORY_ROOT_CACHE = p
                return p
    except Exception:
        pass

    # 2) 扫描 G: 盘（云盘镜像盘）
    try:
        g = Path("G:/")
        if g.exists() and g.is_dir():
            hits: list[Path] = []

            def _walk(top: str) -> None:
                try:
                    for root, dirs, _files in os.walk(top):
                        # 权限/系统目录剪枝（避免卡死/拒绝访问）
                        try:
                            dirs[:] = [d for d in dirs if d not in {"System Volume Information", "$RECYCLE.BIN"}]
                        except Exception:
                            pass

                        base = os.path.basename(root)
                        if "Jiumo_Auto_Factory" in base:
                            hits.append(Path(root))
                            # 找到一个就够了（优先最浅层）
                            return
                except Exception:
                    return

            _walk(str(g))
            if hits:
                best = sorted([p.resolve() for p in hits], key=lambda x: len(str(x)))[0]
                _FACTORY_ROOT_CACHE = best
                os.environ["JIUMO_FACTORY_DIR"] = str(best)
                return best
    except Exception:
        pass

    # 3) 本地回退
    try:
        p2 = JIUMO_FACTORY_DIR_FALLBACK.resolve()
        _FACTORY_ROOT_CACHE = p2
        os.environ["JIUMO_FACTORY_DIR"] = str(p2)
        return p2
    except Exception:
        _FACTORY_ROOT_CACHE = JIUMO_FACTORY_DIR_FALLBACK
        os.environ["JIUMO_FACTORY_DIR"] = str(JIUMO_FACTORY_DIR_FALLBACK)
        return JIUMO_FACTORY_DIR_FALLBACK


def firecontrol_preflight_or_die() -> Path:
    """
    V29.0：火控系统暴力自检（云端静默模式）
    - 云端环境：跳过所有检测，允许空仓启动（严禁停机）
    - 本地环境：扫描工厂根目录，若 mp4=0 则警告但不停机
    """
    root = detect_jiumo_factory_root()
    print(f"[雷达扫描] 目标分仓：{root}")
    
    # V29.0：云端环境跳过素材检测（严禁停机）
    if IS_CLOUD_ENV:
        print("[云端模式] 跳过本地素材检测，依赖在线 API 生产")
        return root
    
    try:
        has_mp4 = False
        for _ in root.rglob("*.mp4"):
            has_mp4 = True
            break
        if not has_mp4:
            # V29.0：本地环境仅警告，不停机
            print(f"[警告] 目标分仓 mp4=0，建议上传素材：{root}")
    except Exception as e:
        print(f"[警告] 无法扫描 mp4：{e}")
    return root

# === 血弹词库（大白话版：小学六年级能听懂，老板听了想砸桌子）===
HOOKS = [
    "你今年比去年更穷吗",
    "同行赚了你十倍，凭什么",
    "忙了三年，口袋还是空的",
    "你最大的敌人，是你自己",
    "干这行的人，大部分都在骗自己",
]
PAINS = [
    "忙死忙活却没人记住你",
    "每个月打款，每个月心慌",
    "干了三年，还不如别人一条视频赚得多",
    "你以为你在拼命，其实你在原地踏步",
    "钱没赚到，时间先没了",
]
ENDINGS = [
    "要么现在改，要么一直穷",
    "不是你不努力，是方向压根就错了",
    "今天不变，五年后你会后悔今天",
    "看完还不动，你就是那90%",
    "继续这样干，明年还是今年",
]

# === V10.0 随机风格引擎（避免机械感复刻） ===
V10_STYLE_POOL = ["冷酷审判", "咆哮揭秘", "毒舌嘲讽", "末路警告"]
# 注意：V10 禁词包含“揭秘”，但风格标签来自统帅指令；Prompt 内使用安全别名，避免输出触发。
V10_STYLE_ALIAS = {"咆哮揭秘": "咆哮剖析"}
V10_ATTACK_ANGLES = ["从成本切入", "从身份切入", "从未来切入"]
_LAST_STYLE_BY_INDUSTRY: dict[str, str] = {}
_LAST_ANGLE_BY_INDUSTRY: dict[str, str] = {}


def _pick_nonrepeating(industry: str, options: list[str], state: dict[str, str]) -> str:
    """同一进程内避免连续两发完全相同（不持久化到磁盘）。"""
    ind = str(industry or "").strip()
    last = state.get(ind)
    pool = [x for x in options if x and x != last]
    picked = random.choice(pool or options)
    state[ind] = picked
    return picked

# === 核心锚点词库（随机3选） ===
# 文案主权合规化：敏感词物理封杀（骗局/圈套/陷阱/割韭菜/暴利/底层/揭秘 等）
CORE_ANCHORS = [
    "没人告诉你的真相",
    "后悔",
    "只有3%的人知道",
    "你被骗了多少年",
    "钱去哪儿了",
    "这才是真正的玩法",
    "绝大多数人输在这里",
]

# === V8.8 公域算法风控：避雷词库（强制平替） ===
risk_control_map: dict[str, list[str]] = {
    # 欺诈/攻击类
    "骗局": ["逻辑闭环路径设伏", "非对称博弈困局"],
    "圈套": ["逻辑闭环路径设伏", "结构性博弈设伏"],
    "陷阱": ["逻辑闭环路径设伏", "结构性博弈设伏"],
    # 诱导/欺诈收益类
    "割韭菜": ["存量价值能级收割", "认知溢价回流"],
    "骗钱": ["存量价值能级收割", "认知溢价回流"],
    # 夸张收益类
    "暴利": ["跨能级超额红利", "结构性套利空间"],
    "赚翻": ["跨能级超额红利", "结构性套利空间"],
    # V10.0：高优先级禁词熔断（输出不允许出现本体）
    "套路": ["系统设定的博弈结构", "路径设伏"],
    "揭秘": ["系统剖析", "逻辑剖面"],
    "底层": ["结构性位置", "系统位阶"],
    "诱导": ["行为触发", "叙事牵引"],
    "微信": ["外部联络", "外部渠道"],
    "赚钱": ["资产能级跃迁", "能级红利兑现"],
    "上岸": ["主动权", "能级转折"],
    "真相": ["博弈后的真实底牌", "被掩盖的逻辑根部"],
}


def _loose_word_regex(word: str) -> re.Pattern:
    """构建宽松匹配：允许字符间夹杂符号/空白。"""
    sep = r"[.\-_|·•\s]*"
    chars = [re.escape(c) for c in (word or "").strip()]
    if not chars:
        return re.compile(r"(?!x)x")
    return re.compile(sep.join(chars))


_RISK_PATTERNS: list[tuple[str, re.Pattern]] = [(k, _loose_word_regex(k)) for k in risk_control_map.keys()]


def apply_risk_control_replacements(text: str) -> str:
    """按 risk_control_map 物理平替（随机二选一，避免重复口癖）。"""
    t = (text or "")
    for k, choices in risk_control_map.items():
        if not choices:
            continue
        # 先精确替换
        if k in t:
            t = t.replace(k, random.choice(choices))
        # 再宽松替换（如 骗.钱 / 割|韭|菜）
        try:
            pat = _loose_word_regex(k)
            t = pat.sub(random.choice(choices), t)
        except Exception:
            continue
    return t


def detect_risk_hits(text: str) -> list[str]:
    """检测残余敏感词（宽松匹配）。"""
    t = (text or "")
    hits: list[str] = []
    for k, pat in _RISK_PATTERNS:
        try:
            if pat.search(t):
                hits.append(k)
        except Exception:
            continue
    return hits


# === 2026 创始人主权觉醒词库（默认版：未提供外部词库时启用） ===
FOUNDER_LEXICON_DEFAULT = {
    "身份宿命类": [
        "你就是个打工的，不管你多努力", "你没有定价权，别人说多少你收多少",
        "你一天不干，一分钱不来", "你换个人就能被替代", "你的时间在给别人打工",
        "熬了三年还是原地踏步", "越忙越穷，你没发现吗", "你是在为老板赚钱，不是为自己",
        "你的收入上限早就被别人定死了", "你没有选择权，只有服从权"
    ],
    "成本模型类": [
        "每个月打款打到手软，利润却见底", "房租涨了，你的价格却不敢涨",
        "广告费扔进去没动静", "三个月回本，结果三年还在亏",
        "客人越来越难谈，成本越来越高", "供应商压着你，平台也压着你",
        "做的量越大，亏得越惨", "你没有利润，只有流水的幻觉",
        "你的钱都进了别人的口袋", "辛苦一年，不如别人躺赚一个月"
    ],
    "行业实战生肉": [
        "设备买来没用三个月就亏了", "房东说涨租你只能认", "库存卖不出去压死你",
        "员工干两个月就跑了", "老客户突然不来了你不知道为什么",
        "同行直接把你的方案抄走卖更低", "平台抽成越来越狠", "团购引来的全是薅羊毛的",
        "旺季没赚到，淡季直接躺平", "投了广告，一个客人都没来"
    ],
    "IP全流程": [
        "先让别人知道你是谁", "再让别人觉得你说的是真的", "然后让别人觉得你能帮到他",
        "最后让别人主动来找你", "你的内容就是你的销售员",
        "你说的话要让人记住，不是让人觉得高大上", "拍视频不是为了好看，是为了赚钱",
        "每条内容都要能带来客户", "你的账号是资产，不是日记",
        "做IP就是把你的经验换成钱"
    ],
    "觉醒与心理爆破": [
        "你不是不行，是方法错了", "你一直很努力，但方向一直是错的",
        "停止感动自己，开始让结果说话", "你的焦虑解决不了问题，但行动可以",
        "别人笑你想多了，等你赚到钱他们就闭嘴了", "现在改还来得及，再等就真的晚了",
        "你看清楚了吗？你现在走的路通往哪里", "穷不可怕，可怕的是穷还不改变",
        "想清楚一件事，你现在做的事五年后值多少钱", "你今天的选择，决定你五年后在哪"
    ]
}


def load_founder_lexicon() -> dict[str, list[str]]:
    """
    优先从本地词库加载；不存在则使用默认词库。

    V7.5 强制结构：必须包含五大维度（身份/成本/实战/全流程/觉醒）。
    即使外部词库键名不一致，也会做归一化映射并回填缺失维度。
    """
    required_keys = ["身份宿命类", "成本模型类", "行业实战生肉", "IP全流程", "觉醒与心理爆破"]
    key_aliases = {
        "身份": "身份宿命类",
        "宿命": "身份宿命类",
        "成本": "成本模型类",
        "模型": "成本模型类",
        "实战": "行业实战生肉",
        "生肉": "行业实战生肉",
        "全流程": "IP全流程",
        "IP": "IP全流程",
        "觉醒": "觉醒与心理爆破",
        "心理": "觉醒与心理爆破",
    }

    normalized: dict[str, list[str]] = {k: [] for k in required_keys}

    p = Path("词库/2026_创始人主权觉醒词库.json")
    try:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    kk = str(k).strip()
                    target = kk if kk in normalized else None
                    if not target:
                        for alias, mapped in key_aliases.items():
                            if alias in kk:
                                target = mapped
                                break
                    if not target:
                        continue
                    if isinstance(v, list):
                        normalized[target].extend([str(x).strip() for x in v if str(x).strip()])
    except Exception as e:
        print(f"[警告] 词库加载失败，使用默认词库: {e}")

    # 回填缺失维度
    for k in required_keys:
        if not normalized[k]:
            normalized[k] = list(FOUNDER_LEXICON_DEFAULT.get(k, []))

    return normalized


def generate_flesh_bombs_v84(industry: str) -> list[str]:
    """
    V8.4：血肉炸弹引擎（素材主权版）。
    - 行业碎片与 qualities 物理写入 bot.py（你提供的库）
    - 产出时做“合规/隐身”平替：避免墓碑/葬礼/绞肉机等高风险词
    - 不输出 emoji（避免 Windows 控制台/口播污染）
    """
    # V8.7：自媒体 破甲弹（大白话刺痛版 - 拒绝学术装逼，只扎痛点）
    # V8.7：自媒体 破甲弹（大白话刺痛版 - 绝对禁止学术装逼）
    ARMOR_PIERCERS_V87: list[str] = [
        "几十块的破背景，直接把你的客单价打骨折",
        "拍了上百条没人看，你的脸在网上根本不值钱",
        "天天陪白嫖客聊天，把自己的精力活活榨干",
        "对着镜头自嗨，观众连个标点符号都不想评论",
        "说话慢吞吞全是废话，三秒钟就被客户划走",
        "别人早用机器分身躺赚了，你还在自己熬夜背稿子",
        "停播一天就断收，你就是个互联网上的体力搬运工",
        "被几十个僵尸粉困死，你的账号已经成了流量坟场",
        "辛辛苦苦剪一天，干不过机器三秒钟生成的降维打击",
        "把自己活成了平台算法随时抛弃的廉价耗材",
    ]

    # 建立行业物理碎片主权库（原始素材）
    industry_assets: dict[str, list[str]] = {
        "餐饮": ["没洗完的残破瓷盘", "混浊的剩余锅底", "油腻的排风扇叶"],
        "教培": ["干涸的打印机墨盒", "深夜亮着的课件屏幕", "被揉皱的试卷副本"],
        "汽修": ["满是机油渍的扳手", "堆积如山的废旧轮胎", "生锈的千斤顶"],
        "医美": ["拆封后的玻尿酸空瓶", "手术台下冰冷的影子", "滤镜后的红肿创面"],
        "服装": ["仓库积压的样衣线头", "过时样衣里的霉味", "剪断的吊牌残骸"],
        "白酒": ["发霉的窖池酒糟", "沾满灰尘的贴牌酒标", "被抵押的陈年原酒"],
        # 兼容现有八大行业（不影响你原库）
        "创业": ["深夜亮着的财务表格", "反复修改的路演页", "未到账的回款提醒"],
        "美容": ["空掉的体验装瓶", "被擦花的价目牌", "反复弹出的退款通知"],
        "婚庆": ["积灰的布景道具", "未结清的供应商账单", "压着日期的档期表"],
        # V8.7：自媒体/做IP 50 枚破甲弹（全量装填）
        "自媒体": ARMOR_PIERCERS_V87,
        "做IP": ARMOR_PIERCERS_V87,
    }

    # 建立深度商业定性库（大白话版：直接说"这件事让你亏钱"）
    qualities: list[str] = [
        "正在把你的钱白白送出去",
        "每天都在拖着你往下沉",
        "是你这几年越干越穷的原因",
        "比你想象的更快在吃掉你的利润",
        "让你忙死也赚不到钱",
        "不解决这个，你干十年也没用",
    ]

    ind = str(industry).strip()
    fragments = industry_assets.get(ind, ["通用的逻辑碎片"])

    # V8.7：自媒体/做IP 行业——从 50 枚中随机抽 10 枚，确保每次全新
    if ind in {"自媒体", "做IP"}:
        if not fragments:
            return ["通用的逻辑碎片"]
        k = 10 if len(fragments) >= 10 else len(fragments)
        try:
            return random.sample(fragments, k)
        except Exception:
            # 兜底：取前 k（不打乱，避免污染原始词库）
            return fragments[:k]

    bombs: list[str] = []
    for _ in range(3):
        f = random.choice(fragments) if fragments else "通用的逻辑碎片"
        q = random.choice(qualities)
        # 统一句式：用于 Prompt 强制引用与 Telegram 消息⑤
        bombs.append(f"{f}里的{q}")
    return bombs


def sanitize_flesh_bombs_v84(bombs: list[str], *, limit: int = 10) -> list[str]:
    """V8.4/V8.7：违禁词自检与平替，确保炸弹词不含‘骗局/圈套’等。"""
    out: list[str] = []
    for b in bombs or []:
        s = str(b or "").strip()
        if not s:
            continue
        # 核心禁词平替（按你的要求：重点核平“骗局/圈套”）
        s = (
            s.replace("骗局", "博弈结构")
             .replace("圈套", "博弈结构")
        )
        out.append(s)
    return out[:limit]


_SYSTEM_PROMPT_TEMPLATE_CACHE: str | None = None


def get_system_prompt_template() -> str:
    """从 prompts/ 加载 System Prompt 模板（带缓存）。"""
    global _SYSTEM_PROMPT_TEMPLATE_CACHE
    if _SYSTEM_PROMPT_TEMPLATE_CACHE is not None:
        return _SYSTEM_PROMPT_TEMPLATE_CACHE

    prompt_path = Path(__file__).parent / "prompts" / "system_prompt.txt"
    try:
        _SYSTEM_PROMPT_TEMPLATE_CACHE = prompt_path.read_text(encoding="utf-8")
    except Exception as e:
        # 兜底：读取失败也不能让生产线崩溃
        print(f"[警告] System Prompt 模板读取失败，使用最小兜底模板: {e}")
        _SYSTEM_PROMPT_TEMPLATE_CACHE = "{SYSTEM_PROMPT_TEMPLATE_MISSING}"
    return _SYSTEM_PROMPT_TEMPLATE_CACHE


def render_system_prompt(
    *,
    seed_ns: int,
    jiumo_slogan: str,
    lexicon_category: str,
    lexicon_keywords: str,
    nightmare_keywords: str,
    flesh_bombs: str,
) -> str:
    """渲染 System Prompt（从 prompts/ 模板注入变量）。"""
    tpl = get_system_prompt_template()
    try:
        return tpl.format(
            seed_ns=seed_ns,
            jiumo_slogan=jiumo_slogan,
            lexicon_category=lexicon_category,
            lexicon_keywords=lexicon_keywords,
            nightmare_keywords=nightmare_keywords,
            flesh_bombs=flesh_bombs,
        )
    except Exception as e:
        print(f"[警告] System Prompt 渲染失败，使用最小兜底: {e}")
        return "{SYSTEM_PROMPT_RENDER_FAILED}"


# === 酒魔口头禅库（V5.5 潜航版 - 语义平替） ===
JIUMO_SLOGANS = [
    "这杯酒你敬系统，我敬底牌",
    "敬这杯酒，拿走钥匙",
    "酒醒之后，是你翻个盘的机会",
    "这杯酒入喉，看清你在这场博弈里的底牌",
    "这杯浓香的窖池不骗人，骗人的是你的阶级幻觉",
    "这杯浓香入喉，不是为了醉，是为了让你在酒局的位次里拿回主动权",
    "平庸化的搭建，从不看你流了多少汗",
    "在这场博弈里，你是执棋者，还是被敬掉的那杯酒？"
]

# === 白酒垂直模型关键词库 ===
BAIJIU_KEYWORDS = [
    "原酒主权", "阶级位次", "社交货币", 
    "浓香鼻祖", "纯粮固态", "窖池年份"
]

_ZERO_WIDTH_RE = re.compile(r"[\u200B\u200C\u200D\uFEFF]")
_RADICAL_HALLUCINATION_RE = re.compile(r"(左边|右边|子边|偏旁|部首)")


def sanitize_final_text(text: str, *, industry: str, for_tts: bool = False) -> str:
    """去复读/去乱码/去偏旁部首幻觉，并对行业做语义避让。

    - **for_tts=False**: 保留结构化信息（更适合归档/战报/可读性）
    - **for_tts=True**: 发送给 ElevenLabs 前的口播纯净化（剔除标题/标签/描述词）
    """
    if not text:
        return ""

    # 兜底禁词净化（即使模型输出，也会被物理替换/删除）
    replace_map = {
        "上岸": "主动权",
        "宣判": "逻辑拆解",
        "入场": "拿走钥匙",
        "带你入场": "拿走钥匙",
        "送你上路": "拿回主动权",
        "送你入局": "拿走钥匙",
        "加我微信": "获取执行模版",
        "诅咒": "结构性误差",
        # V10.0：去“真相”表达（统一转为底牌/逻辑）
        "真相拆解": "逻辑拆解",
        "拆解真相": "逻辑拆解",
        # 文案主权合规化：敏感词物理替换（其余由 risk_control_map 再做一次平替）
        "骗子": "阶级定额代价",
        "套路": "系统设定的博弈结构",
        "底层": "结构性位置",
        "揭秘": "拆解",
        # 语义自动平替（公域算法防御）
        "受骗": "在博弈中沦为逻辑代价",
        "赚钱": "实现资产能级跃迁",
        # V8.3：诱导词物理核平（公域隐身）
        "评论区留": "同步思维逻辑",
        "评论区扣": "获取执行模版",
        "评论区": "同步思维逻辑",
        "私信": "获取执行模版",
        "关注": "开启主权并轨",
        # V8.3：阶级敏感词清理
        "剥削": "存量切割",
    }
    for k, v in replace_map.items():
        text = text.replace(k, v)
    # V8.8：避雷词库强制平替（全局）
    text = apply_risk_control_replacements(text)
    # V8.9：影子主权死令——残余“结语”一律替换为“军师论断”
    text = text.replace("结语", "军师论断")
    # V10.0：去 AI 口癖与模板化引导词
    text = text.replace("首先", "").replace("总之", "")
    # “真相是”属于高风险模板口头禅，直接核平（含空白变体）
    text = re.sub(r"真\s*相\s*是", "", text)
    # “最后”直接删除，避免赌徒/末路暗示
    text = text.replace("最后", "")
    # 风格锁死：严禁感叹号（替换为句号）
    text = text.replace("！", "。").replace("!", "。")

    # 去掉不可见字符，避免 TTS 串词/复读
    text = _ZERO_WIDTH_RE.sub("", text)

    # 语义潜航 2.0：屏蔽“入场/上岸/宣判”及其变体（如 入.场 / 上|岸 / 宣_判）
    sep = r"[.\-_|·•\s]*"
    text = re.sub(rf"入{sep}场", "拿走钥匙", text)
    text = re.sub(rf"上{sep}岸", "主动权", text)
    text = re.sub(rf"宣{sep}判", "逻辑拆解", text)

    # V10.0：禁逻辑连词（短促、断句，减少 AI 机械串联感）
    for w in ["因为", "所以", "但是", "然而", "并且", "而且", "不过", "因此", "同时", "如果", "那么", "然后", "于是"]:
        text = text.replace(w, "")

    # 删除偏旁部首类幻觉行
    kept_lines: list[str] = []
    for line in text.splitlines():
        if _RADICAL_HALLUCINATION_RE.search(line):
            continue
        kept_lines.append(line)
    text = "\n".join(kept_lines)

    # 物理去重（按行去重，保留顺序）
    seen: set[str] = set()
    deduped: list[str] = []
    for line in text.splitlines():
        k = line.strip()
        if not k or k in seen:
            continue
        seen.add(k)
        deduped.append(k)
    text = "\n".join(deduped)

    if for_tts:
        # 口播纯净化：剔除 # 标题 / 【】标签 / [] 标签 / 文案描述词
        # 1) 删除 Markdown 标题行
        text = re.sub(r"(?m)^\s*#{1,6}\s*.*$", "", text)
        # 2) 删除 【...】 和 [...] 标签
        text = re.sub(r"【[^】]*】", "", text)
        text = re.sub(r"\[[^\]]*\]", "", text)
        # 3) 删除“描述词/标注”类行（镜头/字幕/画面/转场等）
        text = re.sub(
            r"(?m)^\s*(标题|文案|口播|字幕|镜头|画面|转场|提示|旁白|说明|注释|备注)\s*[:：].*$",
            "",
            text,
        )
        # 3.1) 删除“证据/元数据”类行（- 场景： / - 关键词： 等）
        text = re.sub(
            r"(?m)^\s*[-–—•]\s*(场景|关键词|证据|时间戳|物理路径|行业战区)\s*[:：].*$",
            "",
            text,
        )
        # 3.2) 删除纯标签行（结论/论证/收口等）
        text = re.sub(r"(?m)^\s*(结论|论证|证据|收口)\s*$", "", text)
        # 4) 删除元数据标签行（文件名/时间/行业等）
        text = re.sub(
            r"(?m)^\s*(文件名|时间|行业|行业战区|物理路径|口头禅|核心锚点|核心爆破点|行业噩梦关键词组|白酒关键词)\s*[:：].*$",
            "",
            text,
        )
        # 4.1) 物理剔除 ①②③ 等标号（含连续）
        text = re.sub(r"[①②③④⑤⑥⑦⑧⑨⑩]+", "", text)
        # 4.2) 剔除常见“1. / 2) / （3）”之类的编号头（避免口播读出数字标号）
        text = re.sub(r"(?m)^\s*[\(（]?\s*\d{1,2}\s*[\)）\.、]\s*", "", text)
        # 5) 压缩空行
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        # 6) 句子级去重（防止同句重复但不换行）
        #    以句末符号切分，保留顺序，只去掉完全相同的句子片段
        pieces = re.split(r"(?<=[。！？!?])", text)
        sent_seen: set[str] = set()
        kept: list[str] = []
        for p in pieces:
            s = p.strip()
            if not s:
                continue
            if s in sent_seen:
                continue
            sent_seen.add(s)
            kept.append(s)
        text = "".join(kept).strip()

        # 7) 特殊符号核平（防止机器音卡顿/乱码/奇怪停顿）
        #    - 统一引号与破折号
        text = (
            text.replace("“", "\"").replace("”", "\"")
                .replace("‘", "'").replace("’", "'")
                .replace("—", "-").replace("–", "-")
                .replace("•", " ").replace("·", "·")
        )
        #    - 删除 emoji / 高位符号（保留中英数字与常用标点/空白）
        text = re.sub(r"[\U00010000-\U0010FFFF]", " ", text)
        text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9\s，。！？!?、,.\-…'\":：;；（）()《》<>·]", " ", text)
        #    - 压缩多空格/多空行
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        # 8) 音频前端清洗（V8.2）：残余敏感词二次熔断（进 ElevenLabs 前最后一道防火墙）
        # V8.8：直接复用 risk_control_map + replace_map 的效果，再跑一遍宽松平替
        text = apply_risk_control_replacements(text)
        # 严禁感叹号
        text = text.replace("！", "。").replace("!", "。")

    # 白酒语义避让：去地名、禁词平替
    if industry == "白酒":
        text = text.replace("泸州", "这杯浓香")
        text = re.sub(rf"上{sep}岸", "主动权", text)
        text = re.sub(rf"入{sep}场", "拿走钥匙", text)

    return text.strip()


def strip_function_words_v142(text: str) -> str:
    """V14.2：预处理器——去掉常见虚词，制造冷硬语感。"""
    t = (text or "")
    if not t:
        return ""
    # 仅按字符级删除，避免复杂分词引入依赖
    for w in ["的", "了", "着"]:
        t = t.replace(w, "")
    return t


def split_text_for_tts(text: str, max_chars: int = 80) -> list[str]:
    """超过 max_chars 时按句子/换行切割，降低 ElevenLabs 复读幻觉概率。

    V7.8：每个 chunk 末尾强制追加物理停顿，强化节奏并降低复读幻觉。
    """
    if not text:
        return []

    # V14.2/V15.6：八十字硬锁——TTS 自动截断（硬熔断到 max_chars=80）
    max_chars = int(max_chars) if int(max_chars) > 0 else 80
    t = str(text).strip()
    if len(t) > max_chars:
        cut = t[:max_chars]
        m = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"), cut.rfind("\n"))
        if m >= int(max_chars * 0.6):
            t = cut[: m + 1]
        else:
            t = cut

    if len(t) <= max_chars:
        # 单段也追加停顿
        pause = "... ... "
        return [t if t.rstrip().endswith("... ...") else f"{t.rstrip()} {pause}"]

    parts = re.split(r"(?<=[。！？!?])|\n+", t)
    chunks: list[str] = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if not buf:
            buf = p
            continue
        if len(buf) + len(p) <= max_chars:
            buf = f"{buf}{p}"
        else:
            chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)

    # 末尾强制停顿（避免 ElevenLabs 长段落复读）
    pause = "... ... "
    paused_chunks: list[str] = []
    for c in chunks:
        c2 = c.strip()
        if not c2:
            continue
        if not c2.endswith("... ..."):
            # 控制长度，避免追加后超过太多
            c2 = (c2[: max(0, max_chars - len(pause) - 1)]).rstrip()
            c2 = f"{c2} {pause}"
        paused_chunks.append(c2)
    return paused_chunks


def inject_logical_pauses(text: str) -> str:
    """V8.1：在每一段论证结束后强制注入 ... ...（逻辑停顿威压）。"""
    t = (text or "").strip()
    if not t:
        return ""
    # 以空行分段
    paras = [p.strip() for p in re.split(r"\n{2,}", t) if p.strip()]
    out: list[str] = []
    for p in paras:
        p2 = p.rstrip()
        if p2.endswith("... ..."):
            out.append(p2)
        else:
            out.append(f"{p2} ... ...")
    return "\n\n".join(out).strip()


def inject_term_pauses(text: str, terms: list[str] | None = None) -> str:
    """V8.3：遇到指定术语自动追加 ... ...（军师沉思感）。"""
    t = (text or "").strip()
    if not t:
        return ""
    terms = terms or ["选题权"]
    for term in terms:
        term = (term or "").strip()
        if not term:
            continue
        # 若术语后面 12 字符内没有 ... ...，则插入
        t = re.sub(rf"({re.escape(term)})(?![^\n]{{0,12}}\.\.\.[\s]*\.\.\.)", r"\1 ... ...", t)
    return t


def v10_wrap_short_lines(text: str, *, max_len: int = 12, protect_terms: list[str] | None = None) -> str:
    """
    V10.0：彻底去 AI 化的“短句断行”。
    - 不截断语义：只做断行拆分
    - 以中文标点/换行优先切分，超长片段再按 max_len 切块
    """
    t = (text or "").strip()
    if not t:
        return ""
    max_len = int(max_len) if int(max_len) > 0 else 12

    # 统一分隔符，优先按标点拆
    t = re.sub(r"[，,；;]", "。\n", t)
    t = re.sub(r"[。！？!?]+", "。\n", t)
    raw_lines = [x.strip() for x in t.splitlines() if x.strip()]
    protect_terms = [str(x).strip() for x in (protect_terms or []) if str(x).strip()]

    out: list[str] = []
    for line in raw_lines:
        s = line.strip()
        if not s:
            continue
        # 去掉末尾重复句号
        s = s.rstrip("。")
        # 保护破甲弹/行业碎片等长短语：避免被强拆导致“词条断裂”
        if protect_terms and any(term in s for term in protect_terms):
            out.append(s)
            continue
        # 超长则切块
        while len(s) > max_len:
            out.append(s[:max_len])
            s = s[max_len:].lstrip()
        if s:
            out.append(s)
    return "\n".join(out).strip()


def concat_mp3_ffmpeg(segment_paths: list[Path], output_path: Path) -> None:
    """用 FFmpeg 合并 MP3 片段（优先 copy，失败则重编码）。"""
    if not segment_paths:
        raise ValueError("没有可合并的音频片段")

    list_file = output_path.with_suffix(".tmp")
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for p in segment_paths:
                f.write(f"file '{p.as_posix()}'\n")

        cmd_copy = [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file.resolve().as_posix(),
            "-c",
            "copy",
            "-y",
            output_path.resolve().as_posix(),
        ]
        r = subprocess.run(cmd_copy, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
        if r.returncode == 0:
            return

        cmd_reencode = [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file.resolve().as_posix(),
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            "-y",
            output_path.resolve().as_posix(),
        ]
        r2 = subprocess.run(cmd_reencode, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
        if r2.returncode != 0:
            raise RuntimeError(f"音频合并失败: {r2.stderr[:300]}")
    finally:
        # V8.0：严禁发送后删除临时文件（用于统帅验收零件）
        if (os.getenv("V8_MODE") or "").strip() == "1":
            return
        try:
            list_file.unlink(missing_ok=True)
        except Exception:
            pass


def ensure_mp3_44100(audio_path: Path) -> None:
    """音频质量锁死：强制重编码为 44.1kHz（失败不阻塞）。"""
    try:
        if not audio_path or not audio_path.exists():
            return
        tmp = audio_path.with_suffix(".44100.tmp.mp3")
        cmd = [
            "ffmpeg",
            "-y",
            "-i", audio_path.resolve().as_posix(),
            "-ar", "44100",
            "-ac", "2",
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            tmp.resolve().as_posix(),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
        if r.returncode == 0 and tmp.exists():
            tmp.replace(audio_path)
        else:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        return


def _generate_silent_mp3_ffmpeg(mp3_path: Path, *, seconds: float = 6.0) -> None:
    """极简兜底：用 FFmpeg 生成静音 mp3（无额外 Python 依赖）。"""
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    sec = max(1.0, float(seconds))
    cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=mono",
        "-t",
        f"{sec:.3f}",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "128k",
        mp3_path.resolve().as_posix(),
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
    if r.returncode != 0 or not mp3_path.exists():
        tail = (r.stderr or "")[-600:]
        raise RuntimeError(f"静音 mp3 兜底失败: {tail}")
    ensure_mp3_44100(mp3_path)


async def tts_fallback_to_mp3(text: str, mp3_path: Path, *, industry: str = "") -> None:
    """
    V13.9：副火控音频（edge-tts 优先，静音 mp3 兜底）。
    静默产出 mp3，供后续视频缝合使用。
    """
    t = (text or "").strip()
    if not t:
        raise RuntimeError("fallback tts text empty")

    # 1) edge-tts（在线、质量更稳）
    try:
        import edge_tts  # type: ignore

        voice = (os.getenv("EDGE_TTS_VOICE") or "").strip() or "zh-CN-YunxiNeural"
        rate = "+18%"
        volume = (os.getenv("EDGE_TTS_VOLUME") or "").strip() or "+0%"
        comm = edge_tts.Communicate(text=t, voice=voice, rate=rate, volume=volume)
        mp3_path.parent.mkdir(parents=True, exist_ok=True)
        # V44.4：15 秒硬超时，防止微软服务卡死阻塞全线
        await asyncio.wait_for(comm.save(str(mp3_path)), timeout=15.0)
        ensure_mp3_44100(mp3_path)
        print(f"   [音频] 已降级为 edge-tts: {mp3_path.name}")
        return
    except Exception:
        pass

    # 2) 生存兜底：静音 mp3（避免因为 TTS 失败导致整条链路炸膛）
    try:
        # 粗略估算口播时长：每秒约 4 字，上限 12 秒
        est = min(12.0, max(4.0, len(t) / 4.0))
        _generate_silent_mp3_ffmpeg(mp3_path, seconds=est)
        print(f"   [音频] 已降级为静音 mp3: {mp3_path.name}")
        return
    except Exception:
        raise RuntimeError("fallback tts failed (edge-tts + silent mp3)")


async def tts_edge_force_mp3(text: str, mp3_path: Path, *, voices: list[str]) -> None:
    """V14.2：强制 edge-tts（指定音色列表依次尝试）。"""
    t = (text or "").strip()
    if not t:
        raise RuntimeError("edge tts text empty")
    import edge_tts  # type: ignore

    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for v in voices:
        try:
            comm = edge_tts.Communicate(text=t, voice=v)
            # V44.4：15 秒硬超时，防止微软服务卡死阻塞全线
            await asyncio.wait_for(comm.save(str(mp3_path)), timeout=15.0)
            ensure_mp3_44100(mp3_path)
            return
        except Exception as e:
            last = e
            continue
    raise RuntimeError(f"edge-tts failed: {last}")

# === 行业痛点场景库（八大主权战区） ===
INDUSTRY_PAIN_SCENES = {
    "白酒": "窖池守了三十年，利润却被资本和渠道层层存量切割，原酒主权旁落",
    "餐饮": "月底看着那堆烂掉的食材和空荡荡的餐桌，满手油渍翻着账本",
    "创业": "融资PPT做了三个月，投资人看完转身就走，账上只剩三个月现金流",
    "美容": "跪着求客户办卡，却发现新客成本已经高到亏本，镜子里都是疲惫",
    "汽修": "满手黑油看账单，一天修12台车，利润却被平台抽成瞬间切走",
    "医美": "设备贷款还没还完，隔壁新店又开始价格战，顾客转头就走",
    "教培": "被双减政策一夜清零，租金和工资压得喘不过气，教室空荡荡",
    "婚庆": "旺季接单接到手软，淡季三个月颗粒无收，团队发不出工资"
}

# === 行业噩梦关键词组（V6.0：严禁串词，只能从本行业池抽取） ===
INDUSTRY_NIGHTMARE_KEYWORDS = {
    "白酒": ["原酒主权", "社交货币", "阶级位次", "渠道税", "压价", "窖池年份", "纯粮固态", "定价权旁落"],
    "餐饮": ["房东涨租", "食材报废", "空台", "团购绑架", "差评", "人效崩塌", "现金流窒息", "外卖抽成"],
    "创业": ["现金流断裂", "融资失败", "合伙人撕裂", "烧钱无效", "产品无人买", "获客塌方", "复盘无解", "方向漂移"],
    "美容": ["新客成本", "办卡流失", "价格战", "客诉", "员工跳槽", "客单下滑", "引流失效", "转化崩塌"],
    "汽修": ["平台抽成", "配件压价", "工时不值钱", "回头客流失", "同行抄袭", "账单难看", "油污一身", "利润见底"],
    "医美": ["设备贷款", "价格战", "渠道返佣", "投放无效", "顾客犹豫", "监管收紧", "客源断层", "口碑风险"],
    "教培": ["政策冲击", "退费", "续费断层", "获客贵", "场地空转", "老师流失", "家长质疑", "转型焦虑"],
    "婚庆": ["旺季透支", "淡季空转", "压价", "临时变卦", "人员闲置", "账期拖欠", "物料积压", "客源断层"],
}

# === 行业爆破矩阵（八大主权战区） ===
INDUSTRIES = [
    {"name": "白酒", "folder": "01-白酒主权战区"},
    {"name": "餐饮", "folder": "02-餐饮生死局"},
    {"name": "创业", "folder": "03-创业避坑"},
    {"name": "美容", "folder": "04-美容陷阱"},
    {"name": "汽修", "folder": "05-汽修真相"},
    {"name": "医美", "folder": "06-医美镰刀"},
    {"name": "教培", "folder": "07-教培内幕"},
    {"name": "婚庆", "folder": "08-婚庆暴利"}
]

INDUSTRY_EMOJIS = {
    "白酒": "🍶",
    "餐饮": "🍴",
    "创业": "🚀",
    "美容": "💄",
    "汽修": "🔧",
    "医美": "💉",
    "教培": "🎓",
    "婚庆": "💒"
}

# === V7.0 行业视觉索引引擎（默认安全：抽象背景，避免地名/车牌/品牌logo） ===
class VisualEngine:
    """V7.0 视觉索引：用语义标签选择安全视觉风格/背景。"""

    # V15.0：映射字典锁死——完全对齐“中文文件夹名”
    INDUSTRY_MAP = {"自媒体": "自媒体", "白酒": "白酒", "创业": "创业"}

    CATEGORY_TAGS = {
        "身份宿命类": ["冷色", "压迫", "孤立", "城市阴影"],
        "成本模型类": ["冷色", "秩序", "图表感", "工业线条"],
        "行业实战生肉": ["锈迹", "重金属", "废旧工厂", "昏暗光影"],
        "IP全流程": ["聚光", "舞台", "对比", "剪影"],
        "觉醒与心理爆破": ["高对比", "黑白", "闪白", "震动感"],
    }

    KEYWORD_TAGS = {
        "设备按废铁论斤卖": ["废旧工厂", "重金属", "锈迹", "昏暗光影"],
        "房东涨租闭店": ["昏暗光影", "冷色", "压迫", "空旷"],
        "压货压死": ["仓库", "阴影", "窒息", "冷色"],
    }

    COLOR_PALETTES = {
        "锈迹": "#2b1b12",
        "重金属": "#0f1116",
        "昏暗光影": "#0a0a0a",
        "冷色": "#0b1b2b",
        "黑白": "black",
        "闪白": "white",
    }

    # 行业主题色块（V7.8：无素材时强制使用行业色块，不用默认图）
    INDUSTRY_THEME_COLORS = {
        "白酒": "#4b0f16",   # 深红
        "餐饮": "#1b1b1b",   # 暗黑（油烟氛围）
        "创业": "#0b1b2b",   # 冷蓝
        "美容": "#2b0f2b",   # 紫黑
        "汽修": "#0f1116",   # 重金属黑
        "医美": "#0a1f2a",   # 冷青
        "教培": "#101018",   # 深蓝黑
        "婚庆": "#201018",   # 暗红紫
    }

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        c = (hex_color or "").strip()
        if not c.startswith("#") or len(c) != 7:
            return (10, 10, 10)
        return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))

    @staticmethod
    def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
        r, g, b = [max(0, min(255, int(x))) for x in rgb]
        return f"#{r:02x}{g:02x}{b:02x}"

    @classmethod
    def _shade(cls, hex_color: str, factor: float) -> str:
        """factor<1 变暗，factor>1 变亮"""
        r, g, b = cls._hex_to_rgb(hex_color)
        return cls._rgb_to_hex((r * factor, g * factor, b * factor))

    def make_industry_gradient(self, industry: str) -> tuple[str, str]:
        """V7.8：行业主题动态渐变的起止颜色。"""
        base = self.INDUSTRY_THEME_COLORS.get(industry, "#0a0a0a")
        c1 = self._shade(base, 0.75)
        c2 = self._shade(base, 1.25)
        return c1, c2

    def __init__(
        self,
        visuals_dir: Path | None = None,
        *,
        factory_dir: Path | None = None,
        safe_mode: bool = True
    ):
        # 旧入口：assets/visuals（可选）
        self.visuals_dir = visuals_dir or Path("assets/visuals")
        # 第三层视觉引信：物理路径硬连接（优先环境变量，其次固定绝对路径兜底）
        env_factory = (os.getenv("JIUMO_FACTORY_DIR") or "").strip().strip('"').strip("'")
        if not env_factory:
            try:
                # V15.2：自动探测工厂根目录（云盘盘符漂移也能命中）
                env_factory = str(detect_jiumo_factory_root())
            except Exception:
                pass

        self.factory_dir = factory_dir or (Path(env_factory) if env_factory else JIUMO_FACTORY_DIR_FALLBACK)
        self.safe_mode = safe_mode
        self._asset_index: list[tuple[str, Path]] = []
        self._indexed = False
        self._factory_files: list[Path] = []
        self._factory_indexed = False
        self._factory_cache: dict[str, list[Path]] = {}

    def _ensure_index(self) -> None:
        """构建本地素材索引，避免 FileNotFoundError；无素材则保持空索引。"""
        if self._indexed:
            return
        self._indexed = True
        try:
            if not self.visuals_dir.exists():
                return
            exts = {".jpg", ".jpeg", ".png", ".webp"}
            for p in self.visuals_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in exts:
                    folder = p.parent.name
                    self._asset_index.append((folder, p))
        except Exception:
            # 索引失败也不阻塞生产线
            self._asset_index = []

    def _resolve_factory_dirs(self) -> list[Path]:
        """物理路径硬连接：只认 JIUMO_FACTORY_DIR 指向的目录。"""
        try:
            if self.factory_dir:
                rp = Path(self.factory_dir).resolve()
                if rp.exists() and rp.is_dir():
                    return [rp]
        except Exception:
            pass
        return []

    def _ensure_factory_index(self) -> None:
        """构建 Jiumo_Auto_Factory 索引：收集图片/视频文件，不阻塞生产线。"""
        if self._factory_indexed:
            return
        self._factory_indexed = True
        self._factory_files = []
        self._factory_cache = {}
        exts = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v", ".webm"}
        try:
            roots = self._resolve_factory_dirs()
            for root in roots:
                for p in root.rglob("*"):
                    try:
                        if p.is_file() and p.suffix.lower() in exts:
                            self._factory_files.append(p)
                    except Exception:
                        continue
        except Exception:
            # 索引失败也不阻塞生产线
            self._factory_files = []
            self._factory_cache = {}

    def find_factory_asset_by_industry_realtime(self, industry: str) -> Path | None:
        """
        V7.9：实时物理索引（严禁缓存）。
        强制深入 Jiumo_Auto_Factory/{industry}/ 子目录，随机抓取一张图片。
        """
        ind = (industry or "").strip()
        if not ind:
            return None

        # V13.5：雷达扩容——优先检索视频文件，其次才是图片
        exts_video = {".mp4", ".mov", ".m4v", ".webm"}
        exts_image = {".jpg", ".jpeg", ".png", ".webp"}
        roots = self._resolve_factory_dirs()
        if (os.getenv("V79_DRY_RUN") or "").strip() == "1":
            if roots:
                print(f"[视觉] 视觉引信根目录: {roots[0]}")
            else:
                print("[视觉] 视觉引信根目录缺失（请设置 JIUMO_FACTORY_DIR）")

        if not roots:
            return None

        root = roots[0]
        # V13.8：若行业命中映射表，强制跳转至英文子文件夹检索
        ind_dir = (root / self.INDUSTRY_MAP.get(ind, ind))
        if not ind_dir.exists() or not ind_dir.is_dir():
            if (os.getenv("V79_DRY_RUN") or "").strip() == "1":
                print(f"[视觉] 未命中行业目录: {ind_dir}")
            return None

        candidates_video: list[Path] = []
        candidates_image: list[Path] = []
        try:
            for p in ind_dir.rglob("*"):
                try:
                    if not p.is_file():
                        continue
                    suf = p.suffix.lower()
                    if suf in exts_video:
                        candidates_video.append(p)
                    elif suf in exts_image:
                        candidates_image.append(p)
                except Exception:
                    continue
        except Exception:
            return None

        if candidates_video:
            return random.choice(candidates_video)
        if candidates_image:
            return random.choice(candidates_image)

        # V13.9：视觉强制匹配——行业目录为空时，仍尝试在工厂根目录搜任意视频
        try:
            any_videos: list[Path] = []
            for p in root.rglob("*"):
                try:
                    if p.is_file() and p.suffix.lower() in exts_video:
                        any_videos.append(p)
                except Exception:
                    continue
            if any_videos:
                return random.choice(any_videos)
        except Exception:
            pass
        return None

    def find_factory_asset_by_industry(self, industry: str) -> Path | None:
        """从 Jiumo_Auto_Factory 内，按行业名随机抓取 .jpg/.png（找不到则返回 None）。"""
        ind = (industry or "").strip()
        if not ind:
            return None
        self._ensure_factory_index()
        if not self._factory_files:
            return None

        if ind not in self._factory_cache:
            key = ind
            key2 = ind.replace(" ", "")
            matched: list[Path] = []
            for p in self._factory_files:
                s = p.as_posix()
                if key in s or key2 in s:
                    matched.append(p)
            self._factory_cache[ind] = matched

        pool = self._factory_cache.get(ind) or []
        return random.choice(pool) if pool else None

    def find_best_local_asset(self, tags: list[str]) -> Path | None:
        """从 assets/visuals/ 中按 tag/文件夹名模糊匹配最接近素材。"""
        self._ensure_index()
        if not self._asset_index or not tags:
            return None

        tags_lower = [t.lower() for t in tags]
        scored: list[tuple[int, Path]] = []
        for folder, p in self._asset_index:
            f = folder.lower()
            score = sum(1 for t in tags_lower if t and t in f)
            if score > 0:
                scored.append((score, p))
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        # 同分随机，避免单一背景
        top_score = scored[0][0]
        top = [p for s, p in scored if s == top_score]
        return random.choice(top) if top else None

    def build_ai_image_prompt(self, tags: list[str]) -> str:
        """只生成提示词，不调用生图API。默认输出抽象风格以规避风险。"""
        tags_text = "、".join(tags) if tags else "高对比、暗色、抽象质感"
        return (
            "抽象工业质感背景图，禁止出现门牌/车牌/地理标志/品牌logo，"
            f"关键词：{tags_text}，风格：高对比、昏暗光影、电影感。"
        )

    def pick_tags(self, lexicon_category: str, lexicon_keywords: list[str], nightmare_keywords: list[str]) -> list[str]:
        tags: list[str] = []
        tags.extend(self.CATEGORY_TAGS.get(lexicon_category, []))
        for kw in (lexicon_keywords or []) + (nightmare_keywords or []):
            tags.extend(self.KEYWORD_TAGS.get(kw, []))
        # 去重保序
        dedup: list[str] = []
        seen: set[str] = set()
        for t in tags:
            if t not in seen:
                dedup.append(t)
                seen.add(t)
        return dedup[:6]

    def _pick_from_visuals_subdir(self, subdir: str, *, must_contain: str | None = None) -> Path | None:
        """从 assets/visuals/{subdir}/ 下随机取一张图（可按文件名/路径关键词过滤）。"""
        try:
            base = (self.visuals_dir / subdir)
            if not base.exists() or not base.is_dir():
                return None
            exts = {".jpg", ".jpeg", ".png", ".webp"}
            pool: list[Path] = []
            for p in base.rglob("*"):
                try:
                    if not (p.is_file() and p.suffix.lower() in exts):
                        continue
                    if must_contain and must_contain not in p.as_posix():
                        continue
                    pool.append(p)
                except Exception:
                    continue
            return random.choice(pool) if pool else None
        except Exception:
            return None

    def pick_visual_override_for_text(self, *, industry: str, text: str) -> Path | None:
        """V8.4：按“文案真实命中词”做视觉联动覆盖。"""
        try:
            ind = (industry or "").strip()
            t = (text or "")
            if ind == "汽修" and ("废旧轮胎" in t):
                # 优先找文件名/路径带“轮胎”的素材
                p = self._pick_from_visuals_subdir("汽修", must_contain="轮胎")
                if p:
                    return p
                return self._pick_from_visuals_subdir("汽修")
        except Exception:
            return None
        return None

    def select_visual_profile(
        self,
        *,
        industry: str,
        lexicon_category: str,
        lexicon_keywords: list[str],
        nightmare_keywords: list[str],
        flesh_bombs: list[str] | None = None,
    ) -> dict:
        """返回用于 FFmpeg 的安全视觉配置。"""
        tags = self.pick_tags(lexicon_category, lexicon_keywords, nightmare_keywords)

        # V38.0：生存第一协议——云端空仓时强制 gradient（不下载、不停机）
        try:
            if IS_CLOUD_ENV and (os.getenv("JUNSHI_FORCE_GRADIENT_BG") or "").strip() == "1":
                c1, c2 = self.make_industry_gradient(industry)
                return {
                    "safe_mode": self.safe_mode,
                    "tags": tags,
                    "ai_image_prompt": self.build_ai_image_prompt(tags),
                    "bg": {"type": "gradient", "from": c1, "to": c2},
                    "vf": "scale=1280:720,eq=contrast=1.25:brightness=-0.05:saturation=0.85,unsharp=5:5:0.9:5:5:0.0",
                    "watermark_text": f"{industry}·核心拆解",
                }
        except Exception:
            pass

        # V8.4 视觉联动：当文案/炸弹提到“废旧轮胎”，优先检查 assets/visuals/汽修/
        try:
            fb_text = " ".join(flesh_bombs or [])
            if industry == "汽修" and ("废旧轮胎" in fb_text):
                local = self._pick_from_visuals_subdir("汽修", must_contain="轮胎")
                if not local:
                    local = self._pick_from_visuals_subdir("汽修")
                if local:
                    bg = {"type": "image", "path": str(local)}
                    return {
                        "safe_mode": self.safe_mode,
                        "tags": tags,
                        "ai_image_prompt": self.build_ai_image_prompt(tags),
                        "bg": bg,
                        "vf": "scale=1280:720,eq=contrast=1.25:brightness=-0.05:saturation=0.85,unsharp=5:5:0.9:5:5:0.0",
                        "watermark_text": f"{industry} · 逻辑拆解",
                    }
        except Exception:
            pass

        # 物理路径硬连接：每次都实时扫描对应行业目录（放弃缓存与复杂策略）
        asset = None
        try:
            asset = self.find_factory_asset_by_industry_realtime(industry)
        except Exception:
            asset = None

        # V15.1：视觉主权硬通电——自媒体音频生成后必须走视频背景
        # 若自媒体目录为空：直接报出物理扫描结果，严禁静默回退
        try:
            if str(industry).strip() == "自媒体":
                roots = self._resolve_factory_dirs()
                root0 = roots[0] if roots else None
                sm_dir = (root0 / "自媒体") if root0 else None
                if sm_dir and sm_dir.exists() and sm_dir.is_dir():
                    vids = [p for p in sm_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}]
                    if not vids:
                        print(f"[视觉][V15.1] 自媒体视频池为空：{sm_dir.resolve()}")
                        # V38.0：云端空仓生存协议——不抛错、不停机，允许 gradient 兜底
                        if not IS_CLOUD_ENV:
                            raise RuntimeError(f"自媒体素材为空：已扫描 {sm_dir.resolve()}")
                        asset = None
                        return {
                            "safe_mode": self.safe_mode,
                            "tags": tags,
                            "ai_image_prompt": self.build_ai_image_prompt(tags),
                            "bg": {"type": "gradient", "from": self.make_industry_gradient(industry)[0], "to": self.make_industry_gradient(industry)[1]},
                            "vf": "scale=1280:720,eq=contrast=1.25:brightness=-0.05:saturation=0.85,unsharp=5:5:0.9:5:5:0.0",
                            "watermark_text": f"{industry}·核心拆解",
                        }
                    asset = random.choice(vids)
                else:
                    p_show = sm_dir if sm_dir else root0
                    print(f"[视觉][V15.1] 工厂根目录/自媒体目录不存在：{p_show}")
                    # V38.0：云端空仓生存协议——不抛错、不停机，允许 gradient 兜底
                    if not IS_CLOUD_ENV:
                        raise RuntimeError(f"工厂路径异常：{p_show}")
                    asset = None
                    return {
                        "safe_mode": self.safe_mode,
                        "tags": tags,
                        "ai_image_prompt": self.build_ai_image_prompt(tags),
                        "bg": {"type": "gradient", "from": self.make_industry_gradient(industry)[0], "to": self.make_industry_gradient(industry)[1]},
                        "vf": "scale=1280:720,eq=contrast=1.25:brightness=-0.05:saturation=0.85,unsharp=5:5:0.9:5:5:0.0",
                        "watermark_text": f"{industry}·核心拆解",
                    }
        except Exception:
            # 让上层日志捕获并反馈，不做静默黑底/渐变回退
            raise

        # 旧入口兜底仍保留，但不作为主策略
        if not asset:
            try:
                asset = self.find_best_local_asset(tags)
            except Exception:
                asset = None
        base_color = self.INDUSTRY_THEME_COLORS.get(industry, "#0a0a0a")
        if tags:
            base_color = self.COLOR_PALETTES.get(tags[0], base_color)

        # 高对比/黑白策略（仅滤镜层面，不做符号混淆）
        vf = "scale=1280:720,eq=contrast=1.25:brightness=-0.05:saturation=0.85,unsharp=5:5:0.9:5:5:0.0"
        if "黑白" in tags:
            vf = "scale=1280:720,hue=s=0,eq=contrast=1.35:brightness=-0.02,unsharp=5:5:0.9:5:5:0.0"

        # 无素材时：严禁报错退出，改为行业渐变兜底（避免黑底与“自愈”字样）
        if asset:
            suf = str(asset.suffix).lower()
            if suf in {".mp4", ".mov", ".m4v", ".webm"}:
                bg = {"type": "video", "path": str(asset)}
            else:
                bg = {"type": "image", "path": str(asset)}
            watermark = f"{industry}·核心拆解"
        else:
            c1, c2 = self.make_industry_gradient(industry)
            bg = {"type": "gradient", "from": c1, "to": c2}
            watermark = f"{industry}·核心拆解"

        return {
            "safe_mode": self.safe_mode,
            "tags": tags,
            "ai_image_prompt": self.build_ai_image_prompt(tags),
            "bg": bg,
            "vf": vf,
            # 水印锁死：始终居中显示
            "watermark_text": watermark,
        }

# === 环境检测 ===
def check_ffmpeg():
    """FFmpeg 环境自检"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
            encoding='utf-8',
            errors='ignore'
        )
        if result.returncode == 0:
            print("[环境] FFmpeg 检查通过")
            return True
    except FileNotFoundError:
        print("[错误] FFmpeg 未安装，请访问: https://ffmpeg.org/download.html")
        return False
    except Exception as e:
        print(f"[错误] FFmpeg 检查失败: {e}")
        return False

# === Token 校验 ===
def validate_token(token):
    """Token 格式验证"""
    if not token or len(token) < 20 or ":" not in token:
        return False
    parts = token.split(":")
    return len(parts) == 2 and parts[0].isdigit() and len(parts[1]) >= 20

# === 懒加载系统 ===
def lazy_load_identity():
    """懒加载核心身份"""
    try:
        identity_path = Path("本体画像/00-核心身份.md")
        if identity_path.exists():
            with open(identity_path, 'r', encoding='utf-8') as f:
                print("[身份] 核心已加载")
                return f.read()
    except Exception as e:
        print(f"[警告] 身份加载失败: {e}")
    return None

# === 创建行业目录 ===
def create_industry_dirs(base_dir):
    """预创建所有行业的三层物理隔离目录"""
    print("\n[准备] 预创建行业三层目录结构...")
    v8_mode = (os.getenv("V8_MODE") or "").strip() == "1"
    for industry in INDUSTRIES:
        if v8_mode:
            # V8.0 零件库：按类别落盘
            (base_dir / "text" / industry["name"]).mkdir(parents=True, exist_ok=True)
            (base_dir / "audio" / industry["name"]).mkdir(parents=True, exist_ok=True)
            (base_dir / "image" / industry["name"]).mkdir(parents=True, exist_ok=True)
            (base_dir / "video" / industry["name"]).mkdir(parents=True, exist_ok=True)
            print(f"  [完成] {industry['name']} (text + audio + image + video)")
        else:
            industry_dir = base_dir / industry["folder"]
            # V31.0：物理路径降维——核平中文路径目录名（Linux 炸膛主因）
            audio_dir = industry_dir / "audio"
            video_dir = industry_dir / "video"
            script_dir = industry_dir / "text"
            audio_dir.mkdir(parents=True, exist_ok=True)
            video_dir.mkdir(parents=True, exist_ok=True)
            script_dir.mkdir(parents=True, exist_ok=True)
            print(f"  [完成] {industry['folder']} (audio + video + text)")
    print("[准备] 三层物理隔离已就位\n")

# === 视频缝合模块 ===
def _v11_ghostify_vf(vf: str) -> str:
    """
    V11.0：素材物理去重（零成本幽灵矩阵）
    - 随机水平翻转（hflip）
    - 随机饱和度微调（±5%，在现有 vf 的 saturation 上做微调）
    - 随机缩放后裁切回 1280x720（1.05x-1.15x）
    """
    base = (vf or "").strip()
    if not base:
        base = "scale=1280:720"

    # 1) 缩放与裁切（先把画布统一到 1280x720 再做滤镜链）
    scale_factor = random.uniform(1.05, 1.15)
    pre = (
        f"scale=trunc(1280*{scale_factor:.3f}/2)*2:"
        f"trunc(720*{scale_factor:.3f}/2)*2,"
        f"crop=1280:720"
    )

    # 2) hflip
    flip = random.random() < 0.5
    flip_f = "hflip" if flip else ""

    # 3) 饱和度微调：只改第一个出现的 saturation= 数值
    sat_mult = random.uniform(0.95, 1.05)

    def _tweak_sat(s: str) -> str:
        m = re.search(r"(saturation=)([0-9.]+)", s)
        if not m:
            return s
        try:
            old = float(m.group(2))
            new = max(0.05, min(2.0, old * sat_mult))
            return s[: m.start(2)] + f"{new:.3f}" + s[m.end(2) :]
        except Exception:
            return s

    # 去掉开头的 scale=1280:720，避免重复 scale 冲突
    base2 = re.sub(r"^\s*scale=1280:720\s*,?\s*", "", base)
    base2 = _tweak_sat(base2)

    chain = [pre]
    if flip_f:
        chain.append(flip_f)
    if base2:
        chain.append(base2)
    # 最终兜底：保证输出分辨率锁死
    chain.append("scale=1280:720")
    return ",".join([x for x in chain if x]).strip(",")


def video_stitcher(audio_path, output_path, visual_profile: dict | None = None):
    """FFmpeg 暴力缝合 + 质量压制 + V7.0 语义视觉对齐（安全抽象背景优先）"""
    visual_profile = visual_profile or {}

    # V22.5：云端战备仓自动创建（Linux 环境 /tmp，Windows C:/）
    is_cloud = os.path.exists("/tmp")  # Linux/云端环境检测
    if is_cloud:
        staging_dir = Path("/tmp/Junshi_Staging")
    else:
        staging_dir = Path("C:/Junshi_Staging")
    staging_dir.mkdir(parents=True, exist_ok=True)
    # V32.0：FFmpeg 算力全开（云端 ultrafast）
    preset = "ultrafast" if IS_CLOUD_ENV else "veryfast"
    
    # V22.5：路径物理级简化（战备仓纯英文环境）
    def _p(x: str | Path) -> str:
        """
        物理路径归一化（战备仓专用）：
        所有文件已搬运至战备仓（Linux: /tmp/Junshi_Staging, Windows: C:/Junshi_Staging）
        路径纯英文，无需复杂转义
        """
        try:
            return str(Path(str(x)).absolute()).replace('\\', '/')
        except Exception:
            return str(x).replace("\\", "/")

    # V17.0：音频搬运至战备仓
    staging_audio = staging_dir / "a.mp3"
    try:
        shutil.copy2(audio_path, staging_audio)
        audio_path = _p(staging_audio)
    except Exception as e:
        print(f"[警告] 音频搬运失败，使用原路径: {e}")
        audio_path = _p(audio_path)
    
    output_path = _p(output_path)

    vf = visual_profile.get("vf") or "scale=1280:720"
    # V11.0：每次缝合对素材做随机微调，确保“同一素材无限原创”
    vf = _v11_ghostify_vf(vf)
    # V7.8：严禁默认使用单一背景图；默认回退为行业渐变
    bg = visual_profile.get("bg") or {"type": "gradient", "from": "#050505", "to": "#202020"}

    # V14.4：水印主权硬锁死——入口强制重置为“{industry} · 核心拆解”
    try:
        ind0 = str(visual_profile.get("_industry") or "").strip()
    except Exception:
        ind0 = ""
    try:
        ind0 = ind0 or _extract_industry_from_watermark(str(visual_profile.get("watermark_text") or ""))
    except Exception:
        pass
    ind0 = (ind0 or "").strip() or "行业"
    watermark_text = f"{ind0} · 核心拆解"
    try:
        visual_profile["watermark_text"] = watermark_text
    except Exception:
        pass
    font_candidates = []
    env_font = os.getenv("WATERMARK_FONT")
    if env_font:
        font_candidates.append(env_font)
    # Windows 常见中文字体
    font_candidates.extend([
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ])
    fontfile = None
    for fp in font_candidates:
        try:
            if fp and os.path.exists(fp):
                fontfile = fp
                break
        except Exception:
            continue

    # 构建 drawtext（字体缺失则降级重试，但不准停止生产）
    # 说明：drawtext 对冒号敏感；fontfile 盘符 ":" 必须转义；text 单引号做转义
    safe_text = str(watermark_text).replace("'", "\\'")
    x_expr = "(w-text_w)/2"
    y_expr = "(h-text_h)/2+8*sin(2*PI*t)"
    alpha_expr = "0.70+0.15*sin(2*PI*t)"
    fontsize = "42"
    box = "1"
    boxcolor = "black@0.30"

    vf_candidates: list[str] = []
    if fontfile:
        # V17.1：字体文件路径简化（无需复杂转义）
        ff_fontfile = _p(fontfile).replace(":", "\\:")
        drawtext = (
            f"drawtext=fontfile='{ff_fontfile}':text='{safe_text}':"
            f"x={x_expr}:y={y_expr}:fontsize={fontsize}:"
            f"fontcolor=white:alpha='{alpha_expr}':box={box}:boxcolor={boxcolor}:boxborderw=12"
        )
        vf_candidates.append(f"{vf},{drawtext}")
    else:
        # 尝试用字体名（某些 FFmpeg/系统可用），失败则会自动降级到无水印版本
        drawtext = (
            f"drawtext=font='Microsoft YaHei':text='{safe_text}':"
            f"x={x_expr}:y={y_expr}:fontsize={fontsize}:"
            f"fontcolor=white:alpha='{alpha_expr}':box={box}:boxcolor={boxcolor}:boxborderw=12"
        )
        vf_candidates.append(f"{vf},{drawtext}")

    # 最终兜底：无 drawtext 也必须产出
    vf_candidates.append(vf)
    # 最终兜底2：只缩放（过滤链再炸也要尽量出片）
    vf_candidates.append("scale=1280:720")

    def _probe_duration_seconds(p: str) -> float | None:
        """用 ffprobe 取音频时长，失败则返回 None。"""
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", p],
                capture_output=True,
                timeout=10,
                encoding="utf-8",
                errors="ignore",
            )
            if r.returncode != 0:
                return None
            s = (r.stdout or "").strip()
            if not s:
                return None
            return max(0.1, float(s))
        except Exception:
            return None

    dur = _probe_duration_seconds(audio_path)
    if not dur:
        dur = 10.0

    video_exts = {".mp4", ".mov", ".m4v", ".webm"}
    bg_type = (bg.get("type") or "").lower()
    bg_path = bg.get("path") if isinstance(bg, dict) else None

    def _extract_industry_from_watermark(s: str) -> str | None:
        t = (s or "").strip()
        if not t:
            return None
        # 常见格式："{行业} · 逻辑拆解" / "{行业}战区·逻辑拆解"
        m = re.match(r"^(.{1,8}?)(战区)?[·\s]", t)
        if m:
            ind = (m.group(1) or "").strip()
            return ind or None
        return None

    def _resolve_factory_root() -> Path:
        # V15.2：统一使用自动探测逻辑（不写死盘符）
        try:
            return detect_jiumo_factory_root().resolve()
        except Exception:
            return JIUMO_FACTORY_DIR_FALLBACK.resolve()

    def _probe_video_wh(p: Path) -> tuple[int, int]:
        try:
            r = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "csv=p=0:s=x",
                    str(p),
                ],
                capture_output=True,
                timeout=10,
                encoding="utf-8",
                errors="ignore",
            )
            if r.returncode != 0:
                return (0, 0)
            s = (r.stdout or "").strip()
            if "x" not in s:
                return (0, 0)
            w, h = s.split("x", 1)
            return (int(w), int(h))
        except Exception:
            return (0, 0)

    def _pick_video_pool_for_industry(industry_name: str | None) -> list[Path]:
        # V15.0：视频缝合优先级（总装点火）
        # 只要音频已落地，优先扫描工厂根目录下的“自媒体/”视频池（统帅阵地：G:\...\自媒体）
        try:
            if audio_path and os.path.exists(str(audio_path)) and (os.path.getsize(str(audio_path)) > 0):
                root = _resolve_factory_root()
                selfmedia_dir = root / "自媒体"
                if selfmedia_dir.exists() and selfmedia_dir.is_dir():
                    pool_sm: list[Path] = []
                    for p in selfmedia_dir.rglob("*"):
                        try:
                            if p.is_file() and p.suffix.lower() in video_exts:
                                pool_sm.append(p)
                        except Exception:
                            continue
                    if pool_sm:
                        return pool_sm
        except Exception:
            pass

        # 优先：Jiumo_Auto_Factory/{industry}/ 内的视频
        try:
            root = _resolve_factory_root()
            # V14.2：强制 media 分仓（额度归零也必须动态生肉）
            forced_subdir = None
            try:
                forced_subdir = str((visual_profile or {}).get("_force_factory_subdir") or "").strip()
            except Exception:
                forced_subdir = None
            if forced_subdir:
                ind_dir = (root / forced_subdir)
                if ind_dir.exists() and ind_dir.is_dir():
                    pool: list[Path] = []
                    for p in ind_dir.rglob("*"):
                        try:
                            if p.is_file() and p.suffix.lower() in video_exts:
                                pool.append(p)
                        except Exception:
                            continue
                    if pool:
                        return pool
            if industry_name:
                mapped = None
                try:
                    mapped = VisualEngine.INDUSTRY_MAP.get(str(industry_name).strip())
                except Exception:
                    mapped = None
                ind_dir = (root / (mapped or industry_name))
                if ind_dir.exists() and ind_dir.is_dir():
                    pool: list[Path] = []
                    for p in ind_dir.rglob("*"):
                        try:
                            if p.is_file() and p.suffix.lower() in video_exts:
                                pool.append(p)
                        except Exception:
                            continue
                    if pool:
                        return pool
        except Exception:
            pass
        # V14.4：素材库增强——子目录为空时，自动在工厂根目录搜任意 4K 视频作为替补素材
        try:
            root = _resolve_factory_root()
            pool_all: list[Path] = []
            pool_4k: list[Path] = []
            for p in root.rglob("*"):
                try:
                    if not (p.is_file() and p.suffix.lower() in video_exts):
                        continue
                    pool_all.append(p)
                except Exception:
                    continue
            # 过滤 4K（支持 portrait 2160x3840）
            for p in pool_all[:200]:
                w, h = _probe_video_wh(p)
                if (max(w, h) >= 3840) and (min(w, h) >= 2160):
                    pool_4k.append(p)
            if len(pool_4k) >= 4:
                return random.sample(pool_4k, min(20, len(pool_4k)))
            if pool_all:
                return random.sample(pool_all, min(20, len(pool_all)))
        except Exception:
            pass

        # 兜底：用 bg_path 本身（若为视频）
        try:
            if bg_path and Path(str(bg_path)).suffix.lower() in video_exts and os.path.exists(str(bg_path)):
                return [Path(str(bg_path)).resolve()]
        except Exception:
            pass
        return []

    def _probe_video_duration_seconds(p: Path) -> float:
        try:
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
                timeout=10,
                encoding="utf-8",
                errors="ignore",
            )
            if r.returncode != 0:
                return 0.0
            s = (r.stdout or "").strip()
            return max(0.0, float(s)) if s else 0.0
        except Exception:
            return 0.0

    def _escape_drawtext_text(s: str) -> str:
        x = (s or "")
        x = x.replace("\\", "\\\\")
        x = x.replace(":", r"\:")
        x = x.replace("'", r"\'")
        x = x.replace("%", r"\%")
        x = x.replace("\n", r"\n")
        return x

    def _split_subtitle_units(text: str) -> list[str]:
        t = (text or "").strip()
        if not t:
            return []
        # 去掉常见元信息标签
        t = re.sub(r"(?m)^\s*【[^】]+】\s*$", "", t).strip()
        # 句子切分
        parts = re.split(r"[。！？!?；;]\s*", t)
        parts = [p.strip() for p in parts if p.strip()]
        if not parts:
            parts = [x.strip() for x in t.splitlines() if x.strip()]
        return parts

    def _wrap_two_lines(s: str, width: int = 18) -> str:
        s2 = re.sub(r"\s+", "", (s or "").strip())
        if not s2:
            return ""
        if len(s2) <= width:
            return s2
        return s2[:width] + "\n" + s2[width : width * 2]

    def _build_subtitle_drawtexts(
        total_dur: float,
        subtitle_text: str,
        *,
        font_spec: str,
        text_shaping: bool = True,
        max_lines: int = 2,
        fontsize: int = 44,
        y_expr: str = "h-(text_h)-70",
    ) -> str:
        units = _split_subtitle_units(subtitle_text)
        if not units:
            return ""
        # 取前 12 条，避免滤镜链过长炸膛
        units = units[:12]
        n = len(units)
        step = max(0.2, float(total_dur) / n)

        draws: list[str] = []
        for i, u in enumerate(units):
            start = i * step
            end = min(float(total_dur), (i + 1) * step)
            # V13.8：字幕遮挡控制——最多 2 行
            txt = _wrap_two_lines(u, width=18)
            safe = _escape_drawtext_text(txt)
            shaping_part = "text_shaping=1:" if text_shaping else ""
            draws.append(
                "drawtext="
                + f"{font_spec}"
                + f"text='{safe}':"
                + "x=(w-text_w)/2:"
                + f"y={y_expr}:"
                + f"fontsize={int(fontsize)}:"
                + "fontcolor=white:"
                + shaping_part
                + "borderw=3:"
                + "bordercolor=black@0.90:"
                + "box=1:"
                + "boxcolor=black@0.30:"
                + "boxborderw=18:"
                + f"enable='between(t,{start:.3f},{end:.3f})'"
            )
        return "," + ",".join(draws) if draws else ""

    def _build_dynamic_video_cmd(industry_name: str | None) -> tuple[list[str], list[str], list[tuple[Path, float, float]]]:
        """
        V17.0：多素材切片缝合（战备仓物理脱敏）
        返回 (cmd_base, filter_candidates, segs)
        """
        pool = _pick_video_pool_for_industry(industry_name)
        if not pool:
            # V29.0：素材库为空，静默警告（严禁停机）
            print(f"[警告] 素材库为空，视频缝合可能失败，但继续生产")
            return ([], [], [])

        # V15.0：总装点火——优先“自媒体”战区，固定抽 4 段生肉片段作为母池
        # （仍会循环使用这 4 段母池来填满音频时长）
        try:
            prefer_selfmedia = bool(pool) and all(((Path(p).parent.name == "自媒体") or ("\\自媒体\\" in str(p)) or ("/自媒体/" in str(p))) for p in pool[: min(8, len(pool))])
        except Exception:
            prefer_selfmedia = False

        # 随机抽取素材文件（不够则全用）
        k = 4 if prefer_selfmedia else random.randint(5, 10)
        if len(pool) >= k:
            sources = random.sample(pool, k)
        else:
            sources = pool[:]

        # 探测时长
        sd_map: dict[Path, float] = {p: _probe_video_duration_seconds(p) for p in sources}

        # 构建切片计划：每段 3-5 秒，循环使用素材，填满音频
        segs: list[tuple[Path, float, float]] = []
        t = 0.0
        idx = 0
        guard = 0
        # V14.2：短音频（约 8 秒）固定 4 段×2 秒（视觉轰炸）
        force_media = False
        try:
            force_media = str((visual_profile or {}).get("_force_factory_subdir") or "").strip() == "media"
        except Exception:
            force_media = False
        target_fixed = (force_media and float(dur) <= 9.0)

        while t < float(dur) - 0.05 and guard < 5000:
            guard += 1
            seg_d = 2.0 if target_fixed else random.uniform(1.5, 2.0)
            rem = float(dur) - t
            if seg_d > rem:
                seg_d = max(0.6, rem)

            src = sources[idx % len(sources)]
            idx += 1
            sd = sd_map.get(src, 0.0)
            if sd > seg_d + 0.8:
                start = random.uniform(0.0, max(0.0, sd - seg_d - 0.2))
            else:
                start = 0.0
            segs.append((src, float(start), float(seg_d)))
            t += seg_d
            if target_fixed and len(segs) >= 4:
                break
            if len(segs) >= 80:
                break

        if not segs:
            # V29.0：切片计划为空，静默警告（严禁停机）
            print(f"[警告] 切片计划为空，视频缝合将使用静态背景")
            return ([], [], [])

        # V17.0：视频素材搬运至战备仓（物理脱敏）
        staging_sources: dict[Path, Path] = {}  # 原始路径 -> 战备仓路径
        for i, src in enumerate(set([s[0] for s in segs]), 1):
            staging_video = staging_dir / f"v{i}.mp4"
            try:
                shutil.copy2(src, staging_video)
                staging_sources[src] = staging_video
                print(f"[战备仓] 已搬运素材 {i}/{len(set([s[0] for s in segs]))}: {src.name}")
            except Exception as e:
                # V29.0：素材搬运失败，静默警告（严禁停机）
                print(f"[警告] 无法复制素材 {src.name}，原因={e}，跳过此素材")
        
        # 更新 segs 为战备仓路径
        segs_staging = [(staging_sources[src], start, seg_d) for src, start, seg_d in segs]

        # 输入：每段素材一个 input（允许循环），最后再加音频
        cmd_base: list[str] = ["ffmpeg", "-y", "-nostdin"]
        for src, start, seg_d in segs_staging:
            cmd_base.extend(
                [
                    "-stream_loop",
                    "-1",
                    "-ss",
                    f"{start:.3f}",
                    "-t",
                    f"{seg_d:.3f}",
                    "-i",
                    _p(src),
                ]
            )
        cmd_base.extend(["-i", audio_path])

        # 滤镜链：逐段去重滤镜 + concat + 水印 + 字幕
        # 工业去重滤镜链（按统帅指令）
        seg_filter = (
            "hflip,"
            "scale=trunc(1.2*iw/2)*2:trunc(1.2*ih/2)*2,"
            "crop=1280:720:(iw-1280)/2:(ih-720)/2,"
            "eq=contrast=1.3:saturation=0.5:brightness=-0.05,"
            # V13.8：强制对齐像素宽高比，防止分辨率不一导致 concat 炸膛
            "setsar=1,fps=30,format=yuv420p"
        )

        # 字体规格（可用 fontfile 或 fontname）
        if fontfile:
            # V17.1：字体文件路径简化
            ff_fontfile = _p(fontfile).replace(":", "\\:")
            font_spec_file = f"fontfile='{ff_fontfile}':"
            font_spec_name = "font='Microsoft YaHei':"
        else:
            font_spec_file = "font='Microsoft YaHei':"
            font_spec_name = "font='Microsoft YaHei':"

        # 水印 drawtext（居中）
        alpha2 = "0.75"
        wm_draw_file = (
            "drawtext="
            f"{font_spec_file}"
            f"text='{safe_text}':"
            f"x={x_expr}:y={y_expr}:fontsize={fontsize}:"
            f"fontcolor=white:alpha='{alpha2}':box={box}:boxcolor={boxcolor}:boxborderw=12"
        )
        wm_draw_name = (
            "drawtext="
            f"{font_spec_name}"
            f"text='{safe_text}':"
            f"x={x_expr}:y={y_expr}:fontsize={fontsize}:"
            f"fontcolor=white:alpha='{alpha2}':box={box}:boxcolor={boxcolor}:boxborderw=12"
        )

        subtitle_text = str(visual_profile.get("subtitle_text") or "")
        # V13.8：字幕烧录——优先 text_shaping=1，失败则降级为不启用高级排版
        # V14.2：字幕逻辑固化——短文案字体放大至 60，位置上移至画面中心偏下
        # V14.3：字幕位置下调，避免遮挡核心视觉
        y_v142 = "h-150"
        sub_draw_file = _build_subtitle_drawtexts(float(dur), subtitle_text, font_spec=font_spec_file, text_shaping=True, max_lines=2, fontsize=60, y_expr=y_v142)
        sub_draw_name = _build_subtitle_drawtexts(float(dur), subtitle_text, font_spec=font_spec_name, text_shaping=True, max_lines=2, fontsize=60, y_expr=y_v142)
        sub_draw_file_plain = _build_subtitle_drawtexts(float(dur), subtitle_text, font_spec=font_spec_file, text_shaping=False, max_lines=2, fontsize=60, y_expr=y_v142)
        sub_draw_name_plain = _build_subtitle_drawtexts(float(dur), subtitle_text, font_spec=font_spec_name, text_shaping=False, max_lines=2, fontsize=60, y_expr=y_v142)

        # filter_complex 候选（字体文件/字体名/无 drawtext）
        vfc_prefix: list[str] = []
        for i in range(len(segs)):
            vfc_prefix.append(f"[{i}:v]{seg_filter}[v{i}]")
        concat_in = "".join([f"[v{i}]" for i in range(len(segs))])
        vfc_prefix.append(f"{concat_in}concat=n={len(segs)}:v=1:a=0[vcat]")

        fc_file = ";".join(vfc_prefix + [f"[vcat]{wm_draw_file}{sub_draw_file}[vout]"])
        fc_name = ";".join(vfc_prefix + [f"[vcat]{wm_draw_name}{sub_draw_name}[vout]"])
        fc_file_plain = ";".join(vfc_prefix + [f"[vcat]{wm_draw_file}{sub_draw_file_plain}[vout]"])
        fc_name_plain = ";".join(vfc_prefix + [f"[vcat]{wm_draw_name}{sub_draw_name_plain}[vout]"])
        fc_nodraw = ";".join(vfc_prefix + ["[vcat]scale=1280:720,setsar=1[vout]"])

        audio_in_idx = len(segs)
        cmd_tail = [
            "-map",
            "[vout]",
            "-map",
            f"{audio_in_idx}:a",
            "-shortest",
            "-t",
            f"{float(dur):.3f}",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            "24",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ]
        # cmd_base 不含 filter_complex，本函数外层会插入
        return (cmd_base + cmd_tail, [fc_file, fc_name, fc_file_plain, fc_name_plain, fc_nodraw], segs)

    # === V13.5 动态视频缝合分支 ===
    bg_is_video = (bg_type == "video") or (bg_path and Path(str(bg_path)).suffix.lower() in video_exts) or (str(bg_path).startswith("FORCE_"))
    if bg_is_video:
        ind_name = str(visual_profile.get("_industry") or "").strip() or _extract_industry_from_watermark(str(watermark_text))
        cmd_dyn, fc_candidates, dyn_segs = _build_dynamic_video_cmd(ind_name or None)
        if cmd_dyn and fc_candidates:
            last_result = None
            for fc in fc_candidates:
                cmd_try = list(cmd_dyn)
                # 插入 filter_complex
                try:
                    # 在 "-map" 之前插入
                    map_i = cmd_try.index("-map")
                    cmd_try = cmd_try[:map_i] + ["-filter_complex", fc] + cmd_try[map_i:]
                except Exception:
                    cmd_try = ["ffmpeg", "-y", "-nostdin"]
                try:
                    # V16.1：强制阻塞缝合自检——打印完整命令供统帅核查
                    print(f"[FFmpeg 动态缝合 CMD] {' '.join(cmd_try[:50])}...")  # 截断显示，避免过长
                    result = subprocess.run(cmd_try, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
                    last_result = (cmd_try, result)
                    if result.returncode == 0:
                        print(f"[视频] 动态缝合成功: {os.path.basename(output_path)}")
                        # V17.0：缝合成功后清空战备仓
                        try:
                            if staging_dir.exists():
                                shutil.rmtree(staging_dir, ignore_errors=True)
                                print("[战备仓] 已清空")
                        except Exception:
                            pass
                        return True, False
                except subprocess.TimeoutExpired:
                    last_result = (cmd_try, None)
                    continue

            # V13.8：二级火控预案——concat demuxer 降级方案
            def _concat_demuxer_fallback(segs: list[tuple[Path, float, float]]) -> bool:
                if not segs:
                    return False
                try:
                    tmp_dir = Path(str(output_path) + ".v13_8_tmp")
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    return False

                # 1) 每段素材先做“逐段滤镜 + 统一编码”输出为临时片段
                seg_paths: list[Path] = []
                seg_filter2 = (
                    "hflip,"
                    "scale=trunc(1.2*iw/2)*2:trunc(1.2*ih/2)*2,"
                    "crop=1280:720:(iw-1280)/2:(ih-720)/2,"
                    "eq=contrast=1.3:saturation=0.5:brightness=-0.05,"
                    "setsar=1,fps=30,format=yuv420p"
                )
                for i, (src, start, seg_d) in enumerate(segs, 1):
                    out_seg = tmp_dir / f"seg_{i:03d}.mp4"
                    seg_paths.append(out_seg)
                    cmd_seg = [
                        "ffmpeg",
                        "-y",
                        "-hide_banner",
                        "-stream_loop",
                        "-1",
                        "-ss",
                        f"{start:.3f}",
                        "-t",
                        f"{seg_d:.3f}",
                        "-i",
                        _p(src),
                        "-an",
                        "-vf",
                        seg_filter2,
                        "-c:v",
                        "libx264",
                        "-preset",
                        preset,
                        "-crf",
                        "24",
                        "-pix_fmt",
                        "yuv420p",
                        "-r",
                        "30",
                        "-g",
                        "60",
                        "-keyint_min",
                        "60",
                        "-sc_threshold",
                        "0",
                        _p(out_seg),
                    ]
                    rseg = subprocess.run(cmd_seg, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
                    if rseg.returncode != 0:
                        return False

                # 2) concat demuxer 拼接出无字幕/无音频主视频
                list_file = tmp_dir / "concat.txt"
                try:
                    with open(list_file, "w", encoding="utf-8") as f:
                        for p in seg_paths:
                            f.write(f"file '{p.as_posix()}'\n")
                except Exception:
                    return False

                joined = tmp_dir / "joined.mp4"
                cmd_join = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-f", "concat", "-safe", "0", "-i", _p(list_file), "-c", "copy", _p(joined)]
                rj = subprocess.run(cmd_join, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
                if rj.returncode != 0:
                    # 兜底：重编码 join
                    cmd_join2 = [
                        "ffmpeg",
                        "-y",
                        "-hide_banner",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        _p(list_file),
                        "-c:v",
                        "libx264",
                        "-preset",
                        preset,
                        "-crf",
                        "24",
                        "-pix_fmt",
                        "yuv420p",
                        "-r",
                        "30",
                        _p(joined),
                    ]
                    rj2 = subprocess.run(cmd_join2, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
                    if rj2.returncode != 0:
                        return False

                # 3) 最后一步：水印 + 字幕 + 音频混缩 输出成品
                # 字幕使用同一套 drawtext（优先 text_shaping=1，失败则降级）
                # V17.1：字幕字体路径简化
                if fontfile:
                    ff_fontfile2 = _p(fontfile).replace(":", "\\:")
                    font_spec2 = f"fontfile='{ff_fontfile2}':"
                else:
                    font_spec2 = "font='Microsoft YaHei':"

                wm2 = (
                    "drawtext="
                    f"{font_spec2}"
                    f"text='{safe_text}':"
                    f"x={x_expr}:y={y_expr}:fontsize={fontsize}:"
                    f"fontcolor=white:alpha='0.75':box={box}:boxcolor={boxcolor}:boxborderw=12"
                )
                subtitle_text2 = str(visual_profile.get("subtitle_text") or "")
                sub2 = _build_subtitle_drawtexts(float(dur), subtitle_text2, font_spec=font_spec2, text_shaping=True, max_lines=2)
                vf2 = f"scale=1280:720,setsar=1,{wm2}{sub2}"

                cmd_final = [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-i",
                    _p(joined),
                    "-i",
                    audio_path,
                    "-shortest",
                    "-t",
                    f"{float(dur):.3f}",
                    "-vf",
                    vf2,
                    "-c:v",
                    "libx264",
                    "-preset",
                    preset,
                    "-crf",
                    "24",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    output_path,
                ]
                rf = subprocess.run(cmd_final, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
                if rf.returncode == 0:
                    return True

                # 降级：不启用 text_shaping
                sub2b = _build_subtitle_drawtexts(float(dur), subtitle_text2, font_spec=font_spec2, text_shaping=False, max_lines=2)
                vf2b = f"scale=1280:720,setsar=1,{wm2}{sub2b}"
                cmd_final2 = list(cmd_final)
                try:
                    i_vf = cmd_final2.index("-vf")
                    cmd_final2[i_vf + 1] = vf2b
                except Exception:
                    pass
                rf2 = subprocess.run(cmd_final2, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
                return rf2.returncode == 0

            try:
                if dyn_segs and _concat_demuxer_fallback(dyn_segs):
                    print(f"[视频] 动态缝合降级（concat）成功: {os.path.basename(output_path)}")
                    # V17.0：缝合成功后清空战备仓
                    try:
                        if staging_dir.exists():
                            shutil.rmtree(staging_dir, ignore_errors=True)
                            print("[战备仓] 已清空")
                    except Exception:
                        pass
                    return True, False
            except Exception:
                pass

            # 动态分支失败：继续走旧兜底（不阻塞生产线）
            try:
                if last_result:
                    cmd_last, result_last = last_result
                    tail = ""
                    if result_last:
                        tail = (result_last.stderr or "")[-600:]
                    print(f"[警告] 动态缝合失败，回退旧逻辑。尾部: {tail}")
            except Exception:
                pass

    # V14.3：音频与视频同步锁死——只要音频存在且大小>0，严禁回退到纯黑底模式
    try:
        ap = Path(str(audio_path))
        if ap.exists() and ap.stat().st_size > 0:
            if isinstance(bg, dict) and str(bg.get("type") or "").lower() == "color" and str(bg.get("color") or "").lower() in {"black", "#000", "#000000"}:
                bg = {"type": "gradient", "from": "#0b1b2b", "to": "#050505"}
    except Exception:
        pass

    # V44.3：视频池为空降级保护——FORCE_ 路径无法实体化时强制渐变（禁止黑底）
    try:
        _bg_type_now = str(bg.get("type") or "").lower()
        _bg_path_now = str(bg.get("path") or "")
        if _bg_type_now == "video" and (
            _bg_path_now.startswith("FORCE_") or not os.path.exists(_bg_path_now)
        ):
            _ind_grad = str(visual_profile.get("_industry") or ind0 or "").strip()
            try:
                _c1, _c2 = VisualEngine.make_industry_gradient(None, _ind_grad)
            except Exception:
                _c1, _c2 = "#0a0a0a", "#1a1a2e"
            bg = {"type": "gradient", "from": _c1, "to": _c2}
            print(f"[V44.3] 视频素材池为空，已切换至行业渐变背景: {_ind_grad} ({_c1}→{_c2})")
    except Exception:
        pass

    # 默认安全：抽象背景（规避门牌/车牌/品牌logo）
    if bg.get("type") == "color":
        color = bg.get("color") or "black"
        # 注意：这里的 -vf 会在后面按 vf_candidates 重试替换
        cmd = [
            "ffmpeg",
            "-f", "lavfi", "-i", f"color=c={color}:s=1280x720" + (f":d={dur:.3f}" if dur else ""),
            "-i", audio_path,
            "-shortest",
            *(["-t", f"{dur:.3f}"] if dur else []),
            "-c:v", "libx264",
            "-preset", "ultrafast" if IS_CLOUD_ENV else "veryfast",
            "-crf", "28",
            "-vf", vf,
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-y", output_path,
        ]
    elif bg.get("type") == "gradient":
        c_from = bg.get("from") or "#050505"
        c_to = bg.get("to") or "#202020"
        r1, g1, b1 = VisualEngine._hex_to_rgb(c_from)
        r2, g2, b2 = VisualEngine._hex_to_rgb(c_to)
        # geq 生成横向渐变：从左到右 c_from -> c_to
        grad = (
            f"geq="
            f"r='(1-(X/W))*{r1} + (X/W)*{r2}':"
            f"g='(1-(X/W))*{g1} + (X/W)*{g2}':"
            f"b='(1-(X/W))*{b1} + (X/W)*{b2}'"
        )
        vf2 = f"{grad},{vf}"
        cmd = [
            "ffmpeg",
            "-f", "lavfi", "-i", "color=c=black:s=1280x720" + (f":d={dur:.3f}" if dur else ""),
            "-i", audio_path,
            "-shortest",
            *(["-t", f"{dur:.3f}"] if dur else []),
            "-c:v", "libx264",
            "-preset", "ultrafast" if IS_CLOUD_ENV else "veryfast",
            "-crf", "28",
            "-vf", vf2,
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-y", output_path,
        ]
    else:
        bg_image = bg.get("path") or DEFAULT_BG_IMAGE
        if not os.path.exists(bg_image):
            # V29.0：背景图缺失，静默警告（严禁停机）
            print(f"[警告] 背景图缺失 {bg_image}，尝试使用备用背景")
            # 尝试创建纯色背景兜底
            bg_image = None
        
        if bg_image:
            # V17.0：背景图搬运至战备仓
            staging_bg = staging_dir / f"bg{Path(bg_image).suffix}"
            try:
                shutil.copy2(bg_image, staging_bg)
                bg_image_safe = _p(staging_bg)
            except Exception as e:
                # V29.0：搬运失败，静默警告（严禁停机）
                print(f"[警告] 无法复制背景图 {bg_image}，原因={e}，将使用纯色背景")
                bg_image = None
        
        if bg_image:
            cmd = [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-loop", "1",
                *(["-t", f"{dur:.3f}"] if dur else []),
                "-i", bg_image_safe,
                "-i", audio_path,
                "-shortest",
                *(["-t", f"{dur:.3f}"] if dur else []),
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", "28",
                "-vf", vf,
                "-c:a", "aac",
                "-pix_fmt", "yuv420p",
                "-y", output_path,
            ]
        else:
            # V29.0：纯色背景兜底（无素材时保底出片）
            cmd = [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-f", "lavfi",
                "-i", f"color=c=black:s=1280x720:d={dur:.3f}",
                "-i", audio_path,
                "-shortest",
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", "28",
                "-vf", vf,
                "-c:a", "aac",
                "-pix_fmt", "yuv420p",
                "-y", output_path,
            ]
            print("[降级] 使用纯色背景生成视频")

    try:
        last_result = None
        for vf_try in vf_candidates:
            # 替换命令中的 -vf 参数值
            cmd_try = list(cmd)
            try:
                i = cmd_try.index("-vf")
                cmd_try[i + 1] = vf_try
            except Exception:
                pass

            # V16.1：强制阻塞缝合自检——打印完整命令供统帅核查
            print(f"[FFmpeg CMD] {' '.join(cmd_try)}")
            result = subprocess.run(cmd_try, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
            last_result = (cmd_try, result)
            if result.returncode == 0:
                print(f"[视频] 缝合成功: {os.path.basename(output_path)}")
                # V17.0：缝合成功后清空战备仓
                try:
                    if staging_dir.exists():
                        shutil.rmtree(staging_dir, ignore_errors=True)
                        print("[战备仓] 已清空")
                except Exception:
                    pass
                return True, False

        # 全部方案失败：写入全量日志（命令 + stderr），但不抛异常
        try:
            cmd_last, result_last = last_result if last_result else (cmd, None)
            log_path = str(output_path) + ".ffmpeg.log"
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("[CMD]\n")
                f.write(" ".join(cmd_last) + "\n\n")
                if result_last:
                    f.write("[STDERR]\n")
                    f.write((result_last.stderr or "") + "\n")
                    f.write("\n[STDOUT]\n")
                    f.write((result_last.stdout or "") + "\n")
            tail = ""
            if result_last:
                tail = (result_last.stderr or "")[-600:]
            print(f"[错误] FFmpeg 缝合失败（尾部）: {tail}")
            print(f"[错误] 详单已写入: {log_path}")
        except Exception:
            pass
        # V17.0：失败时也清空战备仓
        try:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass
        return False, False
    except subprocess.TimeoutExpired:
        print("[错误] 视频渲染超时（120秒），本发跳过视频")
        # V17.0：失败时也清空战备仓
        try:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass
        return False, False
    except Exception as e:
        print(f"[错误] 视频缝合异常: {e}")
        # V17.0：失败时也清空战备仓
        try:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass
        return False, False


def export_background_jpg(*, industry: str, visual_profile: dict | None, output_jpg: Path) -> bool:
    """
    V8.0：导出“本次使用的背景图”到 jpg，供 Telegram 消息③投递与物理验收。
    - 若有真实素材图：转码/缩放为 jpg。
    - 若无素材图：生成黑底 jpg，并尽最大努力叠加水印（失败则降级纯黑）。
    """
    try:
        output_jpg.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    vp = visual_profile or {}
    bg = (vp.get("bg") or {}) if isinstance(vp, dict) else {}
    bg_type = (bg.get("type") or "").lower()
    bg_path = bg.get("path") if isinstance(bg, dict) else None

    def _pick_fontfile() -> str | None:
        env_font = os.getenv("WATERMARK_FONT")
        candidates = []
        if env_font:
            candidates.append(env_font)
        candidates.extend([
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
        ])
        for fp in candidates:
            try:
                if fp and os.path.exists(fp):
                    return fp
            except Exception:
                continue
        return None

    def _run(cmd: list[str]) -> bool:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=120, encoding="utf-8", errors="ignore")
            return r.returncode == 0
        except Exception:
            return False

    # 1) 有真实图：转 jpg
    if bg_type == "image" and bg_path and os.path.exists(str(bg_path)):
        try:
            bg_in = Path(str(bg_path)).resolve().as_posix()
        except Exception:
            bg_in = str(bg_path).replace("\\", "/")
        cmd = [
            "ffmpeg",
            "-y",
            "-i", bg_in,
            "-vf", "scale=1280:720",
            "-q:v", "3",
            str(output_jpg),
        ]
        if _run(cmd):
            return True

    # 2) 无图：生成黑底 + 尝试水印
    # V14.3：彻底移除“自愈”字样
    text = f"{industry} · 核心拆解"
    safe_text = str(text).replace("'", "\\'")
    fontfile = _pick_fontfile()
    if fontfile:
        ff_fontfile = str(fontfile).replace("\\", "/").replace(":", "\\\\:")
        vf = (
            f"drawtext=fontfile='{ff_fontfile}':text='{safe_text}':"
            f"x=(w-text_w)/2:y=(h-text_h)/2:fontsize=46:"
            f"fontcolor=white:box=1:boxcolor=black@0.35:boxborderw=14"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "color=c=black:s=1280x720",
            "-frames:v", "1",
            "-vf", vf,
            "-q:v", "3",
            str(output_jpg),
        ]
        if _run(cmd):
            return True

    # 3) 最终兜底：纯黑 jpg
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "color=c=black:s=1280x720",
        "-frames:v", "1",
        "-q:v", "3",
        str(output_jpg),
    ]
    return _run(cmd)

# === Telegram 投递模块（带 429 重试） ===
async def tg_notifier(client, filename, script, local_path, video_failed=False, 
                      error_reason=None, industry="", sub_dir="", 
                      semaphore=None, max_retries=3):
    """Telegram 暴力投递 - 429 重试"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("   [警告] 电报配置缺失")
        return False
    
    # 使用 Semaphore 限流
    if semaphore:
        async with semaphore:
            return await _tg_notifier_internal(
                client, filename, script, local_path, video_failed,
                error_reason, industry, sub_dir, max_retries
            )
    else:
        return await _tg_notifier_internal(
            client, filename, script, local_path, video_failed,
            error_reason, industry, sub_dir, max_retries
        )

async def _tg_notifier_internal(client, filename, script, local_path, video_failed,
                                 error_reason, industry, sub_dir, max_retries):
    """Telegram 投递核心逻辑（带自动重试）"""
    for attempt in range(max_retries):
        try:
            seed_ns = time.time_ns()
            seed_headers = {"X-Seed-NS": str(seed_ns)}
            identity = "[中国酒魔·冷酷军师]"
            industry_emoji = INDUSTRY_EMOJIS.get(industry, "📂")
            industry_label = f"{industry_emoji} 行业战区: {industry}"
            
            if video_failed:
                caption = (
                    f"{identity}\n[警告 - 视频合成失败]\n\n"
                    f"{industry_label}\n🎯 物理路径: {sub_dir}\n\n"
                    f"文件名: {filename}\n文案: {script[:200]}...\n"
                    f"错误: {error_reason or '未知错误'}\n"
                    f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            else:
                caption = (
                    f"{identity}\n[逻辑拆解]\n\n"
                    f"{industry_label}\n🎯 物理路径: {sub_dir}\n"
                    f"文件名: {filename}\n\n文案:\n{script[:300]}\n\n"
                    f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            
            response = None

            def _log_failed_bullet(status_code: int, body: str) -> None:
                try:
                    log_path = Path("failed_bullets.log")
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(f"[{ts}] 行业={industry} 文件={filename} 状态={status_code}\n")
                        f.write(f"路径={local_path}\n")
                        f.write(f"响应={body[:500]}\n")
                        f.write(f"文案片段={script[:300]}\n")
                        f.write("=" * 60 + "\n")
                except Exception:
                    pass
            
            # 尝试发送视频
            if not video_failed and os.path.exists(local_path) and local_path.endswith('.mp4'):
                try:
                    with open(local_path, 'rb') as vf:
                        response = await client.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo",
                            files={'video': (filename, vf, 'video/mp4')},
                            data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'supports_streaming': 'true'},
                            headers=seed_headers,
                            timeout=120.0
                        )
                    
                    if response.status_code == 200:
                        print(f"   [投递] 视频发送成功: {filename}")
                        return True
                    elif response.status_code == 429:
                        # 429 重试：解析 retry_after 并等待
                        retry_after = response.json().get('parameters', {}).get('retry_after', 30)
                        print(f"   [流控] 遭遇 429，就地卧倒 {retry_after} 秒...")
                        await asyncio.sleep(retry_after)
                        continue  # 重试
                    elif response.status_code in (400, 403):
                        body = ""
                        try:
                            body = json.dumps(response.json(), ensure_ascii=False)
                        except Exception:
                            body = response.text
                        _log_failed_bullet(response.status_code, body)
                        print(f"   [跳过] 投递被拒绝 ({response.status_code})，已写入 failed_bullets.log")
                        return False
                except Exception as e:
                    print(f"   [警告] 视频上传异常: {e}")
            
            # 降级文本投递
            response = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": caption},
                headers=seed_headers,
                timeout=120.0
            )
            
            if response.status_code == 200:
                print(f"   [投递] 文本发送成功: {filename}")
                return True
            elif response.status_code == 429:
                # 429 重试：解析 retry_after 并等待
                retry_after = response.json().get('parameters', {}).get('retry_after', 30)
                print(f"   [流控] 遭遇 429，就地卧倒 {retry_after} 秒... (尝试 {attempt+1}/{max_retries})")
                await asyncio.sleep(retry_after)
                continue  # 重试
            elif response.status_code in (400, 403):
                body = ""
                try:
                    body = json.dumps(response.json(), ensure_ascii=False)
                except Exception:
                    body = response.text
                _log_failed_bullet(response.status_code, body)
                print(f"   [跳过] 投递被拒绝 ({response.status_code})，已写入 failed_bullets.log")
                return False
            else:
                print(f"   [错误] 投递失败 ({response.status_code})")
                try:
                    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
                except:
                    print(response.text)
                return False
                
        except Exception as e:
            print(f"   [警告] 投递异常（非阻塞）: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)  # 其他异常等待 5 秒后重试
                continue
            return False
    
    print(f"   [放弃] 重试 {max_retries} 次后仍失败")
    return False

# === V8.0 零件拆解：Telegram 独立投递（文案/音频/背景/视频） ===
def _split_telegram_text(text: str, limit: int = 3500) -> list[str]:
    """把长文案切成多条消息（避免 Telegram 4096 限制）。"""
    t = (text or "").strip()
    if not t:
        return []
    if len(t) <= limit:
        return [t]
    parts: list[str] = []
    buf = ""
    for line in t.splitlines():
        line2 = line.rstrip()
        if not line2 and not buf:
            continue
        # +1 预留换行
        if len(buf) + len(line2) + 1 <= limit:
            buf = (buf + "\n" + line2).strip("\n")
        else:
            if buf:
                parts.append(buf)
            buf = line2
    if buf:
        parts.append(buf)
    # 极端：仍超长则硬切
    hard: list[str] = []
    for p in parts:
        if len(p) <= limit:
            hard.append(p)
        else:
            for i in range(0, len(p), limit):
                hard.append(p[i:i + limit])
    return hard


async def _tg_post_with_retries(
    client: httpx.AsyncClient,
    method: str,
    *,
    json_body: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
    max_retries: int = 3,
) -> bool:
    """统一 429 重试；失败返回 False（不阻塞生产线）。"""
    if not TELEGRAM_BOT_TOKEN or not validate_token(TELEGRAM_BOT_TOKEN) or not TELEGRAM_CHAT_ID:
        print("   [警告] Telegram 配置缺失或无效，已跳过投递")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    for attempt in range(max_retries):
        try:
            seed_ns = time.time_ns()
            headers = {"X-Seed-NS": str(seed_ns)}
            resp = await client.post(
                url,
                json=json_body,
                data=data,
                files=files,
                headers=headers,
                timeout=120.0,
            )
            if resp.status_code == 200:
                return True
            if resp.status_code == 429:
                retry_after = 30
                try:
                    retry_after = int(resp.json().get("parameters", {}).get("retry_after", 30))
                except Exception:
                    retry_after = 30
                print(f"   [流控] Telegram 429，卧倒 {retry_after} 秒... (尝试 {attempt+1}/{max_retries})")
                await asyncio.sleep(retry_after)
                continue
            if resp.status_code in (400, 403):
                try:
                    body = json.dumps(resp.json(), ensure_ascii=False)
                except Exception:
                    body = resp.text
                try:
                    with open(Path("failed_bullets.log"), "a", encoding="utf-8") as f:
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        f.write(f"[{ts}] 投递被拒绝 method={method} status={resp.status_code}\n")
                        f.write(f"响应={body[:800]}\n")
                        f.write("=" * 60 + "\n")
                except Exception:
                    pass
                print(f"   [跳过] Telegram 投递被拒绝 ({resp.status_code})")
                return False

            print(f"   [错误] Telegram 投递失败 ({resp.status_code})")
            try:
                print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
            except Exception:
                print(resp.text)
            return False
        except Exception as e:
            print(f"   [警告] Telegram 投递异常: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
                continue
            return False
    return False


async def tg_send_text_only(client: httpx.AsyncClient, text: str, *, tag: str = "投递①") -> bool:
    """发送纯文本（可多条），用于文案/炸弹清单等。"""
    ok_any = False
    print(f"   [{tag}] 纯文本")
    for part in _split_telegram_text(text):
        ok = await _tg_post_with_retries(
            client,
            "sendMessage",
            json_body={"chat_id": TELEGRAM_CHAT_ID, "text": part},
        )
        ok_any = ok_any or ok
    return ok_any


def format_argument_layout(
    text: str,
    *,
    industry: str,
    evidence_scene: str | None = None,
    evidence_keywords: list[str] | None = None,
) -> str:
    """V8.1：按“论证感结构 + 证据感结构”排版，增强手机端视觉威压感。"""
    t = (text or "").strip()
    if not t:
        return ""
    # 提取 CTA 行
    lines = [x.strip() for x in t.splitlines() if x.strip()]
    cta_lines = [x for x in lines if any(k in x for k in ["同步思维逻辑", "获取执行模版", "开启主权并轨", "置顶", "模版", "执行路径"])]
    core_lines = [x for x in lines if x not in cta_lines]
    core = "\n".join(core_lines).strip()

    # 按 ①②③ 切段
    m = re.split(r"(?=(?:①|②|③))", core)
    m = [x.strip() for x in m if x.strip()]

    # 没有编号则按句号拆成短段
    if not any(("①" in x or "②" in x or "③" in x) for x in m):
        pieces = re.split(r"(?<=[。！？!?])", core)
        pieces = [p.strip() for p in pieces if p.strip()]
        # 组合为 3-5 句一段
        blocks: list[str] = []
        buf: list[str] = []
        for p in pieces:
            buf.append(p)
            if len(buf) >= 4:
                blocks.append("".join(buf))
                buf = []
        if buf:
            blocks.append("".join(buf))
        m = blocks if blocks else [core]

    out: list[str] = []
    out.append(f"【{industry}｜论坛排版｜论证拆解】")
    out.append("")
    # 结论段：取第一段前 1-2 句作为“结论”
    first = m[0] if m else core
    first_sent = re.split(r"(?<=[。！？!?])", first)
    first_sent = [x.strip() for x in first_sent if x.strip()]
    conclusion = "".join(first_sent[:2]) if first_sent else first
    out.append("【结论】")
    out.append(conclusion)
    out.append("")

    # 论证段
    out.append("【论证】")
    for idx, seg in enumerate(m[:3], 1):
        label = ["①", "②", "③"][idx - 1]
        seg2 = seg
        # 去掉重复编号符号，统一展示
        seg2 = seg2.lstrip("①②③").strip()
        out.append(f"{label} {seg2}")
        out.append("")

    # 收口 CTA
    out.append("【证据】")
    if evidence_scene:
        out.append(f"- 场景：{evidence_scene}")
    if evidence_keywords:
        kws = "、".join([k for k in evidence_keywords if k][:6])
        if kws:
            out.append(f"- 关键词：{kws}")
    if not evidence_scene and not evidence_keywords:
        out.append("- 证据位：本条为结构化拆解稿，可直接复制发帖")
    out.append("")

    if cta_lines:
        out.append("【收口】")
        out.extend(cta_lines[:3])

    return "\n".join(out).strip()


async def tg_send_mp3(client: httpx.AsyncClient, mp3_path: str, *, caption: str = "") -> bool:
    """消息②：发送 mp3 音频文件。"""
    try:
        print(f"   [投递②] 音频: {os.path.basename(mp3_path)}")
        fn = os.path.basename(mp3_path)
        with open(mp3_path, "rb") as f:
            return await _tg_post_with_retries(
                client,
                "sendAudio",
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                files={"audio": (fn, f, "audio/mpeg")},
            )
    except Exception as e:
        print(f"   [警告] 音频发送失败: {e}")
        return False


async def tg_send_jpg(client: httpx.AsyncClient, jpg_path: str, *, caption: str = "") -> bool:
    """消息③：发送背景图片（jpg）。"""
    try:
        print(f"   [投递③] 背景图: {os.path.basename(jpg_path)}")
        fn = os.path.basename(jpg_path)
        with open(jpg_path, "rb") as f:
            return await _tg_post_with_retries(
                client,
                "sendPhoto",
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                files={"photo": (fn, f, "image/jpeg")},
            )
    except Exception as e:
        print(f"   [警告] 背景图发送失败: {e}")
        return False


async def tg_send_mp4(client: httpx.AsyncClient, mp4_path: str, *, caption: str = "") -> bool:
    """消息④：发送最终 mp4 视频。"""
    try:
        print(f"   [投递④] 视频: {os.path.basename(mp4_path)}")
        fn = os.path.basename(mp4_path)
        with open(mp4_path, "rb") as f:
            return await _tg_post_with_retries(
                client,
                "sendVideo",
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "supports_streaming": "true"},
                files={"video": (fn, f, "video/mp4")},
            )
    except Exception as e:
        print(f"   [警告] 视频发送失败: {e}")
        return False


# V16.2：已删除 tg_send_flesh_bombs 函数（统帅指令：战术减重，核平冗余）

# === 血弹生产线 ===
async def generate_blood_bullet(
    client,
    index,
    base_dir,
    industry,
    folder,
    semaphore=None,
    visual_engine: VisualEngine | None = None,
    render_semaphore: asyncio.Semaphore | None = None,
):
    """V3 血弹生产线 - 全量变量预初始化，严禁块外引用块内变量"""

    # ============================================================
    # 强制初始化协议：所有变量在 try 之前一次性声明
    # ============================================================
    hook = random.choice(HOOKS)
    pain = random.choice(PAINS)
    ending = random.choice(ENDINGS)
    
    # 酒魔人设主权：随机抽取口头禅
    jiumo_slogan = random.choice(JIUMO_SLOGANS)
    
    # 核心锚点：随机3选
    core_anchors = random.sample(CORE_ANCHORS, 3)
    anchors_text = "、".join(core_anchors)

    # V10.0：随机风格引擎 + 攻击角度轮换（避免机械感）
    v10_style = _pick_nonrepeating(industry, V10_STYLE_POOL, _LAST_STYLE_BY_INDUSTRY)
    v10_style_prompt = V10_STYLE_ALIAS.get(v10_style, v10_style)
    v10_angle = _pick_nonrepeating(industry, V10_ATTACK_ANGLES, _LAST_ANGLE_BY_INDUSTRY)

    # 2026 创始人主权觉醒词库：随机抽取 1 个分类 + 3 个关键词（严禁串词）
    founder_lexicon = load_founder_lexicon()
    lexicon_category = random.choice(list(founder_lexicon.keys()))
    lexicon_keywords_list = random.sample(founder_lexicon[lexicon_category], 3)
    lexicon_keywords = "、".join(lexicon_keywords_list)

    # 行业噩梦关键词组：只从该行业池抽取 3 个（严禁串词）
    nightmare_pool = INDUSTRY_NIGHTMARE_KEYWORDS.get(industry, [])
    nightmare_keywords_list = random.sample(nightmare_pool, 3) if len(nightmare_pool) >= 3 else nightmare_pool
    nightmare_keywords = "、".join(nightmare_keywords_list)

    # V8.4 血肉炸弹：提前生成（用于视觉联动 + Prompt 注入 + Telegram 消息⑤）
    # V8.7：自媒体/做IP 抽 10；其他行业 3
    bomb_limit = 10 if str(industry).strip() in {"自媒体", "做IP"} else 3
    flesh_bombs_list = sanitize_flesh_bombs_v84(generate_flesh_bombs_v84(industry), limit=bomb_limit)

    # V10.0：自媒体/做IP 主语化开场（从破甲弹中抽 2 枚）
    v10_subject_piercers: list[str] = []
    if str(industry).strip() in {"自媒体", "做IP", "IP"} and len(flesh_bombs_list) >= 2:
        try:
            v10_subject_piercers = random.sample([x for x in flesh_bombs_list if x], 2)
        except Exception:
            v10_subject_piercers = [x for x in flesh_bombs_list if x][:2]

    # V7.0 视觉索引：根据分类/关键词生成安全视觉配置
    visual_engine = visual_engine or VisualEngine(safe_mode=True)
    visual_profile = visual_engine.select_visual_profile(
        industry=industry,
        lexicon_category=lexicon_category,
        lexicon_keywords=lexicon_keywords_list,
        nightmare_keywords=nightmare_keywords_list,
        flesh_bombs=flesh_bombs_list,
    )
    # V14.3：水印状态物理重置（禁用“自愈”字样）
    visual_profile["watermark_text"] = f"{industry} · 核心拆解"
    # V13.5：动态缝合需要行业名（用于索引 Jiumo_Auto_Factory/{industry}）
    visual_profile["_industry"] = industry

    # V15.1：音频生成成功后强制走“自媒体”视频池（严禁黑底/静默回退）
    # （video_stitcher 内会优先 root/自媒体 扫描；此处同时给出强制子目录提示）
    if str(industry).strip() == "自媒体":
        try:
            visual_profile["_force_factory_subdir"] = "自媒体"
            visual_profile["bg"] = {"type": "video", "path": "FORCE_SELF_MEDIA_POOL"}
        except Exception:
            pass
    
    # 行业痛点场景
    pain_scene = INDUSTRY_PAIN_SCENES.get(industry, "深夜看账本，发现这个月又是负数，满身疲惫")
    
    content = ""          # 原始文案
    clean_text = ""       # 断句后文案
    el_resp = None        # ElevenLabs 响应
    audio_path = None     # 音频物理路径
    video_path = None     # 视频物理路径
    video_ok = False      # 视频缝合结果
    err = None            # 错误原因

    # V8.0：零件库物理落盘（/output/text|audio|image|video）
    v8_mode = (os.getenv("V8_MODE") or "").strip() == "1"
    bg_jpg_path = None    # 背景图（jpg）物理路径

    if v8_mode:
        # base_dir 作为 output 根目录（由 main / 监听模式传入或 OUTPUT_BASE_DIR 覆盖）
        output_root = Path(base_dir).resolve()
        text_dir = output_root / "text" / industry
        audio_dir = output_root / "audio" / industry
        image_dir = output_root / "image" / industry
        video_dir = output_root / "video" / industry
        text_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)
        image_dir.mkdir(parents=True, exist_ok=True)
        video_dir.mkdir(parents=True, exist_ok=True)
        script_dir = text_dir
    else:
        # V31.0：路径物理降维（纯英文，核平中文路径炸膛隐患）
        industry_dir = base_dir / folder
        audio_dir = industry_dir / "audio"
        video_dir = industry_dir / "video"
        script_dir = industry_dir / "text"
    
    # 白酒垂直模型：如果是白酒行业，注入垂直关键词
    baijiu_keyword = ""
    if industry == "白酒":
        baijiu_keyword = random.choice(BAIJIU_KEYWORDS)

    # V15.8：文件名物理降维（纯英文/数字，核平乱码隐患）
    ts = int(time.time())
    name = f"task_{ts}"
    af = f"{name}.mp3"
    vf = f"{name}.mp4"
    sf = f"{name}.txt"  # 文案文件
    bf = f"{name}.bombs.txt"  # 炸弹清单（V8.4）
    audio_path = audio_dir / af
    video_path = video_dir / vf
    script_path = script_dir / sf
    bombs_path = script_dir / bf
    # V15.8：中文标签仅用于 Telegram caption，不污染物理磁盘
    display_name = f"【行业拆解】_{industry}_{ts}"
    if v8_mode:
        bg_jpg_path = (image_dir / f"{name}.jpg")
        try:
            # 若本次背景为视频（V13.5），则不强制改写为 jpg；jpg 仅用于零件③验收
            orig_bg = visual_profile.get("bg") if isinstance(visual_profile, dict) else {}
            orig_bg_type = ""
            try:
                orig_bg_type = str((orig_bg or {}).get("type") or "").lower()
            except Exception:
                orig_bg_type = ""
            ok_bg = export_background_jpg(industry=industry, visual_profile=visual_profile, output_jpg=bg_jpg_path)
            # V8.1：视频合成瞬间必须引用“成功发送的那张 jpg 零件”
            if ok_bg and bg_jpg_path.exists() and orig_bg_type != "video":
                visual_profile["bg"] = {"type": "image", "path": str(bg_jpg_path)}
        except Exception:
            # 背景导出失败不阻塞生产线（视频仍可走渐变/视频兜底）
            pass

    # V8.4：血肉炸弹落盘（给 SaaS/封面文案复用）
    try:
        with open(bombs_path, "w", encoding="utf-8") as f:
            for b in flesh_bombs_list:
                f.write(f"{b}\n")
    except Exception:
        pass

    print(f"\n[点火] [{index}/{len(INDUSTRIES)}] 正在为【{industry}】锻造血弹...")
    print(f"   [锚定] {name}")

    try:
        # === 1. DeepSeek 文案（爆款 5 步公式） ===
        seed_ns = time.time_ns()
        seed_headers = {"X-Seed-NS": str(seed_ns)}
        flesh_bombs_text = "\n".join([f"- {x}" for x in flesh_bombs_list if x])
        prompt_template = {
            "model": "deepseek-chat",
            "temperature": 0.9,
            "top_p": 0.95,
            "messages": [
                {
                    "role": "system",
                    "content": render_system_prompt(
                        seed_ns=seed_ns,
                        jiumo_slogan=jiumo_slogan,
                        lexicon_category=lexicon_category,
                        lexicon_keywords=lexicon_keywords,
                        nightmare_keywords=nightmare_keywords,
                        flesh_bombs=flesh_bombs_text,
                    )
                },
                {
                    "role": "user",
                    "content": "\n".join([
                        f"目标行业：{industry}",
                        # V44.3：顶级操盘手身份主权注入
                        "你现在的身份是：一个顶级的短视频操盘手专家，专门为百万级账号策划爆款脚本。",
                        "你的任务是策划一套能够突破百万播放量的爆款脚本，每个字都必须精准刺穿用户的认知防线。",
                        f"V10.0 风格引擎：{v10_style_prompt}（只按风格写，不要输出风格名称）",
                        f"V10.0 攻击角度：{v10_angle}（本篇只允许一个角度，禁止复刻上一次句式）",
                        f"深夜噩梦场景：{pain_scene}",
                        f"融合关键词：{hook}、{pain}、{ending}",
                        f"核心锚点（必须全部出现）：{anchors_text}",
                        f"核心爆破点（必须全部出现）：{lexicon_keywords}",
                        f"行业噩梦关键词组（必须全部出现）：{nightmare_keywords}",
                        f"行业物理碎片（必须在①②③论证中原样引用至少1条）：\n{flesh_bombs_text}",
                        # V44.3：说人话死令——绝对禁止学术装逼
                        "【语气死令：绝对禁止学术装逼】",
                        "- 严禁使用诸如'赛博'、'底层逻辑'、'结构性'、'能级'等拗口的互联网黑话或学术名词！",
                        "- 必须用最接地气、最口语化的'人话'写！",
                        "- 像一个冷酷的老板在酒桌上教训人，一针见血，字字扎心。",
                        "- 用短句！用大白话！拒绝长篇大论的复杂定语！",
                        (
                            "V10.0 禁词熔断：严禁出现这些词及其变体："
                            "骗局、割韭菜、暴利、套路、揭秘、底层、诱导、微信、赚钱、上岸、真相。"
                        ),
                        (
                            "V13.91 战术减重死命令：文案总长度严禁超过150字符。"
                            "每句话控制在8-10字以内。只要精华，删除废话。"
                            "严禁出现：首先、总之、真相是。"
                        ),
                        (
                            "V14.1 百字核平：输出必须是直击灵魂的短句。"
                            "总字数严禁超过80字。"
                            "剔除所有形容词，只留动词和名词。"
                        ),
                        (
                            "V10.0 短句断行：每句不超过10字，尽量不用逻辑连词（因为/所以/但是/然而/同时/如果/那么/然后）。"
                            "每句尽量独立成行。"
                        ),
                        (
                            f"V10.0 主语破甲弹：开头15字内必须出现其一并作为主语，且紧跟 ... ... 停顿："
                            f"{v10_subject_piercers[0]} / {v10_subject_piercers[1]}"
                        ) if len(v10_subject_piercers) == 2 else "",
                        f"白酒垂直关键词（必须包含）：{baijiu_keyword}" if baijiu_keyword else "",
                        (
                            "V8.7 自媒体/做IP 特规：你会收到 10 枚破甲弹词。"
                            "必须在①②③论证中引用其中至少 3 枚，并倒推每枚背后的商业定性。"
                            "若出现“赛博地主”，必须讨论“数字收租/数字收租模型”。"
                        ) if str(industry).strip() in ["自媒体", "做IP", "IP"] else "",
                        # V44.3：核心爆款要求
                        "核心要求：",
                        "- 观点极端犀利，节奏连环刺激，剔除所有文学修饰废话。",
                        "- 必须含：深度干货、情绪钩子、引起阶级共鸣的真实场景。",
                        "- 结尾硬锁死：以一个让人停止刷屏的'金句'作为灵魂升华。",
                        "要求：狠、短、可拍、可上屏。每段开头必须先抛一个生肉关键词，再接一句场景。",
                        "严禁套话，禁止泛泛而谈，必须贴合实际行业痛点，让看到的人产生强烈的自我代入感。"
                    ]).strip()
                }
            ]
        }
        prompt_payload = copy.deepcopy(prompt_template)

        ds = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", **seed_headers},
            json=prompt_payload,
            timeout=120.0
        )

        if ds.status_code != 200:
            err = f"DeepSeek API 失败: {ds.status_code}"
            raise Exception(err)

        content = ds.json()["choices"][0]["message"]["content"].strip()

        # === 逻辑清洗：去复读/去乱码/去偏旁部首幻觉 ===
        content = sanitize_final_text(content, industry=industry)

        # === 收口语：公域隐身（禁诱导词） ===
        cta_hooks = [
            "\n\n如果你要同步思维逻辑，我把执行路径写成了可复制的步骤。",
            "\n\n如果你要获取执行模版，我会把关键变量拆成清单，照做就行。",
            "\n\n如果你要开启主权并轨，就从今天把一个动作做到可重复。",
            "\n\n把你现在的现状写清楚，我只按事实把路径校准。"
        ]
        
        # 白酒行业专属CTA
        if industry == "白酒":
            cta_hooks.append("\n\n白酒这条线，我只讲原酒主权与定价权。要获取执行模版，就按这套结构把变量填满。")
        
        # 创业/餐饮专属CTA
        if industry in ["创业", "餐饮"]:
            cta_hooks.append("\n\n创业与餐饮的结构性误差如何拆解，我已经写成同步思维逻辑的步骤。照做即可。")

        # V44.0：100 枚金句导弹并轨 CTA 池（随机抽 1 枚注入收口）
        if GOLDEN_SENTENCES_100:
            try:
                cta_hooks.append("\n\n" + random.choice(GOLDEN_SENTENCES_100))
            except Exception:
                pass

        final_text = sanitize_final_text(content + random.choice(cta_hooks), industry=industry)

        # V10.0：破甲弹后强制 ... ... 停顿（非线性节奏）
        if str(industry).strip() in {"自媒体", "做IP", "IP"}:
            pause_terms = [x for x in (v10_subject_piercers or []) if x]
            # 为了保证“引用到的破甲弹”后都能出现停顿，顺带覆盖整组破甲弹（最多 10）
            pause_terms.extend([x for x in flesh_bombs_list[:10] if x])
            final_text = inject_term_pauses(final_text, pause_terms)

            # V10.0：主语化开场硬锁死（若模型未在前 15 字内命中，则强制前置）
            if len(v10_subject_piercers) == 2:
                hit_early = any((final_text.find(t) != -1 and final_text.find(t) < 15) for t in v10_subject_piercers)
                if not hit_early:
                    # 双行主语化：两枚破甲弹都在开头直接甩出（不做铺垫）
                    final_text = (
                        f"{v10_subject_piercers[0]} ... ...\n"
                        f"{v10_subject_piercers[1]} ... ...\n"
                        f"{final_text}"
                    )

        # V10.0：短句断行（不截断语义，仅拆行）
        final_text = v10_wrap_short_lines(final_text, max_len=12, protect_terms=(flesh_bombs_list[:10] if str(industry).strip() in {"自媒体", "做IP", "IP"} else None))

        # V15.6：八十字硬锁死——超过 80 字符则暴力截断并记录日志
        # 同时先剔除虚词（的/了/着），制造冷硬语感
        final_text = strip_function_words_v142(final_text)
        if len(final_text) > 80:
            try:
                log_root = Path(base_dir).resolve()
                lp = (log_root / "length_truncations.log")
                with open(lp, "a", encoding="utf-8") as f:
                    head_preview = final_text[:60].replace("\n", " ")
                    f.write(
                        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\t"
                        f"industry={industry}\tlen={len(final_text)}\tcut=80\t"
                        f"head={head_preview}\n"
                    )
            except Exception:
                pass
            final_text = final_text[:80].rstrip()

        # V10.0：自检机制（detect_risk_hits → 二次物理平替 → 再检测）
        risk_hits = detect_risk_hits(final_text)
        if risk_hits:
            repaired = apply_risk_control_replacements(final_text)
            repaired = sanitize_final_text(repaired, industry=industry)
            repaired = v10_wrap_short_lines(
                repaired,
                max_len=12,
                protect_terms=(flesh_bombs_list[:10] if str(industry).strip() in {"自媒体", "做IP", "IP"} else None),
            )
            risk_hits2 = detect_risk_hits(repaired)
            if not risk_hits2:
                final_text = repaired
            else:
                raise RiskAlertException("、".join(sorted(set(risk_hits2))))

        # V13.5：字幕输入源锁定（文案均匀烧录到视频下方）
        try:
            # V13.8：总装流程闭环——字幕文本先清洗，防止特殊符号碎裂滤镜链/乱码
            s = str(final_text)
            s2 = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9，。]", "", s)
            visual_profile["subtitle_text"] = (s2 or s)[:2000]
        except Exception:
            pass

        # V8.4 视觉联动（文案真实命中）：命中“废旧轮胎”优先用 assets/visuals/汽修/ 素材图
        try:
            override_bg = visual_engine.pick_visual_override_for_text(industry=industry, text=final_text)
            if override_bg:
                visual_profile["bg"] = {"type": "image", "path": str(override_bg)}
        except Exception:
            pass

        # === 发送 ElevenLabs 前：口播纯净化（物理隔离元数据/标号/标签） ===
        tts_text = sanitize_final_text(final_text, industry=industry, for_tts=True)
        # V8.1：每段论证强制注入停顿威压
        tts_text = inject_logical_pauses(tts_text)
        # V8.3：术语沉思停顿（如“选题权”）
        tts_text = inject_term_pauses(tts_text, ["选题权"])

        # 物理断句（中式停顿）
        clean_text = tts_text.replace("。", "... ... ").replace("！", "... ... ").replace("？", "... ... ")

        print(f"   [文案] 已生成 ({len(clean_text)} 字)")
        
        # 保存文案到文案库
        try:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(f"【行业】{industry}\n")
                f.write(f"【口头禅】{jiumo_slogan}\n")
                f.write(f"【核心锚点】{anchors_text}\n")
                if baijiu_keyword:
                    f.write(f"【白酒关键词】{baijiu_keyword}\n")
                f.write(f"【时间戳】{ts}\n")
                f.write(f"\n{'='*60}\n\n")
                f.write(final_text)
            print(f"   [文案] 已归档: {sf}")
        except Exception as e:
            print(f"   [警告] 文案归档失败: {e}")

        # === 2. 音频引擎（ElevenLabs 主火控 + V13.9 副火控） ===
        segments = split_text_for_tts(clean_text, max_chars=80)
        seg_paths: list[Path] = []
        used_fallback_tts = False
        try:
            if len(segments) > 1:
                print(f"   [音频] 文案过长，分段合成: {len(segments)} 段")

            for si, seg in enumerate(segments, 1):
                seg_path = audio_dir / f"{name}.seg{si}.tmp.mp3"
                seg_paths.append(seg_path)

                el_resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
                    headers={"xi-api-key": ELEVENLABS_API_KEY, "X-Seed-NS": str(time.time_ns())},
                    json={
                        "text": seg,
                        "model_id": "eleven_v3",
                        "voice_settings": {
                            "stability": ELEVEN_STABILITY,
                            "similarity_boost": ELEVEN_SIMILARITY_BOOST
                        }
                    },
                    timeout=120.0
                )

                if el_resp.status_code != 200:
                    err = f"ElevenLabs V3 引擎失败: {el_resp.status_code}"
                    try:
                        err += f" - {el_resp.text[:200]}"
                    except Exception:
                        pass
                    low = err.lower()
                    # V13.9/V13.91：额度熔断识别（quota_exceeded/credit/insufficient/401/429）
                    if ("quota" in low) or ("exceeded" in low) or ("insufficient" in low) or ("credit" in low) or (el_resp.status_code in (401, 429)):
                        raise ElevenQuotaExceeded(err, status_code=int(el_resp.status_code))
                    raise Exception(err)

                with open(seg_path, "wb") as f:
                    f.write(el_resp.content)

            # 合并分段音频
            if len(seg_paths) == 1:
                if v8_mode:
                    # V8.0：保留临时片段，另存一份成品 mp3
                    try:
                        audio_path.write_bytes(seg_paths[0].read_bytes())
                    except Exception:
                        seg_paths[0].replace(audio_path)
                else:
                    seg_paths[0].replace(audio_path)
            else:
                concat_mp3_ffmpeg(seg_paths, audio_path)

            # V8.1：音频质量锁死（44.1kHz）
            ensure_mp3_44100(audio_path)

            print(f"   [音频] 已生成: {af}")
        except ElevenQuotaExceeded as exc_q:
            # V13.9：静默切换副火控（不抛错，不炸膛）
            used_fallback_tts = True
            # V13.91：401 额度熔断专用预警文案
            try:
                if getattr(exc_q, "status_code", None) == 401:
                    print("[系统预警] 统帅，重火力额度耗尽，已自动装填轻型电子弹（Edge TTS）继续执行任务！")
            except Exception:
                pass
            try:
                # 清理临时片段（避免误用）
                for p in seg_paths:
                    try:
                        if p.exists():
                            p.unlink()
                    except Exception:
                        pass
            except Exception:
                pass

            # V14.2：401 quota_exceeded 时强制 edge-tts 指定音色，并强制走 media 生肉素材（禁止黑底）
            if getattr(exc_q, "status_code", None) == 401:
                try:
                    await tts_edge_force_mp3(clean_text, audio_path, voices=["zh-CN-YunxiNeural", "zh-CN-XiaoxiaoNeural"])
                    print(f"   [音频] edge-tts 强制音色已装填: {af}")
                except Exception:
                    await tts_fallback_to_mp3(clean_text, audio_path, industry=str(industry))

                try:
                    visual_profile["_force_factory_subdir"] = "media"
                    # 触发动态缝合分支
                    visual_profile["bg"] = {"type": "video", "path": "FORCE_MEDIA_POOL"}
                except Exception:
                    pass
            else:
                await tts_fallback_to_mp3(clean_text, audio_path, industry=str(industry))
            print(f"   [音频] 已降级，继续生产线: {af}")
        finally:
            # V8.0：严禁发送后删除临时文件（用于统帅验收零件）
            if not v8_mode:
                for p in seg_paths:
                    try:
                        if p.exists():
                            p.unlink()
                    except Exception:
                        pass

        # === 3. 视频缝合 ===
        # V15.7：阻塞式缝合（宁可慢 5 秒，确保成品物理产出）
        try:
            if render_semaphore:
                async with render_semaphore:
                    video_ok, _ = await asyncio.to_thread(
                        video_stitcher,
                        str(audio_path),
                        str(video_path),
                        visual_profile=visual_profile,
                    )
            else:
                video_ok, _ = await asyncio.to_thread(
                    video_stitcher,
                    str(audio_path),
                    str(video_path),
                    visual_profile=visual_profile,
                )
            if not video_ok:
                err = "视频缝合失败"
                # V16.2：缝合失败——发送完整 ffmpeg.log
                try:
                    log_path = str(video_path) + ".ffmpeg.log"
                    if Path(log_path).exists():
                        log_content = Path(log_path).read_text(encoding="utf-8", errors="ignore")
                        # Telegram 单条消息限制 4096 字符，分批发送
                        header = "🔴 缝合炸膛：FFmpeg 完整日志\n" + "="*40 + "\n"
                        await tg_send_text_only(client, header + log_content[:3500], tag="缝合失败")
                    else:
                        await tg_send_text_only(client, "🔴 缝合炸膛：路径转义异常，请查阅终端日志（ffmpeg.log 未生成）", tag="缝合失败")
                except Exception:
                    pass
        except Exception as exc:
            video_ok = False
            err = f"视频缝合异常: {exc}"
            print(f"   [警告] {err}")
            # V16.2：缝合异常——发送详细错误
            try:
                log_path = str(video_path) + ".ffmpeg.log"
                if Path(log_path).exists():
                    log_content = Path(log_path).read_text(encoding="utf-8", errors="ignore")
                    header = f"🔴 缝合炸膛：{str(exc)[:100]}\n" + "="*40 + "\n"
                    await tg_send_text_only(client, header + log_content[:3400], tag="缝合异常")
                else:
                    await tg_send_text_only(client, f"🔴 缝合炸膛：{str(exc)[:200]}", tag="缝合异常")
            except Exception:
                pass

        # V23.0：成品归位逻辑（云端/本地双模式）
        try:
            if video_ok and video_path and Path(video_path).exists():
                # V23.0：云端环境直接发送，不落盘到 Final_Out
                if IS_CLOUD_ENV:
                    print(f"   [云端模式] 成品已生成，准备直接投递: {Path(video_path).name}")
                else:
                    # 本地环境：物理归位到 Final_Out/
                    final_out_dir = Path(os.getenv("FINAL_OUT_DIR", "./Final_Out"))
                    final_out_dir.mkdir(parents=True, exist_ok=True)
                    ts2 = int(time.time())
                    final_out_file = final_out_dir / f"output_{ts2}.mp4"
                    # V16.1：物理覆盖模式（确保统帅始终看到最新成品）
                    try:
                        if final_out_file.exists():
                            final_out_file.unlink()
                    except Exception:
                        pass
                    try:
                        shutil.copy2(str(video_path), str(final_out_file))
                        print(f"   [成品] 已物理归位到 Final_Out/: {final_out_file.name}")
                    except Exception as e:
                        print(f"   [警告] 成品归位失败: {e}")
                    
                    # V16.1：物理检测（成品破壳验证）
                    if not final_out_file.exists():
                        print(f"   !!! 报错：成品未能在物理磁盘生成，检查 FFmpeg 日志")
                        print(f"   !!! 目标路径: {final_out_file}")
        except Exception as e:
            print(f"   [警告] 成品导出异常: {e}")

        # === 4. Telegram 投递 ===
        if v8_mode:
            # SaaS/PTB 模式：仅生成零件并落盘，不走旧 Telegram 投递（由上层负责发送）
            if (os.getenv("V8_SKIP_TG") or "").strip() == "1":
                print("   [投递] V8_SKIP_TG=1：已跳过旧 Telegram 投递（零件已落盘）")
            else:
                # V8.0：五条独立消息顺序投递（文案/音频/背景/视频/炸弹）
                try:
                    # 消息①：纯文案（论坛排版 + 证据感结构）
                    await tg_send_text_only(
                        client,
                        format_argument_layout(
                            final_text,
                            industry=industry,
                            evidence_scene=pain_scene,
                            evidence_keywords=(nightmare_keywords_list or []) + (lexicon_keywords_list or []),
                        ),
                        tag="投递①",
                    )
                    # 消息②：mp3
                    await tg_send_mp3(client, str(audio_path), caption=f"{industry} 音频零件")
                    # 消息③：背景 jpg（若不存在则临时生成兜底图）
                    if bg_jpg_path is None:
                        bg_jpg_path = Path(str(audio_path) + ".bg.jpg")
                    if not bg_jpg_path.exists():
                        try:
                            export_background_jpg(industry=industry, visual_profile=visual_profile, output_jpg=bg_jpg_path)
                        except Exception:
                            pass
                    if bg_jpg_path.exists():
                        await tg_send_jpg(client, str(bg_jpg_path), caption=f"{industry} 背景零件")
                    # 消息④：mp4（兜底成品）
                    # V23.0：云端环境自动清理成品（发送后删除）
                    if video_path and Path(video_path).exists():
                        await tg_send_mp4(client, str(video_path), caption=f"{industry} 成品视频")
                        if IS_CLOUD_ENV:
                            try:
                                Path(video_path).unlink()
                                print(f"   [云端清理] 成品已发送并删除: {Path(video_path).name}")
                            except Exception:
                                pass
                    # V16.2：已删除炸弹投递（战术减重）
                except Exception as exc:
                    print(f"   [投递异常] {exc}")
        else:
            # V7.9 空测模式可跳过，不影响落盘
            if (os.getenv("V79_DRY_RUN") or "").strip() == "1":
                print("   [投递] V7.9 空测模式：已跳过 Telegram 投递")
            else:
                try:
                    await tg_notifier(
                        client,
                        vf if video_ok else af,
                        clean_text,
                        str(video_path) if video_ok else str(audio_path),
                        not video_ok,
                        err,
                        industry,
                        str(video_dir) if video_ok else str(audio_dir),
                        semaphore=semaphore
                    )
                except Exception as exc:
                    print(f"   [投递异常] {exc}")

        if video_ok:
            print(f"[成功] 【{industry}】血弹已入库: {vf}")
        else:
            print(f"[部分成功] 【{industry}】音频已生成，视频缝合失败")
        
        # V23.5：自动垃圾回收（物理粉碎临时文件）
        if IS_CLOUD_ENV:
            try:
                # 清理音频临时文件
                if audio_path and Path(audio_path).exists():
                    Path(audio_path).unlink()
                    print(f"   [垃圾回收] 已粉碎音频临时文件: {Path(audio_path).name}")
                
                # 清理背景图临时文件
                if bg_jpg_path and bg_jpg_path.exists():
                    bg_jpg_path.unlink()
                    print(f"   [垃圾回收] 已粉碎背景临时文件: {bg_jpg_path.name}")
                
                # 清理视频临时文件（如果还存在）
                if video_path and Path(video_path).exists():
                    Path(video_path).unlink()
                    print(f"   [垃圾回收] 已粉碎视频临时文件: {Path(video_path).name}")
                
                # 清理文案临时文件
                if script_path and script_path.exists():
                    script_path.unlink()
                
                print(f"   [垃圾回收] /tmp 临时文件已物理粉碎，仅保留成品已回传统帅")
            except Exception as e:
                print(f"   [垃圾回收] 清理警告: {e}")
        
        return video_ok

    except RiskAlertException as exc:
        # V8.8：风控流弹拦截——不进入 ElevenLabs，不进入视频合成
        msg = "🔴 警告：检测到违禁词流弹，系统已物理拦截，正在重新装药。"
        try:
            print(f"[拦截] 【{industry}】{msg} (命中: {exc})")
        except Exception:
            pass
        # 若是旧 Telegram 投递链路，反馈给统帅；SaaS 模式（V8_SKIP_TG）交由上层处理
        try:
            if v8_mode and (os.getenv("V8_SKIP_TG") or "").strip() != "1":
                await tg_send_text_only(client, msg, tag="拦截")
        except Exception:
            pass
        await asyncio.sleep(1)
        return False

    except Exception as exc:
        err = str(exc)
        print(f"[哑火] 【{industry}】{err}")
        traceback.print_exc()
        await asyncio.sleep(5)  # 静默等待：避免 Provider Error 断联后连锁崩溃
        return False

# === Git 提交 ===
def auto_commit():
    """Git 自动提交"""
    try:
        subprocess.run(["git", "add", "."], check=True, timeout=10, capture_output=True)
        subprocess.run(["git", "commit", "-m", "iteration: V3 production auto-evolution"], 
                      check=True, timeout=10, capture_output=True)
        print("[提交] 自动提交完成")
        print("[统帅验收] 本批次已入库，Git 镜像已同步")
        return True
    except subprocess.CalledProcessError:
        print("[提交] 无变更需要提交")
        return False
    except Exception as e:
        print(f"[提交] 提交失败: {e}")
        return False

# === 自动净空 ===
def physical_cleanup_output_lib():
    """
    V23.0：阵地全线净空协议（云端/本地双模式）
    - 云端环境：清理 /tmp/output
    - 本地环境：清理用户指定路径或 ./output
    - 正则检测：凡是包含中文字符的文件，一律物理删除
    - 保护逻辑：严禁删除文件夹本身，必须保留目录结构
    """
    if IS_CLOUD_ENV:
        output_dir = Path("/tmp/output")
    else:
        output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
    
    if not output_dir.exists():
        print("[净空] output 目录不存在，跳过清场")
        return
    
    # 中文字符检测正则（Unicode 中文范围）
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
    cleaned = 0
    
    try:
        # 深度遍历所有文件（不包括目录）
        for item in output_dir.rglob("*"):
            if item.is_file():
                # 检测文件名是否包含中文字符
                if chinese_pattern.search(item.name):
                    try:
                        item.unlink()  # 物理删除，严禁进入回收站
                        cleaned += 1
                        print(f"[净空] 已核平: {item.name}")
                    except Exception as e:
                        print(f"[警告] 无法删除 {item.name}: {e}")
        
        print(f"[净空] 报告统帅：已清理 {cleaned} 个旧时代残余文件，输出库已实现全英文净空！")
    except Exception as e:
        print(f"[警告] 净空过程异常: {e}")


def auto_cleanup(base_dir):
    """全自动净空：清理临时文件"""
    print("\n[净空] 开始清理临时文件...")
    cleaned = 0
    for tmp_file in base_dir.rglob("*.tmp"):
        try:
            tmp_file.unlink()
            cleaned += 1
            print(f"[净空] 已删除: {tmp_file.name}")
        except Exception as e:
            print(f"[警告] 无法删除 {tmp_file.name}: {e}")
    
    if cleaned > 0:
        print(f"[净空] 共清理 {cleaned} 个临时文件")
    else:
        print("[净空] 归档区保持整洁 - 无需清理")

# === 主控系统 ===
async def main():
    """V3 主控流程"""
    
    # V16.9：启动即清场——战区净空协议
    physical_cleanup_output_lib()
    
    print("="*60)
    print("冷酷军师·V3 架构")
    print("="*60)

    # V15.2：点火前暴力自检（mp4=0 直接熔断停止）
    firecontrol_preflight_or_die()
    
    # === 配置校验 ===
    v79_mode = (os.getenv("V79_DRY_RUN") or "").strip() == "1"

    # 空测模式不依赖 Telegram（只要能落盘即可）
    if not v79_mode:
        if not TELEGRAM_BOT_TOKEN or not validate_token(TELEGRAM_BOT_TOKEN):
            print("\n[错误] TELEGRAM_BOT_TOKEN 无效或缺失")
            return
        
        if not TELEGRAM_CHAT_ID:
            print("\n[错误] TELEGRAM_CHAT_ID 缺失")
            return
    else:
        if not TELEGRAM_BOT_TOKEN or not validate_token(TELEGRAM_BOT_TOKEN) or not TELEGRAM_CHAT_ID:
            print("\n[提示] V7.9 空测模式：Telegram 未配置或无效，将仅执行本地落盘闭环")
    
    if not check_ffmpeg():
        print("\n[中止] FFmpeg 未安装")
        return
    
    # === 懒加载身份 ===
    lazy_load_identity()
    
    # === 创建目录结构 ===
    today = datetime.now().strftime("%Y-%m-%d")
    v8_mode = (os.getenv("V8_MODE") or "").strip() == "1"
    override_base = (os.getenv("OUTPUT_BASE_DIR") or "").strip().strip('"').strip("'")
    if not override_base and v8_mode:
        override_base = "output"
    if override_base:
        base_dir = Path(override_base).resolve()
    else:
        base_dir = Path(f"01-内容生产/成品炸弹/{today}").resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    print(f"[输出] 基础目录: {base_dir}")
    
    print(f"\n[系统] 生产线已上线")
    if TELEGRAM_CHAT_ID:
        print(f"[系统] 目标群组: {TELEGRAM_CHAT_ID}")
    print(f"[系统] V3 引擎: eleven_v3")
    
    # === 权限测试 ===
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=5)
    if not v79_mode:
        print("\n[测试] 启动群组权限测试...")
        async with httpx.AsyncClient(timeout=120.0, limits=limits) as test_client:
            test_ok = await tg_notifier(
                test_client, 'SYSTEM_TEST', '[生产线点火测试]', 'NULL',
                True, None, 'SYSTEM', '系统测试 - 权限验证', None
            )
            print(f"[测试] {'权限已验证' if test_ok else '权限测试失败 - 继续执行'}")
    else:
        print("\n[测试] V7.9 空测模式：已跳过群组权限测试")
    
    # === 预创建目录 ===
    create_industry_dirs(base_dir)
    print("[统帅部] 视觉主权已全面合围，1000 发饱和打击请求点火！")
    try:
        factory_dir = os.getenv("JIUMO_FACTORY_DIR") or ""
        if factory_dir:
            print(f"[视觉] 视觉引信已物理连接: {factory_dir}")
    except Exception:
        pass
    
    # === 物理限流器：Semaphore(2) 单管循环 ===
    tg_semaphore = asyncio.Semaphore(2)
    print(f"[流控] Telegram 投递限流器已激活: 单管循环模式（最大并发 2）")

    # === V7.0 渲染队列：并发渲染上限 3 ===
    render_semaphore = asyncio.Semaphore(3)
    visual_engine = VisualEngine(safe_mode=True)
    
    # === 八大主权战区：全量开火 ===
    targets = INDUSTRIES  # 默认全部8个行业

    # === 单体行业测试开关（SINGLE_INDUSTRY=白酒/餐饮/创业/...） ===
    single_industry = (os.getenv("SINGLE_INDUSTRY") or "").strip().strip('"').strip("'")
    # PowerShell/控制台编码混用时，可能把 UTF-8 字节按 GBK 解读成“鐧介厭”这类乱码。
    # 这里做一次纠偏：把字符串按 GBK 编码回字节，再按 UTF-8 解码尝试还原。
    try:
        if single_industry:
            single_industry = single_industry.encode("gbk").decode("utf-8")
    except Exception:
        pass
    if single_industry:
        def _match_industry(x: dict) -> bool:
            name = str(x.get("name") or "").strip()
            folder = str(x.get("folder") or "").strip()
            if not name and not folder:
                return False
            # 允许：精确命中 / 子串命中 / 输入含编号前缀
            if single_industry == name or single_industry == folder:
                return True
            if name and (single_industry in name or name in single_industry):
                return True
            if folder and (single_industry in folder or folder in single_industry):
                return True
            return False

        picked = [x for x in INDUSTRIES if _match_industry(x)]
        if picked:
            targets = picked
            print(f"[测试] 单体行业模式已激活: {single_industry}")
        else:
            print(f"[警告] SINGLE_INDUSTRY={single_industry} 未命中行业列表，继续全量开火")
    
    # === 批量生产 ===
    print(f"[战争] 八大主权战区: {len(targets)} 个行业（全量开火模式）")
    for ind in targets:
        print(f"  - {ind['name']} -> {ind['folder']}")
    
    success = 0
    async with httpx.AsyncClient(timeout=120.0, limits=limits) as client:
        tasks = []
        for i, ind_cfg in enumerate(targets, 1):
            print(f"\n{'='*60}")
            print(f"[目标] 行业: {ind_cfg['name']}")
            print(f"{'='*60}")
            tasks.append(
                generate_blood_bullet(
                    client,
                    i,
                    base_dir,
                    ind_cfg["name"],
                    ind_cfg["folder"],
                    tg_semaphore,
                    visual_engine=visual_engine,
                    render_semaphore=render_semaphore,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for idx, result in enumerate(results, 1):
            if isinstance(result, Exception):
                print(f"[警告] 第 {idx} 发并行任务异常: {result}")
            elif result:
                success += 1

            # V7.8 极限压力维护：每完成 50 次任务，GC + 降温
            if idx % 50 == 0:
                gc.collect()
                print("[系统维护] 正在为生产线进行物理降温，请统帅稍候...")
                await asyncio.sleep(30)
    
    # === 结果汇总 ===
    print("\n" + "="*60)
    print(f"[结果] {success}/{len(targets)} 颗炸弹已部署")
    print(f"[位置] {base_dir}")
    print("="*60)
    
    # === 自动净空 ===
    if (os.getenv("V8_MODE") or "").strip() == "1":
        print("[净空] V8.0 零件模式：已跳过临时文件清理（保留全部零件）")
    else:
        auto_cleanup(base_dir)
    
    # === Git 提交 ===
    if success > 0:
        print("\n[提交] 启动自动提交...")
        auto_commit()


# =========================
# V8.9 SaaS 监听引擎（bot.py 内置）
# =========================
def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return (v or default).strip()


def _sanitize_industry_text(text: str) -> str:
    t = (text or "").strip()
    t = t.replace("【", "").replace("】", "")
    t = re.sub(r"\s+", "", t)
    return t[:50]


def _detect_industry_trigger(text: str) -> str | None:
    """
    V8.9：模糊指令雷达（纯文字唤醒）
    - 不要求任何特殊符号（如【】、/、命令前缀）
    - 只要消息中包含行业关键词（餐饮、自媒体、白酒、IP 等）即触发
    """
    raw = (text or "").strip()
    if not raw:
        return None
    norm = _sanitize_industry_text(raw)
    low = norm.lower()

    allow: list[str] = [str(x.get("name", "")).strip() for x in (INDUSTRIES or []) if str(x.get("name", "")).strip()]
    # 补充自媒体/做IP/IP 触发词（不依赖 INDUSTRIES）
    allow += ["自媒体", "做IP", "IP"]
    allow = list(dict.fromkeys([x for x in allow if x]))  # 去重保序

    for k in allow:
        if not k or k == "IP":
            continue
        if (k in raw) or (k in norm):
            return k

    if ("自媒" in raw) or ("自媒" in norm):
        return "自媒体"
    if "做ip" in low or "做ip" in raw.lower():
        return "做IP"
    if "ip" in low or "ip" in raw.lower():
        return "IP"
    return None


def _pick_latest_parts(base_dir: Path, industry: str) -> dict[str, Path | None]:
    root = base_dir.resolve()
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


async def _saas_pipeline_task(app: "Application", *, chat_id: int, industry: str) -> None:
    """
    后台任务：触发工厂生产，并按 V8.0 规范顺序投递 ①②③④⑤。
    生产阶段强制跳过旧 httpx Telegram 投递，统一由 PTB 发送。
    """
    # 让工厂进入零件模式落盘
    os.environ["V8_MODE"] = "1"
    os.environ["V8_SKIP_TG"] = "1"
    base_dir = Path(_env("OUTPUT_BASE_DIR", "output")).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    # folder：仅用于签名兼容（V8_MODE 下不走 folder 落盘）
    folder_map = {x["name"]: x["folder"] for x in (INDUSTRIES or []) if x.get("name") and x.get("folder")}
    folder = folder_map.get(industry, f"00-{industry}")

    try:
        try:
            await app.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass

        limits = httpx.Limits(max_keepalive_connections=5, max_connections=5)
        async with httpx.AsyncClient(timeout=120.0, limits=limits) as client:
            await generate_blood_bullet(
                client,
                1,
                base_dir,
                industry,
                folder,
                semaphore=None,
                visual_engine=VisualEngine(safe_mode=True),
                render_semaphore=asyncio.Semaphore(1),
            )

        parts = _pick_latest_parts(base_dir, industry)

        # ① 文案
        if parts["txt"]:
            txt = parts["txt"].read_text(encoding="utf-8", errors="ignore").strip()
            for i in range(0, len(txt), 3500):
                await app.bot.send_message(chat_id=chat_id, text=txt[i:i + 3500])

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

        # V16.2：已删除炸弹清单投递（战术减重）
    except Exception:
        try:
            await app.bot.send_message(chat_id=chat_id, text="🔴 系统算力全开中，请稍后再试")
        except Exception:
            pass


# V11.0：本地排队机（TaskQueue）——允许连发多行业，后台按序压制回传
_SAAS_TASK_QUEUE: "asyncio.Queue[tuple[int, str]]" = asyncio.Queue()


async def _saas_worker(app: "Application") -> None:
    while True:
        chat_id, industry = await _SAAS_TASK_QUEUE.get()
        try:
            await _saas_pipeline_task(app, chat_id=chat_id, industry=industry)
        finally:
            try:
                _SAAS_TASK_QUEUE.task_done()
            except Exception:
                pass


# V15.6：确保 worker 在 run_polling 后启动（避免 Application.create_task 警告）
_SAAS_WORKER_TASK: "asyncio.Task[None] | None" = None


def _ensure_saas_worker_started(app: "Application") -> None:
    global _SAAS_WORKER_TASK
    try:
        if _SAAS_WORKER_TASK and not _SAAS_WORKER_TASK.done():
            return
    except Exception:
        pass
    try:
        _SAAS_WORKER_TASK = asyncio.get_running_loop().create_task(_saas_worker(app))
    except Exception:
        _SAAS_WORKER_TASK = asyncio.create_task(_saas_worker(app))


async def start_callback(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    try:
        _ensure_saas_worker_started(context.application)
    except Exception:
        pass
    try:
        msg = update.effective_message
        if msg:
            await msg.reply_text(
                "【统帅部】雷达已在线。\n"
                "- 私聊：直接发送行业关键词（如：白酒/餐饮/自媒体/IP）\n"
                "- 群聊/频道：若隐私模式拦截普通消息，请用命令：/fire 自媒体"
            )
    except Exception:
        pass


async def fire_callback(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    """
    V40.4：群聊/频道生存触发器
    - 解决 Telegram 隐私模式导致普通文本不触发的问题
    - 统一走队列，保证“发一次就有回执”
    """
    msg = update.effective_message
    if not msg:
        return

    try:
        _ensure_saas_worker_started(context.application)
    except Exception:
        pass

    try:
        chat_id = int(update.effective_chat.id) if update.effective_chat else int(msg.chat_id)
    except Exception:
        return

    raw = ""
    try:
        raw = " ".join(getattr(context, "args", []) or [])
    except Exception:
        raw = ""
    raw = raw.strip() or str(getattr(msg, "text", "") or "")

    industry = _detect_industry_trigger(raw)
    if not industry:
        try:
            await msg.reply_text("用法：/fire 自媒体（或白酒/餐饮/创业/美容/汽修/医美/教培/婚庆）")
        except Exception:
            pass
        return

    try:
        await msg.reply_text(f"✓ 收到统帅指令：正在紧急调配【{industry}】行业弹药零件...")
    except Exception:
        pass

    try:
        pos = _SAAS_TASK_QUEUE.qsize() + 1
        _SAAS_TASK_QUEUE.put_nowait((chat_id, industry))
        if pos >= 2:
            try:
                await msg.reply_text(f"【排队】已加入队列，第 {pos} 位。")
            except Exception:
                pass
    except Exception:
        asyncio.create_task(_saas_pipeline_task(context.application, chat_id=chat_id, industry=industry))


async def industry_callback(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    msg = update.effective_message
    if not msg or not getattr(msg, "text", None):
        return

    try:
        _ensure_saas_worker_started(context.application)
    except Exception:
        pass

    try:
        chat_id = int(update.effective_chat.id) if update.effective_chat else int(msg.chat_id)
    except Exception:
        return
    industry = _detect_industry_trigger(str(msg.text))
    if not industry:
        return

    # 心跳：先回执，验证监听不死锁
    try:
        await msg.reply_text(f"✓ 收到统帅指令：正在紧急调配【{industry}】行业弹药零件...")
    except Exception:
        pass

    # V11.0：排队机模式（按序压制 + 回传），监听线程只负责入队
    try:
        pos = _SAAS_TASK_QUEUE.qsize() + 1
        _SAAS_TASK_QUEUE.put_nowait((chat_id, industry))
        # 只做轻量反馈，避免刷屏
        if pos >= 2:
            try:
                await msg.reply_text(f"【排队】已加入队列，第 {pos} 位。")
            except Exception:
                pass
    except Exception:
        # 兜底：直接后台触发（避免因为队列异常导致“脱靶”）
        asyncio.create_task(_saas_pipeline_task(context.application, chat_id=chat_id, industry=industry))


def main_saas() -> None:
    """
    V31.0：SaaS 监听主权入口（暴力云端填装）
    - 素材强制静默下载：云端启动时自动从 Google Drive 拉取素材
    - 链路诊断：物理清除 Webhook，离线任务重放
    """
    # V27.0：启动第一行 - 火控自检
    print("\n" + "="*60)
    print("✓ [火控自检] 正在尝试连接 Telegram API...")
    print("="*60 + "\n")

    # V39.5：云端存活端口（避免 CrashLoop 时无法观测）
    try:
        _start_minimal_health_server()
    except Exception:
        pass
    
    # V38.0：暴力降维——云端空仓不下载，强制 gradient 生存模式
    if IS_CLOUD_ENV:
        try:
            factory_root = Path("/tmp/Jiumo_Auto_Factory")
            selfmedia_dir = factory_root / "自媒体"
            try:
                selfmedia_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            mp4_count = 0
            try:
                if selfmedia_dir.exists():
                    mp4_count = len(list(selfmedia_dir.glob("*.mp4")))
            except Exception:
                mp4_count = 0
            if mp4_count <= 0:
                os.environ["JUNSHI_FORCE_GRADIENT_BG"] = "1"
                print("[生存协议] /tmp/Jiumo_Auto_Factory 空仓：已强制切换 gradient 背景模式（不下载，不停机）")
        except Exception as e:
            print(f"[生存协议] 检测空仓失败（已忽略）: {e}")
    
    # V29.0：云端素材自动补齐（启动第一秒）
    if IS_CLOUD_ENV:
        print("[素材补齐] 云端环境检测到，正在自动生成备用背景...")
        try:
            # 创建备用背景目录
            bg_dir = Path("/tmp/assets/bg")
            bg_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成纯色背景图（1280x720 黑底）
            bg_path = bg_dir / "default_bg.jpg"
            if not bg_path.exists():
                subprocess.run([
                    "ffmpeg", "-y", "-nostdin",
                    "-f", "lavfi",
                    "-i", "color=c=#1a1a1a:s=1280x720:d=1",
                    "-frames:v", "1",
                    str(bg_path)
                ], capture_output=True, timeout=10)
                
                if bg_path.exists():
                    print(f"✓ [素材补齐] 备用背景已生成: {bg_path}")
                    os.environ["DEFAULT_BG_IMAGE"] = str(bg_path)
        except Exception as e:
            print(f"[警告] 备用背景生成失败: {e}")
    
    # V27.0：环境变量代码级死锁
    token = _env("TELEGRAM_TOKEN") or _env("TELEGRAM_BOT_TOKEN")
    if not token:
        logging.error("🔴 [致命错误] TELEGRAM_TOKEN 获取为空！")
        print("\n" + "="*60)
        print("🔴 [环境变量死锁] TELEGRAM_TOKEN 缺失")
        print("🔴 [正在尝试] 5秒后从本地备份暴力提取...")
        print("="*60 + "\n")
        
        # 等待5秒后从 EmergencyConfig 重新读取
        time.sleep(5)
        token = EmergencyConfig.get("TELEGRAM_BOT_TOKEN") or EmergencyConfig.get("TELEGRAM_TOKEN")
        
        if not token:
            print("🔴 [暴力提取失败] TELEGRAM_TOKEN 仍为空：进入生存模式（不退出进程）")
            try:
                _start_minimal_health_server()
            except Exception:
                pass
            while True:
                time.sleep(60)
        else:
            print("✓ [暴力提取成功] 已从本地备份装填 TELEGRAM_TOKEN")
    
    # V26.0：环境变量入库验证（静默模式，自动装填）
    if IS_CLOUD_ENV:
        missing_keys = []
        if not token:
            missing_keys.append("TELEGRAM_BOT_TOKEN")
        if not DEEPSEEK_API_KEY:
            missing_keys.append("DEEPSEEK_API_KEY")
        if not ELEVENLABS_API_KEY:
            missing_keys.append("ELEVENLABS_API_KEY")
        if not VOICE_ID:
            missing_keys.append("VOICE_ID")
        
        if missing_keys:
            print("\n" + "="*60)
            print("🔴 [云端环境] 环境变量缺失，已尝试从 .env 自动装填")
            print(f"🔴 [缺失密钥] {', '.join(missing_keys)}")
            print("="*60 + "\n")
            print("⚠️ [生存协议] 不退出进程：请在 Zeabur 环境变量补齐后重启部署")
    
    # V16.9：启动即清场——战区净空协议
    physical_cleanup_output_lib()
    
    if not _PTB_AVAILABLE:
        print("🔴 [依赖缺失] python-telegram-bot 未安装：进入生存模式（不退出进程）")
        try:
            _start_minimal_health_server()
        except Exception:
            pass
        while True:
            time.sleep(60)
    # V15.2：点火前暴力自检（mp4=0 直接熔断停止）
    firecontrol_preflight_or_die()

    # V40.0：物理核平 Webhook + 积压消息（启动前 URL 强扫）
    # - deleteWebhook(drop_pending_updates=true)：扫平历史积压 update
    # - run_polling(drop_pending_updates=true)：彻底丢弃旧指令，避免重启炸膛
    # V44.2：使用 urllib（不触碰 asyncio）替代 httpx.get，
    #        防止 anyio 关闭事件循环后 run_polling 拿到已关闭的 loop 炸膛
    print("\n[链路诊断] 正在物理核平 Webhook + 历史积压...")
    try:
        import urllib.request as _urllib_req
        import urllib.parse as _urllib_parse
        _wh_url = (
            f"https://api.telegram.org/bot{token}/deleteWebhook"
            f"?{_urllib_parse.urlencode({'drop_pending_updates': 'true'})}"
        )
        with _urllib_req.urlopen(_wh_url, timeout=15) as _r:
            if _r.status == 200:
                print("✓ [链路诊断] Webhook + 历史积压已物理扫平")
            else:
                print(f"[链路诊断] Webhook 清除警告: HTTP {_r.status}")
    except Exception as e:
        print(f"[链路诊断] Webhook 清除警告: {e}")

    # V44.2：事件循环物理重置（防止任何同步 IO 提前关闭 loop）
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:
        pass
    
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start_callback))
    application.add_handler(CommandHandler("fire", fire_callback))
    # 普通消息（私聊/群聊）
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, industry_callback))
    # 频道消息（channel_post）兜底
    try:
        application.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST & filters.TEXT & ~filters.COMMAND, industry_callback))
    except Exception:
        pass
    print("[统帅部] 工厂与雷达已物理并轨：bot.py SaaS 监听模式已启动")
    
    # V26.0：云端成功启动通知（自动发送到 Telegram）
    if IS_CLOUD_ENV and TELEGRAM_CHAT_ID:
        try:
            import httpx
            now = datetime.now()
            
            # V32.0：实弹装填战报对时
            material_count = 0
            material_dir = Path("/tmp/Jiumo_Auto_Factory/自媒体")
            if material_dir.exists():
                material_count = len(list(material_dir.glob("*.mp4")))
            
            startup_msg = (
                f"✓ [统帅部] 云端母机已自动完成环境变量装填\n"
                f"✓ 4K 缝合线已全线通电\n"
                f"✓ 启动时间: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"✓ 环境: Zeabur Cloud\n"
                f"✓ [{now.strftime('%H:%M')} 战报] 云端实弹已入库！\n"
                f"✓ {material_count} 枚 4K 生肉已物理占领 /tmp 阵地\n"
                f"✓ 物理 PC 已彻底解耦，母机已进入全自动收割状态！\n"
                f"✓ 统帅请关机，静候核弹回传！"
            )
            httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": startup_msg},
                timeout=10.0
            )
            print(f"✓ [{now.strftime('%H:%M')} 战报] 启动通知已发送到 Telegram")
        except Exception as e:
            print(f"[启动通知] 发送失败: {e}")
    
    # V40.0：绝杀模式——不重放旧指令，直接清空积压后监听
    print("\n[Listening...] 母机已进入监听模式，等待统帅指令\n")
    try:
        application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        print(f"[监听异常] run_polling 异常（将重试，不退出进程）: {e}")
        time.sleep(10)


# === 入口点 ===
if __name__ == "__main__":
    # 主权并轨：默认启动 SaaS 监听；需要手动工厂批量模式时再显式切换
    if (os.getenv("RUN_FACTORY_STANDALONE") or "").strip() == "1":
        # --- 工厂手动运行通道（不含任何 Telegram 监听逻辑） ---
        if (os.getenv("V79_DRY_RUN") or "").strip() == "1":
            os.environ["SINGLE_INDUSTRY"] = "白酒"
            os.environ["V79_REALTIME_VISUAL"] = "1"
            print("\n============================================================")
            print("V7.9 闭环逻辑实弹空测")
            print("============================================================")
            os.environ["OUTPUT_BASE_DIR"] = "output"
            asyncio.run(main())
            print("[统帅部] 空测导弹已命中，成品已存放至 /output 文件夹，请统帅查验战损！")
        else:
            asyncio.run(main())
    else:
        # V39.5：生存第一——监听异常也不退出进程（避免云端 Backoff）
        while True:
            try:
                main_saas()
            except Exception as e:
                try:
                    print(f"[主循环] main_saas 异常（将重试）: {e}")
                except Exception:
                    pass
                time.sleep(10)
