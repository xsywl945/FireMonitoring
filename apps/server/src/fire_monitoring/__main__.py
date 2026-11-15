from pathlib import Path

import uvicorn

from .config import load_config
from .main import create_app


def main() -> None:
    path = Path("config.json")
    config = load_config(path)
    uvicorn.run(
        create_app(config, config_path=path),
        host=config.server.host,
        port=config.server.port,
    )


if __name__ == "__main__":
    main()
