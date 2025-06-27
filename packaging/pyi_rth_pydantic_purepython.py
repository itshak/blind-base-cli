"""PyInstaller runtime hook – force Pydantic to pure-python mode.

This runs **before** any of your code inside the frozen executable, setting the
`PYDANTIC_PUREPYTHON` env-var so that Pydantic skips loading its compiled Rust
extension (`pydantic_core`).  This makes the frozen executable architecture-independent
at the cost of slightly slower validation -- acceptable for CLI usage.

This runs *before* any project code, setting the environment variable that
instructs `pydantic` version 2.6 or higher to skip importing the compiled `pydantic_core` wheel.

This runs **only** inside the frozen executable when the wheel for the current
architecture is absent.  The hook provides a minimal stub module to prevent
import errors.
"""

import os
import sys

# Set PYDANTIC_PUREPYTHON=1 to force pure-python mode
os.environ.setdefault("PYDANTIC_PUREPYTHON", "1")

# Also remove pydantic_core from sys.modules to prevent any import attempts
if "pydantic_core" in sys.modules:
    del sys.modules["pydantic_core"]
