FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（playwright需要）
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    procps \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装playwright浏览器
RUN playwright install chromium
RUN playwright install-deps chromium

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "run.py"]
