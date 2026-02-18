# 强制规则：文件名命名铁律

**最后更新**: 2025-02-15  
**规则级别**: 强制执行（MANDATORY）

---

## 核心铁律

### ✅ 强制格式
**所有自动生成的文件名必须使用：英文前缀 + 序号 + 时间戳**

```python
filename = f"blood_bullet_{index}_{int(time.time())}.mp3"
```

### ❌ 绝对禁止
- 中文字符（汉字、标点符号）
- 特殊符号（除 `_` 和 `-` 外）
- 空格
- Emoji

---

## 标准格式模板

### 1. 音频文件
```python
# 血弹音频
f"blood_bullet_{index}_{timestamp}.mp3"

# 示例
"blood_bullet_1_1739604123.mp3"
"blood_bullet_2_1739604145.mp3"
```

### 2. 文案文件
```python
# 文案脚本
f"script_{industry_code}_{timestamp}.txt"

# 示例
"script_automotive_1739604123.txt"
```

### 3. 日志文件
```python
# 情景记忆
f"YYYYMMDD-{event_type}-{description}.md"

# 示例
"20250215-fix-filename-encoding.md"
```

---

## 避雷原因

### Windows 编码陷阱
- PowerShell 默认 GBK 编码
- 中文文件名在 `open()` 时可能触发 `UnicodeEncodeError`
- `print()` 输出中文也会导致终端编码冲突

### 跨平台兼容性
- Linux/macOS 使用 UTF-8
- Windows 使用 GBK/CP936
- 文件名中文会导致哈希值不一致

### 自动化友好
- CI/CD 管道通常不支持中文路径
- Git 操作在某些环境下会报错
- 日志解析工具无法识别

---

## 执行检查清单

提交代码前必须验证：
- [ ] 文件名是否包含中文？
- [ ] 是否使用了 `{index}` 和 `{timestamp}`？
- [ ] 是否使用了纯 ASCII 字符（a-z, 0-9, _, -）？
- [ ] print 输出是否避免了 Emoji？

---

## 违规处理

**一旦发现中文文件名**：
1. 立即停止生产流程
2. 重命名为英文格式
3. 记录到情景记忆
4. 更新代码模板

---

## 正确示例 ✅

```python
# 生成文件名
filename = f"blood_bullet_{index}_{int(time.time())}.mp3"

# 写入文件
with open(filename, "wb") as f:
    f.write(audio_data)

# 输出日志（纯 ASCII）
print(f"[OK] {filename} generated")
```

## 错误示例 ❌

```python
# ❌ 包含中文
filename = f"汽修行业_血弹_第{index}发.mp3"

# ❌ 包含空格
filename = f"blood bullet {index}.mp3"

# ❌ 输出 Emoji
print(f"🚀 {filename} 锻造成功！")
```

---

**记住：物理避雷 > 事后修复**

**英文 + 时间戳 = 永不出错**
