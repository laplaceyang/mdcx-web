"""web 后端入口：mdcx-web 命令。

默认值可用环境变量覆盖：MDCX_WEB_HOST / MDCX_WEB_PORT；
命令行参数优先于环境变量。
"""

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mdcx-web",
        description="MDCx web 版（FastAPI 后端 + 内置前端页面）",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MDCX_WEB_HOST", "127.0.0.1"),
        help="监听地址（默认 MDCX_WEB_HOST 或 127.0.0.1，局域网访问用 0.0.0.0）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MDCX_WEB_PORT", "9801")),
        help="监听端口（默认 MDCX_WEB_PORT 或 9801）",
    )
    parser.add_argument("--reload", action="store_true", help="开发模式：代码变更自动重启")
    args = parser.parse_args()
    uvicorn.run("mdcx.webapp.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
