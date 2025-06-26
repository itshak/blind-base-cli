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
    sys.modules['pydantic_core._pydantic_core'] = core_so_stub
    stub._pydantic_core = core_so_stub

    # Mark as namespace package for completeness
    stub.__path__ = []  # type: ignore[attr-defined]

    # Finally register stub with the import machinery
    sys.modules['pydantic_core'] = stub
