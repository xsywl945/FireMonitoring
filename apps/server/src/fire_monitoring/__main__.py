import os
import sys
from pathlib import Path

import uvicorn

from .config import load_config
from .main import create_app
from .web import mount_spa


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "config.json")
    if not path.is_file():
        raise SystemExit(f"缺少配置文件：{path}")
    config = load_config(path)
    app = create_app(config, config_path=path)
    static = os.environ.get("FIRE_WEB_DIST", "")
    if static:
        mount_spa(app, Path(static))
    uvicorn.run(app, host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
