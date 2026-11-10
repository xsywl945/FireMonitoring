import uvicorn

from .config import load_config
from .main import create_app


def main() -> None:
    config = load_config()
    uvicorn.run(create_app(config), host=config.server.host, port=config.server.port)


if __name__ == "__main__":
    main()
