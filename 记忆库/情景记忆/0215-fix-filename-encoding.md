# 情景记忆：0215-修复文件名编码报错

**时间**: 2025-02-15  
**问题**: 文件名包含中文导致 UnicodeEncodeError  
**严重程度**: 高（阻断生产流程）

## 问题现象
```python
# 原错误代码示例
filename = f"{industry}_血弹_第{index}发_{int(time.time())}.mp3"
# 触发报错：UnicodeEncodeError: 'gbk' codec can't encode character
```

## 根本原因
1. Windows 系统默认使用 GBK 编码
2. Python 文件名包含中文字符时，在某些环境下触发编码错误
3. print() 输出中文 Emoji（🚀、🎯）也会导致终端编码冲突

## 解决方案

### 修复1：文件名主权锁定
```python
# 强制使用纯英文格式
filename = f"blood_bullet_{index}_{int(time.time())}.mp3"
```

**关键点**：
- ✅ 使用英文前缀 `blood_bullet_`
- ✅ 序号使用数字 `{index}`
- ✅ 时间戳使用 Unix 时间戳 `{int(time.time())}`
- ❌ 绝对禁止中文字符

### 修复2：print 输出避雷
```python
# 避免使用中文和 Emoji
print(f"[{index}/5] Generating bullet...")  # ✅ 纯 ASCII
print("🚀 军师全自动血弹工厂")  # ❌ 会触发 GBK 编码错误
```

### 修复3：httpx 请求编码确认
```python
# httpx 默认使用 UTF-8，无需额外配置
# 但确保所有 payload 中的中文内容是 JSON 序列化的
ds_resp = await client.post(
    url,
    headers={"Authorization": f"Bearer {key}"},  # ✅ 纯 ASCII
    json={"messages": [...]},  # ✅ JSON 自动处理编码
    timeout=30.0
)
```

## 实施结果
- ✅ 文件名格式已锁定为 `blood_bullet_{index}_{timestamp}.mp3`
- ✅ 所有 print 输出已移除中文和 Emoji
- ✅ httpx 请求编码正常
- ✅ 5发血弹全部成功生成

## 教训提炼
**物理避雷原则**：
1. 文件名必须纯英文+数字+下划线
2. print 输出避免 Emoji 和中文（Windows GBK 环境）
3. 关键路径变量禁用中文

## 后续预防
- 已写入强制规则：`记忆库/强制规则/force-rule-naming.md`
- 代码模板已更新为第二代架构
- Git 提交消息使用英文

## 参考资料
- Python Windows 编码问题：https://docs.python.org/3/library/codecs.html
- 文件命名最佳实践：强制规则文档
