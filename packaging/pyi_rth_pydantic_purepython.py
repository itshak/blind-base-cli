"""PyInstaller runtime hook to ensure pydantic falls back to the pure-python implementation.

This runs *before* any project code, setting the environment variable that
instructs `pydantic` ≥2.6 to skip importing the compiled `pydantic_core` wheel.
It prevents the common "ModuleNotFoundError: pydantic_core" error when the
binary wheel for the running architecture is missing (e.g. in a one-file
PyInstaller bundle).
"""
import os, sys, types

# If the user already set an explicit override keep it, otherwise default to the
# safe pure-python path.
os.environ.setdefault("PYDANTIC_PUREPYTHON", "1")

# Provide a minimal stub so that `import pydantic_core` succeeds when the
# compiled extension wheel is absent (e.g. different architecture) and
# `PYDANTIC_PUREPYTHON` is set.  This prevents the import error raised from
# inside pydantic/version.py when it tries to read pydantic_core.__version__.
if 'pydantic_core' not in sys.modules:
    stub = types.ModuleType('pydantic_core')
    stub.__dict__['__version__'] = '0.0.0'
    sys.modules['pydantic_core'] = stub
