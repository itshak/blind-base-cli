"""PyInstaller runtime hook to ensure pydantic falls back to the pure-python implementation.

This runs *before* any project code, setting the environment variable that
instructs `pydantic` ≥2.6 to skip importing the compiled `pydantic_core` wheel.
It prevents the common "ModuleNotFoundError: pydantic_core" error when the
binary wheel for the running architecture is missing (e.g. in a one-file
PyInstaller bundle).
"""
import os

# If the user already set an explicit override keep it, otherwise default to the
# safe pure-python path.
os.environ.setdefault("PYDANTIC_PUREPYTHON", "1")
