# Junshi Bot - Claude 最高宪法

**制定时间**: 2026-02-15  
**执行级别**: 强制遵守（MANDATORY）

---

## V3 架构强制规则

### 0 红字铁律（最高优先级）
- **每次代码修改必须清理所有红色波浪线，实现 0 Linter Errors 运行**
- 修改后必须立即执行 Linter 扫描并清理全部残留
- 所有变量必须在函数入口（try 之前）完成物理初始化
- 严禁将 try 块内局部变量提取到块外引用
- `generate_blood_bullet` 的核心变量（content, clean_text, el_resp, audio_path, video_path, video_ok, is_black, err）必须在函数最顶层声明
- 如果修改后仍有红字，自动重写整个函数直到清零

### 音频引擎主权
- ElevenLabs 音频引擎物理唯一标识：`eleven_v3`
- voice_settings 仅保留：`{"stability": 0.20, "similarity_boost": 1.0}`
- 禁止使用 `eleven_multilingual_v2`、`eleven_turbo_v2_5` 等过时引擎

### 物理隔离标准
- 每个行业目录必须包含 `/音频库` 和 `/视频库` 双层分类
- 文件名格式（纯中文）：`【行业宣判】_{行业}_{时间戳}.mp3` / `.mp4`

### 自动净空协议
- 生产结束自动清理所有 `.tmp` 临时文件
- 归档区必须保持绝对整洁

---

## 核心规则

### 1. 双重闭环铁律
**所有成片必须实现：本地归档 + Telegram 通知的双重闭环**

- 本地归档: 所有音频/视频存储在 `01-内容生产/成品炸弹/YYYY-MM-DD/{行业}/`
- 云端通知: 通过 Telegram Bot 实时推送战报（文件名、文案、物理路径）
- 禁止仅本地存储而不通知
- 禁止仅通知而不本地归档

### 2. 文件命名规范
**V3 架构使用纯中文文件名**

```python
# V3 标准格式
name = f"【行业宣判】_{industry}_{timestamp}"
audio = f"{name}.mp3"
video = f"{name}.mp4"
```

### 3. 异步架构标准
**所有 API 请求必须使用 httpx 异步框架**

```python
async with httpx.AsyncClient(timeout=60.0) as client:
    response = await client.post(url, json=payload)
```

### 4. 懒加载原则
**仅在启动时加载核心身份，禁止读取整个记忆库**

```python
def lazy_load_identity():
    # 仅读取 本体画像/00-核心身份.md
    with open("本体画像/00-核心身份.md", 'r', encoding='utf-8') as f:
        return f.read()
```

### 5. 物理断句武器
**所有文案必须强制执行物理停顿注入**

```python
clean_text = content.replace("。", "... ... ").replace("！", "... ... ")
```

### 6. 编码完全避雷
**所有 subprocess 调用必须处理编码问题**

```python
result = subprocess.run(
    cmd,
    capture_output=True,
    encoding='utf-8',
    errors='ignore'
)
```

### 7. 自愈基因规则
**每次成功生产必须自动 Git 提交**

```python
if success > 0:
    auto_commit()
```

### 8. Telegram 投递规范
**每条战报必须包含以下信息**

- 身份标识: `[中国酒魔·冷酷军师]`
- 行业战区标签
- 物理路径标签
- 文案宣判词
- 生成时间戳

### 9. 爆款 5 步公式（Prompt 铁律）
**DeepSeek 文案必须严格执行：**

1. 3秒痛点场景（具体画面，非抽象概念）
2. 情绪钩子词（真相/陷阱/后悔 至少一个）
3. 用 ①②③ 结构给出三条预判
4. 视觉卡点短句（可直接上屏幕的大字）
5. 行动号召（立即执行的一句话）

---

## 环境变量清单

必须在 `.env` 中配置以下变量：

```env
# AI 服务
DEEPSEEK_API_KEY=sk-xxxxx
ELEVENLABS_API_KEY=sk_xxxxx
VOICE_ID=xxxxx

# 素材配置
DEFAULT_BG_IMAGE=./assets/default_bg.jpg

# Telegram 通知
TELEGRAM_BOT_TOKEN=xxxxxxxxxx:xxxxx
TELEGRAM_CHAT_ID=-xxxxxxxxxx
```

---

## 目录结构规范

```
Junshi_Bot/
├── 本体画像/
│   └── 00-核心身份.md
├── 记忆库/
│   ├── 情景记忆/
│   ├── 语义记忆/
│   └── 强制规则/
├── 01-内容生产/
│   └── 成品炸弹/
│       └── YYYY-MM-DD/
│           ├── 餐饮/
│           │   ├── 音频库/
│           │   │   └── 【行业宣判】_餐饮_timestamp.mp3
│           │   └── 视频库/
│           │       └── 【行业宣判】_餐饮_timestamp.mp4
│           ├── 汽修/
│           ├── 教培/
│           ├── 美容/
│           └── 装饰/
├── assets/
│   └── default_bg.jpg
├── .env
├── .gitignore
├── bot.py
├── sniffer.py
└── CLAUDE.md
```

---

## 迭代流程

### 八步迭代法则
1. **观察** (Observe): 发现问题
2. **分析** (Analyze): 诊断根本原因
3. **设计** (Design): 制定解决方案
4. **实施** (Implement): 执行修复
5. **验证** (Verify): 测试结果
6. **记录** (Record): 写入情景记忆
7. **提炼** (Refine): 更新语义记忆
8. **提交** (Commit): Git 自动提交

---

## 禁止行为

- 使用过时的 V2 引擎（eleven_multilingual_v2）
- 使用同步请求（requests）
- 读取整个记忆库
- 跳过 Telegram 通知
- 跳过 Git 提交
- 不处理 subprocess 编码错误
- 在 try 块内声明变量后在块外引用
- 修改后不执行 Linter 检查

---

**记住：0 红字 > 一切功能**

**双重闭环 = 本地归档 + Telegram 通知**
