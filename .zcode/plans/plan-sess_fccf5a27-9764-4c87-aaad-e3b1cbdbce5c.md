# MDCx 桌面应用 → Web 项目改造方案

## 目标与总体架构

把 PyQt6 桌面应用改造成 **FastAPI 后端 + Vue 3 前端** 的 web 项目，全功能对齐桌面版 7 个页面，最终移除 Qt 层。

- **后端**：FastAPI + WebSocket（项目已是 asyncio + Pydantic v2 + uvicorn 架构，自然衔接）
- **前端**：Vue 3 + TypeScript + Vite + Element Plus + Pinia，构建产物由 FastAPI 静态托管（单进程部署，类 qBittorrent WebUI）
- **运行模型**：单用户（与现有架构一致）：一份 config.json、同时一个刮削任务，多浏览器标签可同时观看同一状态
- **关键事实（已探明）**：约 5.5 万行核心代码（crawlers/core/base/config/tools）本就无 GUI 依赖、在后台 asyncio 线程运行；UI 回传唯一通道是 `signals.py`（15 个信号，带 `set_signal()` 换实现机制）；非 GUI 层仅 3 处 import PyQt6；已有无 GUI CLI（`crawl`）和 105 个无 GUI 测试作行为基线

## Phase 0：基线与核心解耦（去 PyQt6）

1. **git 基线**：提交当前全部代码作为改造前基线（仓库尚无任何 commit）
2. **`mdcx/signals.py` 改造**：新增无头 `WebSignalBus`（实现与 `Signals` 鸭子类型兼容：15 个信号的 `.emit()`、`add_log/get_log`、`stop` 标志、`log_lock`），内部用环形日志缓冲 + asyncio 广播；`signal` 全局改为转发代理，桌面默认仍走 Qt 实现、web 入口启动时切换为 WebSignalBus，桌面行为零变化
3. **`mdcx/core/scraper.py` 去 Qt**：`get_remain_list()`（两个 QMessageBox）拆成无副作用的 `get_resume_info()`（返回剩余列表/是否在扫描目录内等），弹窗决策上移到调用方——桌面 controller 恢复原对话框逻辑，web 由前端弹窗后带 `resume` 参数调 API；这是核心层唯一的阻塞式 GUI
4. **`mdcx/config/resources.py`**：`get_fonts()` 的 QFontDatabase 导入加守卫/移到桌面侧
5. **pyproject 增加依赖**：fastapi
6. **验证**：`import mdcx.core.scraper` 全链路在无 PyQt6 环境可导入；现有 pytest 无 GUI 子集全绿

## Phase 1：后端 API 骨架

新建 `mdcx/webapp/` 包：

- **app 工厂**：FastAPI 应用、启动时切换 WebSignalBus、静态托管前端构建产物（SPA fallback）、console script 入口 `mdcx-web`（uvicorn 启动，端口/主机可用参数覆盖）
- **WS Hub**：单一 `/ws` 端点，把 15 个信号映射为类型化 JSON 事件流（log 主日志/详情/失败、progress 百分比+ETA+计数、result 成功/失败+ShowData、status 任务状态、net_info 等），支持多客户端广播、断线重连后补发缓冲日志
- **ScrapeJobManager**：封装 start（Default/Again/Single 模式）/stop（复刻现有停止流程：置 stop 标志 → save_success_list → cancel_async，不用 `_kill_threads` SystemExit hack）/状态查询/结果查询（成功树、失败列表）
- **路由**：`/api/scrape`（start/stop/status/results/resume-info）、`/api/config`（GET 全量/PUT 保存/reset/多配置文件切换，直接复用 ConfigManager 原子写与迁移层）、`/api/media`（poster/thumb 图片、视频 range 流式播放）、`/api/network`（网络检测/重测/报告，包装 `core/network_check.py`）、`/api/system`（版本/检查更新）
- **测试**：httpx AsyncClient + WebSocket 测试覆盖 scrape 生命周期、config 读写、WS 事件推送

## Phase 2：前端骨架 + 核心页面

新建 `frontend/`（Vite + Vue3 + TS + Element Plus + Pinia + vue-router，dev 模式代理到后端）：

- **布局**：复刻桌面版——左侧导航 7 项 + 底部全局进度条
- **主界面页**：媒体目录展示、结果树（成功/失败两分支）、选中项详情面板（番号/标题/演员/标签/评分/简介 + 海报缩略图预览、点击看大图）、开始/停止按钮、右键菜单（按番号/网址重刮、打开目录、编辑 NFO、删除文件/文件夹带双确认）
- **日志页**：主日志/摘要/失败详情三窗（WS 实时推送 + 虚拟滚动，日志内联 HTML 做清洗渲染）、查看成功/失败列表、失败重刮、保存失败列表
- **设置页**：12 个 tab 全量控件（约 200 项），值统一走 config store（一次 GET/PUT），站点优先级拖拽编辑器、字段优先级矩阵（16 字段 × 站点）做成自定义组件；"保存设置"显式提交（与桌面语义一致）
- **网络检测页**、**关于页**（版本 + 检查更新）
- 工具/演员管理/NFO 三页先放占位入口（Phase 3 填充）

## Phase 3：全功能对齐（剩余页面）

- **工具页 8 组**：单文件刮削、软/硬链接创建、视频+字幕移动、批量字幕、批量 extras 加删、封面补图、Gfriends 头像同步、刮削缓存统计/导出/重置/清空、演员库 12 项维护、缺失番号查找 → `/api/tools/*`；长任务复用 job 进度推送
- **NFO 信息管理页**：目录浏览/文件列表/15 字段编辑表单/海报预览/批量操作（换演员、加删标签、统一系列名）/重刮/删除，复用 `core/nfo.py` 读写与合并策略
- **Emby 演员管理**：包装无头的 `tools/emby_actor_manager.py`（连接配置、列表、详情编辑、数据源测试）→ `/api/emby/*`
- **海报裁剪**：前端 canvas 框选比例 + 后端 Pillow 裁剪落盘

## Phase 4：部署与打磨

- Dockerfile + docker-compose（挂载媒体目录/config/userdata，`consts.py` 已有 IS_DOCKER 探测）
- 可选访问 token（保护删除/移动类接口，默认本机免认证）
- README/docs 更新；CI 增加前端 build + API 测试

## Phase 5：移除桌面版（web 全对齐后）

- 删除 `views/`、`controllers/`、`main.py` Qt 启动、PyQt6 依赖、10 个 GUI 测试、`signals.py` Qt 实现
- 构建脚本改为 web 打包；文档同步

## 风险与说明

- 全功能对齐工作量大，按阶段交付，每个 Phase 结束都是可运行、可验证的状态；先落地 Phase 0-2
- `Flags`/`manager` 全局单例维持单任务模型；若以后要并行多任务，再引入任务队列（不在本期）
- 日志含 `<font color>` 等内联 HTML：前端统一清洗后渲染
- 前端构建需要本机 Node（≥20）；后端用 uv 管理（项目已有 uv.lock）
