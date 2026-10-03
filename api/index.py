"""
Vercel entry point. Vercel's @vercel/python runtime looks for a WSGI `app`
object in this file. It simply re-exports the real Flask app from bot_app.py
so there is only one copy of the actual logic (no duplicated code to drift
out of sync between local and deployed versions).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot_app import app  # noqa: E402  (re-exported for Vercel)
