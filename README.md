# Junshi Bot 冷酷军师 🤖

**V26.0 暴力接管版** - 全自动无人值守模式

一款基于 DeepSeek + ElevenLabs + FFmpeg 的全自动行业拆解视频生产机器人。

---

## ⚡ 快速开始

### 云端部署（推荐）

1. **Fork 本仓库到你的 GitHub**
2. **登录 [Zeabur](https://zeabur.com)** 并导入仓库
3. **配置环境变量**（复制 `.env.example` 中的内容）：
   ```
   ZEABUR=1
   TELEGRAM_BOT_TOKEN=你的Bot Token
   TELEGRAM_CHAT_ID=你的Chat ID
   DEEPSEEK_API_KEY=sk-xxxxx
   ELEVENLABS_API_KEY=sk_xxxxx
   VOICE_ID=你的Voice ID
   ```
4. **点击 Deploy** - 等待 2-5 分钟即可上线

完整部署指南：[DEPLOYMENT.md](./DEPLOYMENT.md)

---

## 🎯 核心功能

### 一键生成行业拆解视频
在 Telegram 群组发送行业名称（如 `自媒体`），自动生成：
1. ✅ 80字爆款文案（DeepSeek Prompt 工程）
2. ✅ AI 语音播报（ElevenLabs 高质量 TTS）
3. ✅ 动态视频缝合（FFmpeg 4K 素材拼接）
4. ✅ 水印 + 字幕（自动化后期）

**支持行业：** 自媒体、白酒、创业、汽修、教培、美容、餐饮等

---

## 📦 本地开发

### 环境要求
- Python 3.11+
- FFmpeg（视频处理）
- 网络连接（API 调用）

### 安装步骤
```bash
# 1. 克隆仓库
git clone https://github.com/你的用户名/Junshi_Bot冷酷军师.git
cd Junshi_Bot冷酷军师

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API 密钥

# 4. 启动机器人
python bot.py
```

---

## 🔧 技术架构

### 核心技术栈
- **AI 文案生成**: DeepSeek API（80字爆款公式）
- **语音合成**: ElevenLabs TTS（中文高质量音色）
- **视频缝合**: FFmpeg（4K 动态素材拼接）
- **消息推送**: python-telegram-bot（实时通知）

### V26.0 暴力接管特性
- ✅ **Emergency Config**（紧急配置类，自动从 .env 装填）
- ✅ **暴力路径自愈**（启动第1秒创建并授权 /tmp 目录）
- ✅ **静默启动通知**（成功启动自动发送到 Telegram）
- ✅ **Keepalive 守护**（进程被杀自动拉起）
- ✅ 云端权限锁死（自动授权 `/tmp` 完整主权）
- ✅ 环境变量入库验证（缺失密钥立即报错）
- ✅ 自动垃圾回收（临时文件物理粉碎）
- ✅ 路径无感化（支持任意 Linux 环境）
- ✅ 双环境自动切换（本地/云端）
- ✅ FFmpeg 无头模式（`-y -nostdin`）

---

## 📂 项目结构

```
Junshi_Bot冷酷军师/
├── bot.py                 # 主程序（4200+ 行核心逻辑）
├── requirements.txt       # Python 依赖清单
├── nixpacks.toml          # Zeabur 部署配置
├── Dockerfile             # Docker 备选方案
├── .env.example           # 环境变量模板
├── .gitignore             # Git 忽略规则
├── .dockerignore          # Docker 构建排除规则
├── DEPLOYMENT.md          # 完整部署指南
├── CLAUDE.md              # AI 编码规范
└── prompts/               # Prompt 模板库
    └── system_prompt.txt  # DeepSeek 系统提示词
```

---

## 🎨 爆款公式（5步结构）

```python
1. 3秒痛点场景（具体画面，非抽象概念）
2. 情绪钩子词（真相/陷阱/后悔 至少一个）
3. 用 ①②③ 结构给出三条预判
4. 视觉卡点短句（可直接上屏幕的大字）
5. 行动号召（立即执行的一句话）
```

**示例输出：**
> 自媒体行业的三大拆解：①补光灯下的肉身苦役 ②低密度口播的视觉毒药 ③零曝光的废弃面部产权。核心真相：数字面孔是特权通行证。

---

## 🛡️ 安全注意

### ⚠️ 敏感信息保护
- `.env` 文件已加入 `.gitignore`（严禁上传 GitHub）
- 所有 API 密钥通过 `os.getenv()` 读取
- Zeabur 环境变量加密存储

### 📋 API 密钥申请
- **DeepSeek**: [platform.deepseek.com](https://platform.deepseek.com)
- **ElevenLabs**: [elevenlabs.io](https://elevenlabs.io)
- **Telegram Bot**: 找 [@BotFather](https://t.me/BotFather)

---

## 📊 监控与日志

### Zeabur 日志查看
```bash
# 在 Zeabur 控制台实时查看
# 或使用 CLI
zeabur logs -f
```

### 本地调试输出
```
[雷达扫描] 目标分仓：/tmp/Jiumo_Auto_Factory
[文案] DeepSeek 生成成功: 80 字符
[音频] ElevenLabs 合成成功: task_1234.mp3
[视频] FFmpeg 缝合成功: task_1234.mp4
[投递] Telegram 发送成功（4 条消息）
```

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 代码规范
- 遵循 [CLAUDE.md](./CLAUDE.md) 编码规范
- 所有修改必须通过 Linter 检查（0 Errors）
- 提交前运行 `python -m py_compile bot.py` 自检

---

## 📄 开源协议

MIT License - 自由使用，但请保留作者署名。

---

## 📞 技术支持

- **部署问题**: 查看 [DEPLOYMENT.md](./DEPLOYMENT.md)
- **代码问题**: 提交 GitHub Issue
- **商业合作**: Telegram 群组联系

---

**[统帅部] V26.0 暴力接管版 - 环境变量已在代码层焊死，云端已进入无人值守模式！** 🚀
