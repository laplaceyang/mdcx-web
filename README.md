# MDCx Web

![python](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?style=flat&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-GPLv3-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Docker%20%7C%20Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![Crawlers](https://img.shields.io/badge/Sites-36-brightgreen.svg)

MDCx Web 是 [MDCx-diy](https://github.com/cdlongbow/mdcx-diy) 的 **Web 版**：把桌面 GUI 替换为浏览器界面（FastAPI + Vue 3），核心刮削引擎与桌面版完全一致——自动从 36 个网站抓取视频文件的元数据（标题、演员、封面、简介等），生成标准 `.nfo` 并整理目录，供 Emby / Jellyfin / Kodi 直接使用。

一句话：把一堆乱七八糟的视频文件，变成媒体服务器能认的整齐资料库——现在在浏览器里完成。

## 功能

- **刮削**：四种模式（正常/整理/更新/读取）、断点续刮、失败重刮、单文件/指定网址刮削，实时进度与日志（WebSocket 推送）
- **结果管理**：成功/失败列表、详情面板（封面预览、元数据）、视频在线播放（Range 流式）、NFO 查看
- **NFO 信息管理**：目录浏览、字段编辑、批量操作（替换演员/加删标签/统一系列名）、重新刮削
- **软件工具**：单文件刮削、网盘软链接、视频/字幕移动、批量字幕、extras 加删、封面补图、Gfriends 同步、刮削缓存管理、演员库维护全套、缺失番号查找、海报裁剪
- **演员管理**：Emby 演员列表/详情/头像更新；演员信息与头像批量写入 Emby/Kodi
- **设置**：全部 160+ 配置项（含站点优先级、字段优先级、6 引擎翻译、水印、命名模板等），多配置文件切换
- **网络检测**：全站连通性 + 实刮探测，诊断报告一键复制
- **核心引擎**（与桌面版一致）：多引擎翻译、人脸裁剪、水印、Amazon 高清封面、演员数据库（TMDB/Wikidata/Gfriends）、Cloudflare 绕过（TRAWL/FlareSolverr）

## 快速开始

### Docker（推荐，NAS/服务器）

```bash
docker build -t mdcx-web .
docker run -d --name mdcx-web \
  -p 9801:9801 \
  -v /path/to/config:/app/data \
  -v /path/to/media:/media \
  mdcx-web
```

打开 `http://<主机IP>:9801`，在「软件设置 → 刮削目录」里把媒体路径填为容器内挂载路径（如 `/media`）。

可选环境变量：
- `MDCX_WEB_PORT`：监听端口（默认 9801），如 `-e MDCX_WEB_PORT=8080 -p 8080:8080`
- `MDCX_WEB_TOKEN`：设置后所有 API/WS 需要携带令牌（`Authorization: Bearer <token>` 或 `?token=`），暴露公网时建议开启
- `MDCX_WEB_DIST`：前端静态目录覆盖（默认镜像内已内置）

### 源码运行

```bash
git clone <本仓库>
cd mdcx-web
pip install -e .
mdcx-web                # 默认 http://127.0.0.1:9801，--host 0.0.0.0 供局域网访问
```

前端开发模式：`frontend/` 下 `npm install && npm run dev`（Vite 代理到 9801），构建用 `npm run build`（产物由后端托管）。

## 文档导航

| 文档 | 内容 |
|------|------|
| [docs/INSTALL.md](docs/INSTALL.md) | 安装细节（源码 / Docker） |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | 每个配置项的语义 |
| [docs/FEATURES.md](docs/FEATURES.md) | 功能与 36 个网站列表（桌面版功能清单，web 版逐步对齐） |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 架构、爬虫开发、测试 |
| [docs/changelog.md](docs/changelog.md) | 版本历史 |

## 上游项目

* [sqzw-x/mdcx](https://github.com/sqzw-x/mdcx) — 项目最早源头，暂停维护
* [Hazard804/mdcx](https://github.com/Hazard804/mdcx) — 基于 sqzw-x/mdcx 继续维护优化
* [ZiPenOk/mdcx](https://github.com/ZiPenOk/mdcx) — 基于 Hazard804/mdcx 优化改进
* [cdlongbow/mdcx-diy](https://github.com/cdlongbow/mdcx-diy) — 本仓库的直接上游（PyQt6 桌面版）

向相关开发者表示敬意！

## 授权许可

GPLv3。使用本项目代表你接受：
* 仅供学习和技术交流
* 使用本软件时请遵守当地法律法规
* 法律及使用后果由使用者自己承担
* 禁止用于商业用途
