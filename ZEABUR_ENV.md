# Zeabur 云端部署 - 环境变量配置清单

**版本**: V32.0  
**更新时间**: 2026-02-18 09:35

---

## 必填环境变量

### 1. Telegram 通知系统
```bash
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=-1001234567890
```

**获取方法**:
- `TELEGRAM_BOT_TOKEN`: 通过 [@BotFather](https://t.me/BotFather) 创建 Bot 获取
- `TELEGRAM_CHAT_ID`: 
  1. 将 Bot 添加到目标频道/群组
  2. 发送任意消息
  3. 访问 `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
  4. 在返回的 JSON 中找到 `chat.id` 字段

---

### 2. DeepSeek 文案生成引擎
```bash
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**获取方法**:
- 登录 [DeepSeek 开放平台](https://platform.deepseek.com/)
- 进入 API Keys 页面生成新密钥

---

### 3. ElevenLabs 音频合成引擎
```bash
ELEVENLABS_API_KEY=sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
VOICE_ID=21m00Tcm4TlvDq8ikWAM
```

**获取方法**:
- 登录 [ElevenLabs](https://elevenlabs.io/)
- API Key: Profile → API Keys → Create
- Voice ID: Voice Library → 选择语音 → Copy Voice ID

---

### 4. Google Drive 实弹装填（V32.0 新增）
```bash
GOOGLE_DRIVE_REFRESH_TOKEN=1//0xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GOOGLE_DRIVE_CLIENT_ID=123456789012-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.apps.googleusercontent.com
GOOGLE_DRIVE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxxxxxxxxxx
GOOGLE_DRIVE_FOLDER_ID=1-68xxxxxxxxxxxxxxxxxxxxxxxxxx
```

**获取方法**:

#### 4.1 创建 Google Cloud 项目
1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目（或选择现有项目）
3. 启用 **Google Drive API**

#### 4.2 创建 OAuth 2.0 凭证
1. 进入 `APIs & Services > Credentials`
2. 点击 `Create Credentials > OAuth client ID`
3. 应用类型: `Desktop app`
4. 创建后获得 `Client ID` 和 `Client Secret`

#### 4.3 获取 Refresh Token
使用以下 Python 脚本（在本地运行）：

```python
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": "YOUR_CLIENT_ID",
            "client_secret": "YOUR_CLIENT_SECRET",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]
        }
    },
    SCOPES
)

creds = flow.run_local_server(port=0)
print(f"Refresh Token: {creds.refresh_token}")
```

#### 4.4 获取文件夹 ID
1. 在 Google Drive 中打开目标文件夹
2. 从 URL 中提取 ID（格式: `https://drive.google.com/drive/folders/1-68xxxxx`）
3. 复制 `1-68xxxxx` 部分

---

### 5. 云端环境标识
```bash
ZEABUR=1
```

**说明**: 此变量用于触发云端模式，自动切换到 `/tmp` 路径和 FFmpeg `ultrafast` 预设。

---

## 可选环境变量

### 背景图路径（本地模式）
```bash
DEFAULT_BG_IMAGE=/tmp/assets/bg/default_bg.jpg
```

**说明**: 云端模式下自动生成，无需手动配置。

---

## Zeabur 配置步骤

### 1. 进入项目设置
登录 [Zeabur](https://zeabur.com/) → 选择项目 → `Settings` → `Environment Variables`

### 2. 批量添加变量
点击 `Add Variable`，逐一添加上述环境变量。

### 3. 重新部署
点击 `Redeploy` 按钮触发重新部署。

### 4. 验证部署
查看 `Logs` 页面，等待以下关键字出现：

```
✓ [火控自检] 正在尝试连接 Telegram API...
✓ [实弹装填] 发现 5 枚 4K 生肉，开始暴力下载...
✓ [09:40 战报] 云端实弹已入库！
✓ [火控自检] Listening...
```

---

## 安全提示

- ❌ **禁止将 `.env` 文件推送到 GitHub**（已在 `.gitignore` 中排除）
- ✅ 所有密钥仅在 Zeabur 环境变量中配置
- ✅ 定期轮换 API 密钥（建议每 90 天）
- ✅ 限制 Google Drive API 权限（仅需 `drive.readonly`）

---

## 故障排查

### 问题：Telegram 无响应
**排查步骤**:
1. 检查 `TELEGRAM_BOT_TOKEN` 是否正确
2. 确认 Bot 已添加到目标频道/群组
3. 检查 `TELEGRAM_CHAT_ID` 格式（群组/频道需带 `-` 前缀）

### 问题：素材下载失败
**排查步骤**:
1. 检查 `GOOGLE_DRIVE_REFRESH_TOKEN` 是否过期
2. 确认 `GOOGLE_DRIVE_FOLDER_ID` 是否正确
3. 验证文件夹权限（需要读取权限）

### 问题：FFmpeg 报错
**排查步骤**:
1. 检查 `nixpacks.toml` 是否存在（FFmpeg 安装指令）
2. 查看日志中是否有 `apt-get install -y ffmpeg` 输出
3. 确认云端 `/tmp` 目录有写入权限

---

**[统帅部] 配置完成后，点击 Redeploy，静候 Telegram 09:40 战报！**
