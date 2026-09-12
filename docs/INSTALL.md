# 安装指南

## 系统要求

- **Docker**（推荐）：任何能跑 Docker 的机器（NAS / 服务器 / 桌面）
- **源码运行**：Python 3.12+、Node.js 20+（仅构建前端时需要）
- **网络**：需要能访问数据源网站

## 方法一：Docker（推荐）

```bash
# 先构建前端（一次性，或直接使用仓库已构建的 frontend/dist）
cd frontend && npm install && npm run build && cd ..

# 构建镜像（基于 python:3.12.10-bullseye）
docker build -t mdcx-web .

# 运行：config 目录持久化，媒体目录只读挂载
docker run -d --name mdcx-web \
  -p 9801:9801 \
  -v /path/to/config:/app/data \
  -v /path/to/media:/media:ro \
  mdcx-web
```

浏览器打开 `http://<主机IP>:9801`。第一次使用先到「软件设置 → 刮削目录」：
把媒体路径设置为容器内的挂载路径（如 `/media`），保存后即可开始刮削。

可选环境变量：

| 变量 | 说明 |
|------|------|
| `MDCX_WEB_PORT` | 监听端口（默认 9801），如 `-e MDCX_WEB_PORT=8080 -p 8080:8080` |
| `MDCX_WEB_HOST` | 监听地址（镜像内默认 0.0.0.0） |
| `MDCX_WEB_TOKEN` | 设置后所有 API/WS 需带令牌（`Authorization: Bearer <token>` 或 `?token=`），公网暴露时建议开启 |
| `MDCX_WEB_DIST` | 前端静态目录覆盖（默认镜像内已内置） |

## 方法二：从源码运行

```bash
# 1. 装 Python 3.12+
# 去 https://www.python.org/downloads/ 下载安装
# Windows 安装时记得勾 "Add Python to PATH"

# 2. 下载代码
git clone <本仓库>
cd mdcx-web

# 3. 安装依赖
pip install -e .

# 4. 启动（默认 http://127.0.0.1:9801）
mdcx-web

# 局域网访问：
mdcx-web --host 0.0.0.0 --port 9801
```

前端热更新开发（可选）：

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173，API/WS 自动代理到 9801
```

## 常见问题

- **打不开页面**：确认服务进程在跑（`mdcx-web`），端口没被占用；Docker 部署确认端口映射。
- **刮削的文件去哪了**：成功/失败输出目录在「软件设置 → 刮削目录」配置，Docker 部署时请把输出目录也挂载进容器。
- **配置文件在哪**：`MDCx.config` 标记文件指向当前启用的 config.json；Docker 部署时在 `/app/data` 挂载卷内持久化。
