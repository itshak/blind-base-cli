"""PyInstaller runtime hook – force Pydantic to pure-python mode.

This runs **before** any of your code inside the frozen executable, setting the
`PYDANTIC_PUREPYTHON` env-var so that Pydantic skips loading its compiled Rust
extension (`pydantic_core`).  Doing so avoids architecture-specific binary
issues – the app will start on any mac (Intel or Apple Silicon).
"""

import os

# Respect explicit user choice, otherwise default to safe fallback.
os.environ.setdefault("PYDANTIC_PUREPYTHON", "1")
"""

import os

# Respect explicit user choice, otherwise default to the safe fallback.
os.environ.setdefault("PYDANTIC_PUREPYTHON", "1")


Setting the environment variable before any project imports guarantees
Pydantic skips the compiled Rust extension (`pydantic_core`).  This makes
the frozen executable architecture-independent at the cost of slightly
slower validation – acceptable for CLI usage."""

This runs *before* any project code, setting the environment variable that
instructs `pydantic` ≥2.6 to skip importing the compiled `pydantic_core` wheel.
It prevents the common "ModuleNotFoundError: pydantic_core" error when the
binary wheel for the running architecture is missing (e.g. in a one-file
PyInstaller bundle).
"""
import os

# Respect explicit user choice, otherwise default to pure-python fallback.
os.environ.setdefault("PYDANTIC_PUREPYTHON", "1")

# Provide a minimal stub so that `import pydantic_core` succeeds when the
# compiled extension wheel is absent (e.g. different architecture) and
# `PYDANTIC_PUREPYTHON` is set.  This prevents the import error raised from
# inside pydantic/version.py when it tries to read pydantic_core.__version__.
# No further stubs required – if the compiled wheel is absent, imports fall
# back to the pure-python path cleanly.
    stub = types.ModuleType('pydantic_core')

    # ------------------------------------------------------------------
    # Provide minimal API surface expected by pydantic when running in
    # PYDANTIC_PUREPYTHON mode.  We purposefully keep the implementation very
    # small – just enough to satisfy imports – as performance is not a concern
    # inside the frozen executable.
    # ------------------------------------------------------------------
    class _PydanticUndefinedType:
        """Sentinel used by Pydantic to denote an undefined value."""

        __slots__ = ()

        def __repr__(self) -> str:  # pragma: no cover – repr is trivial
            return "PydanticUndefined"

        def __reduce__(self):  # pragma: no cover – pickle support, mirrors real impl
            return ("pydantic_core.PydanticUndefined", ())

    PydanticUndefined: object = _PydanticUndefinedType()  # type: ignore[var-annotated]

    # Expose symbols that pydantic imports at module level
    stub.PydanticUndefined = PydanticUndefined
    stub.PydanticUndefinedType = _PydanticUndefinedType

    # Bare-bones stand-ins for validator / serializer classes used in
    # type-checking branches.  They are *never* instantiated when the pure-python
    # backend is active but need to exist for `from pydantic_core import ...`
    # statements to succeed.
    class _NoCoreStub:  # pragma: no cover
        def __getattr__(self, item):
            raise RuntimeError(
                "pydantic_core compiled backend is unavailable in this build. "
                "If you hit this error please report a bug."
            )

    stub.SchemaValidator = _NoCoreStub
    stub.SchemaSerializer = _NoCoreStub

    # Generic fallback so any future symbol access on the parent stub returns a
    # safe placeholder instead of raising ImportError (covers e.g.
    # PydanticKnownError, PydanticSerializationError, etc.).
    def _return_no_core_stub(name):  # pragma: no cover
        return _NoCoreStub

    stub.__getattr__ = _return_no_core_stub

    # Minimal replacement for the custom error class
    class PydanticCustomError(Exception):  # pragma: no cover
        """Placeholder matching the public interface of pydantic_core.PydanticCustomError."""

        def __init__(self, kind: str, message_template: str, context: dict | None = None):
            self.kind = kind
            self.message_template = message_template
            self.context = context or {}
            super().__init__(self.message_template.format(**self.context))

        def __reduce__(self):  # required for pickle compat
            return (
                PydanticCustomError,
                (self.kind, self.message_template, self.context),
            )

    stub.PydanticCustomError = PydanticCustomError

    # Create a very small sub-module to satisfy `from pydantic_core import core_schema`
    core_schema_module = types.ModuleType('pydantic_core.core_schema')
    sys.modules['pydantic_core.core_schema'] = core_schema_module
    # Re-export it as an attribute so `from pydantic_core import core_schema` works
    stub.core_schema = core_schema_module

    stub.__version__ = '0.0.0'

        # Provide empty compiled-extension submodule so that relative imports like
    # `from pydantic_core import _pydantic_core` or `import pydantic_core._pydantic_core`
    # succeed even in pure-python mode.
    core_so_stub = types.ModuleType('pydantic_core._pydantic_core')
    # Provide the same generic attribute fallback inside the extension submodule.
    core_so_stub.__getattr__ = _return_no_core_stub
    sys.modules['pydantic_core._pydantic_core'] = core_so_stub
    stub._pydantic_core = core_so_stub

    # Mark as namespace package for completeness
    stub.__path__ = []  # type: ignore[attr-defined]

    # Finally register stub with the import machinery
    
