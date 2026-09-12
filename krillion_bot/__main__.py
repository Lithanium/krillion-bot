from __future__ import annotations

import logging

from .bot import build
from .config import Config, load_dotenv


def main() -> None:
    load_dotenv()
    config = Config.from_env()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bot = build(config)
    bot.run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
