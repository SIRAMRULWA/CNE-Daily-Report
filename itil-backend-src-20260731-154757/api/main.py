"""
api/main.py
============
Stable Uvicorn entrypoint.

Run with:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

This file only imports the app — all configuration lives in api/app.py.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from api.observability import configure_logging

configure_logging()

from api.app import create_app

app = create_app()
