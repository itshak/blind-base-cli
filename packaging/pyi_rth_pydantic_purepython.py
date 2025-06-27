"""PyInstaller runtime hook – force Pydantic to pure-python mode.

This runs **before** any of your code inside the frozen executable, setting the
`PYDANTIC_PUREPYTHON` env-var so that Pydantic skips loading its compiled Rust
extension (`pydantic_core`).  This makes the frozen executable architecture-independent
at the cost of slightly slower validation -- acceptable for CLI usage.

This runs *before* any project code, setting the environment variable that
instructs `pydantic` version 2.6 or higher to skip importing the compiled `pydantic_core` wheel.
It prevents the common "ModuleNotFoundError: pydantic_core" error when the
binary wheel for the running architecture is missing (e.g. in a one-file
PyInstaller bundle).
"""
import os
import sys
import types

# Set PYDANTIC_PUREPYTHON=1 to force pure-python mode
os.environ.setdefault("PYDANTIC_PUREPYTHON", "1")

# Create a minimal stub for pydantic_core to prevent import errors
stub = types.ModuleType('pydantic_core')
stub.__version__ = '0.0.0'
sys.modules['pydantic_core'] = stub

# Create a very small sub-module to satisfy `from pydantic_core import core_schema`
core_schema_module = types.ModuleType('pydantic_core.core_schema')
sys.modules['pydantic_core.core_schema'] = core_schema_module
# Re-export it as an attribute so `from pydantic_core import core_schema` works
stub.core_schema = core_schema_module

# Provide empty compiled-extension submodule so that relative imports like
# `from pydantic_core import _pydantic_core` or `import pydantic_core._pydantic_core`
# succeed even in pure-python mode.
core_so_stub = types.ModuleType('pydantic_core._pydantic_core')
sys.modules['pydantic_core._pydantic_core'] = core_so_stub
stub._pydantic_core = core_so_stub

# Mark as namespace package for completeness
stub.__path__ = []  # type: ignore[attr-defined]

# Finally register stub with the import machinery
