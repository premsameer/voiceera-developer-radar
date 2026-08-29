"""Streamlit Community Cloud entrypoint for the presentation snapshot."""
import os
import runpy

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/presentation.sqlite")

runpy.run_path("dashboard.py",run_name="__main__")
