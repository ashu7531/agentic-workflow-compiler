"""Vercel Python serverless entrypoint.

Vercel serves the exported ASGI `app`. We add the backend root to sys.path so the
`app` package (app.main) imports correctly inside the serverless bundle.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402  (must come after sys.path tweak)
