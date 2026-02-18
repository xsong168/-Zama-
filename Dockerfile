# Junshi Bot - Docker 部署配置
# 备选方案：当 Nixpacks 失败时使用 Docker 模式

FROM python:3.11-slim

# 安装系统依赖（FFmpeg）
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY bot.py .
COPY prompts/ ./prompts/

# 创建临时目录（战备仓）
RUN mkdir -p /tmp/Junshi_Staging /tmp/output /tmp/Final_Out /tmp/Jiumo_Auto_Factory

# 设置环境变量（标识云端环境）
ENV ZEABUR=1
ENV PYTHONUNBUFFERED=1

# 暴露端口（可选，用于健康检查）
EXPOSE 8080

# 启动命令
CMD ["python", "-u", "bot.py"]
