"""Vercel Python Serverless Entrypoint for Remi Nusantara 2D."""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
for p in (ROOT_DIR, SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from web_game_server import RemiWebHandler


class handler(RemiWebHandler):
    pass
