# Junshi Bot - Zeabur 云端部署指南

## 🚀 V23.0 离线云端总装协议

**部署文件三件套已自动生成：**
- ✅ `nixpacks.toml` - Zeabur 自动部署配置
- ✅ `Dockerfile` - Docker 备选部署方案
- ✅ `requirements.txt` - Python 依赖清单

---

## 📦 快速部署流程

### 1. 本地代码准备（已完成）
```bash
# 所有文件已自动生成并提交到 Git
# 路径已完成"无感化"转换，支持云端 Linux 环境
```

### 2. GitHub 仓库推送
```bash
cd "c:\Users\GIGABYTE\Desktop\Junshi_Bot冷酷军师"
git add .
git commit -m "V23.0 Deploy to Zeabur"
git push origin main
```

### 3. Zeabur 部署步骤

1. **登录 Zeabur**
   - 访问 [zeabur.com](https://zeabur.com)
   - 使用 GitHub 账号登录

2. **创建新项目**
   - 点击 "New Project"
   - 选择 "Import from GitHub"
   - 选择 `Junshi_Bot冷酷军师` 仓库
   - Zeabur 会自动检测 `nixpacks.toml` 配置

3. **配置环境变量**（⚠️ 必填）
   在 Zeabur 项目设置中添加：
   ```
   ZEABUR=1
   TELEGRAM_BOT_TOKEN=你的Bot Token（从 .env 复制）
   TELEGRAM_CHAT_ID=你的Chat ID（从 .env 复制）
   DEEPSEEK_API_KEY=sk-xxxxx（从 .env 复制）
   ELEVENLABS_API_KEY=sk_xxxxx（从 .env 复制）
   VOICE_ID=你的Voice ID（从 .env 复制）
   ```

4. **启动服务**
   - 点击 "Deploy" 按钮
   - 等待部署完成（约 2-5 分钟）
   - 查看日志确认启动成功

---

## 📋 环境变量说明

| 变量名 | 必填 | 说明 | 示例值 |
|--------|------|------|--------|
| `ZEABUR` | ✅ | 云端环境标识 | `1` |
| `TELEGRAM_BOT_TOKEN` | ✅ | Telegram Bot 令牌 | `123456:ABC-DEF...` |
| `TELEGRAM_CHAT_ID` | ✅ | 接收消息的 Chat ID | `-1001234567890` |
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API 密钥 | `sk-xxxxxxxx` |
| `ELEVENLABS_API_KEY` | ✅ | ElevenLabs API 密钥 | `sk_xxxxxxxx` |
| `VOICE_ID` | ✅ | ElevenLabs 音色 ID | `NKRyHOXl...` |
| `OUTPUT_DIR` | ❌ | 输出目录（云端自动 `/tmp/output`） | `./output` |
| `FINAL_OUT_DIR` | ❌ | 成品目录（云端自动 `/tmp/Final_Out`） | `./Final_Out` |

---

## 🔧 V23.5 技术架构特性

### 1. 云端权限锁死（物理目录强制授权）
**启动时自动创建并授权关键目录：**
```python
critical_dirs = [
    "/tmp/assets",
    "/tmp/output", 
    "/tmp/Final_Out",
    "/tmp/Junshi_Staging",
    "/tmp/Jiumo_Auto_Factory"
]
# 权限：0o777（完整 Linux 主权）
```

### 2. 环境变量入库验证
**云端环境必填项检查：**
- ✅ `TELEGRAM_BOT_TOKEN` - 缺失时立即报错
- ✅ `DEEPSEEK_API_KEY` - 缺失时立即报错
- ✅ `ELEVENLABS_API_KEY` - 缺失时立即报错
- ✅ `VOICE_ID` - 缺失时立即报错

**错误提示示例：**
```
🔴 [云端环境检测] 致命错误：缺少必填环境变量
🔴 [缺失密钥] TELEGRAM_BOT_TOKEN, DEEPSEEK_API_KEY
🔴 [解决方案] 请在 Zeabur 控制台配置以上环境变量
```

### 3. 自动垃圾回收
**缝合完成后物理粉碎：**
- 🗑️ `task_xxx.mp3` - 音频临时文件
- 🗑️ `task_xxx.jpg` - 背景临时文件
- 🗑️ `task_xxx.mp4` - 视频临时文件（已发送）
- 🗑️ `task_xxx.txt` - 文案临时文件
- ✅ 仅保留成品回传给统帅（Telegram）

### 4. 物理路径"无感化"转换
**所有硬编码路径已核平：**
- ❌ 旧版：`C:/Users/GIGABYTE/Desktop/Junshi_Bot冷酷军师/output`
- ✅ 新版：`os.getenv("OUTPUT_DIR", "./output")`（云端自动 `/tmp/output`）
- ❌ 旧版：`D:\Google 云端硬盘\Jiumo_Auto_Factory`
- ✅ 新版：云端自动创建 `/tmp/Jiumo_Auto_Factory`

### 5. 双环境自动切换
```python
IS_CLOUD_ENV = os.getenv("ZEABUR") == "1" or not os.path.exists("D:/")
```
- **云端模式**：跳过 D 盘扫描，使用 `/tmp` 临时目录
- **本地模式**：保留原有 Windows 路径逻辑

### 6. 战备仓路径自适应
- Windows: `C:/Junshi_Staging`
- Linux/云端: `/tmp/Junshi_Staging`

### 7. FFmpeg 无头模式
- 所有命令添加 `-y -nostdin` 参数
- 避免云端部署时卡死在交互式提示

### 8. 成品自动清理
- **云端模式**：发送到 Telegram 后立即删除 MP4（节省存储）
- **本地模式**：归档到 `Final_Out/` 目录

### 9. 离线监听补丁
```python
application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
```
- `drop_pending_updates=True`：母机关机期间的旧指令自动清空
- 防止云端重启时"炸膛"

---

## 🛡️ 安全注意事项

### ⚠️ 严禁上传的文件（已在 `.gitignore` 中）
- `.env` - 包含所有明文密钥
- `本体画像/` - 本地记忆库
- `记忆库/` - 历史数据
- `Final_Out/` - 成品视频
- `output/` - 临时输出文件
- `*.mp4` / `*.mp3` - 音视频成品

### ✅ 必须上传的文件
- `bot.py` - 主程序（已完成路径无感化）
- `requirements.txt` - Python 依赖清单
- `nixpacks.toml` - Zeabur 配置
- `Dockerfile` - Docker 备选方案
- `.env.example` - 环境变量模板
- `.gitignore` - Git 忽略规则
- `.dockerignore` - Docker 构建排除规则

---

## 📊 监控与调试

### 查看日志
```bash
# 在 Zeabur 控制台查看实时日志
# 或使用 Zeabur CLI
zeabur logs -f
```

### 常见问题排查

1. **FFmpeg 未找到**
   - 确认 `nixpacks.toml` 文件已提交
   - 检查部署日志中是否有 `apt-get install ffmpeg` 成功信息
   - 重新部署服务

2. **Telegram 发送失败**
   - 检查 `TELEGRAM_BOT_TOKEN` 是否正确（从 `.env` 复制）
   - 确认 Bot 已加入目标群组
   - 验证 `TELEGRAM_CHAT_ID` 格式（群组 ID 需加 `-` 前缀）

3. **DeepSeek API 报错**
   - 检查密钥是否有效（`sk-` 开头）
   - 确认账户余额充足
   - 查看 Zeabur 日志中的具体错误信息

4. **ElevenLabs 额度耗尽**
   - 系统会自动降级到 Edge TTS
   - 不影响正常生产，仅音质略降

5. **路径错误 (Path not found)**
   - V23.0 已完成路径无感化，不应出现此错误
   - 如仍报错，检查环境变量 `ZEABUR=1` 是否设置

---

## 🎯 验收测试

部署成功后，在 Telegram 群组发送以下命令：

```
自媒体
```

**预期结果（4 条消息）：**
1. ✅ 文案文本消息（论坛排版）
2. ✅ 音频文件（MP3）
3. ✅ 背景图片（JPG）
4. ✅ 成品视频（MP4，云端发送后自动删除）

---

## 🔄 Docker 部署（备选方案）

如果 Nixpacks 失败，可切换到 Docker 模式：

### 1. 本地测试
```bash
# 构建镜像
docker build -t junshi-bot .

# 运行容器（需先配置 .env）
docker run --env-file .env junshi-bot
```

### 2. Zeabur Docker 部署
- 在 Zeabur 项目设置中选择 "Dockerfile"
- Zeabur 会自动检测并使用 `Dockerfile` 构建
- 环境变量配置方式相同

---

## 📞 技术支持

如遇到部署问题，请检查：
1. ✅ Zeabur 部署日志（查看 FFmpeg 安装是否成功）
2. ✅ 环境变量配置（所有必填项是否正确）
3. ✅ GitHub 仓库文件完整性（三件套是否上传）
4. ✅ API 密钥有效性（DeepSeek / ElevenLabs）
5. ✅ Telegram Bot 权限（是否加入目标群组）

---

## 🎖️ V23.5 核心优势

1. **云端权限锁死**：启动时自动授权 `/tmp` 目录（0o777 完整主权）
2. **环境变量入库验证**：缺失必填项立即报错（严禁带病运行）
3. **自动垃圾回收**：缝合完成后物理粉碎临时文件（节省存储 3x）
4. **路径无感化**：支持任意云端 Linux 环境，无硬编码
5. **双环境切换**：同一套代码本地/云端自动适配
6. **离线监听**：`drop_pending_updates=True` 防止旧指令堆积
7. **无头 FFmpeg**：`-y -nostdin` 防止云端卡死
8. **三件套部署**：Nixpacks + Docker + requirements.txt 全覆盖

---

**[统帅部] V23.5 权限补丁已焊死。云端母机已获得完整 Linux 主权，请统帅静候成品视频降临！** 🚀

