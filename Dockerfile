# MDCx Web — FastAPI 后端 + 内置 Vue 前端（单进程）
# 基础镜像：python:3.12.10-bullseye（离线包导入：docker load -i "python(3.12.10-bullseye).tar"）
FROM python:3.12.10-bullseye

WORKDIR /app

# 依赖层：先拷源码与资源安装项目（改动少时命中缓存）
# 网络受限环境可用 --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple 走镜像
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY pyproject.toml README.md ./
COPY mdcx ./mdcx
COPY scripts ./scripts
COPY resources ./resources
RUN pip install --no-cache-dir --retries 10 --timeout 120 --index-url "$PIP_INDEX_URL" -e .

# 前端构建产物（构建镜像前先在 frontend/ 执行 npm run build）
COPY frontend/dist ./frontend/dist

ENV PYTHONUNBUFFERED=1
ENV MDCX_WEB_HOST=0.0.0.0
ENV MDCX_WEB_PORT=9801
EXPOSE 9801

# /app/data 为配置与用户数据持久化目录（建议挂载卷）：
# 首次启动写入 MDCx.config 标记文件，把配置/数据库/缓存指向 /app/data
# 监听地址/端口可用环境变量覆盖：-e MDCX_WEB_HOST=0.0.0.0 -e MDCX_WEB_PORT=8080
CMD ["sh", "-c", "mkdir -p /app/data && [ -f /app/MDCx.config ] || printf /app/data/config.json > /app/MDCx.config; exec python -m mdcx.cmd.web"]
