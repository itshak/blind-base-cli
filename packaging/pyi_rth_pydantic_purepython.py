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
import types

# Set PYDANTIC_PUREPYTHON=1 to force pure-python mode
os.environ.setdefault("PYDANTIC_PUREPYTHON", "1")

# Create a minimal stub for pydantic_core to prevent import errors
stub = types.ModuleType('pydantic_core')
stub.__version__ = '0.0.0'

# Add all necessary attributes that Pydantic might try to import
stub.PydanticUndefined = object()
stub.PydanticUndefinedType = type(stub.PydanticUndefined)
stub.PydanticUndefinedAny = object()
stub.PydanticUndefinedTypeAny = type(stub.PydanticUndefinedAny)
stub.PydanticUndefinedType = type(stub.PydanticUndefined)

# Add some additional attributes that might be needed
stub.PydanticValueError = type('PydanticValueError', (ValueError,), {})
stub.PydanticTypeError = type('PydanticTypeError', (TypeError,), {})
stub.PydanticRuntimeError = type('PydanticRuntimeError', (RuntimeError,), {})

# Create a very small sub-module to satisfy `from pydantic_core import core_schema`
core_schema_module = types.ModuleType('pydantic_core.core_schema')
sys.modules['pydantic_core.core_schema'] = core_schema_module
# Re-export it as an attribute so `from pydantic_core import core_schema` works
stub.core_schema = core_schema_module

# Create additional sub-modules that might be needed
errors_module = types.ModuleType('pydantic_core.errors')
sys.modules['pydantic_core.errors'] = errors_module
stub.errors = errors_module

# Provide empty compiled-extension submodule so that relative imports like
# `from pydantic_core import _pydantic_core` or `import pydantic_core._pydantic_core`
# succeed even in pure-python mode.
core_so_stub = types.ModuleType('pydantic_core._pydantic_core')
sys.modules['pydantic_core._pydantic_core'] = core_so_stub
stub._pydantic_core = core_so_stub

# Mark as namespace package for completeness
stub.__path__ = []  # type: ignore[attr-defined]

# Finally register stub with the import machinery
sys.modules['pydantic_core'] = stub
