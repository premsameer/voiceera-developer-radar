"""Streamlit Community Cloud entrypoint for the presentation snapshot."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/presentation.sqlite")

import dashboard  # noqa: E402,F401
