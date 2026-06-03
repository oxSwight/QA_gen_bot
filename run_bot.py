"""Launch QA Gen Bot. Loads .env from project root."""
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")

import asyncio

from qa_gen_bot.main import main

if __name__ == "__main__":
    asyncio.run(main())
