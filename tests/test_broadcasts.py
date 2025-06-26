"""Unit tests for broadcasts command – API layer and basic UI helpers.
The interactive loops are not executed end-to-end; we stub user input and
requests so code paths run without network access.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import builtins
import json
from pathlib import Path

import pytest

import blindbase.commands.broadcasts as bc


class _DummyResp:
    def __init__(self, payload: Any, *, ndjson: bool = False):
        self._json = payload
        if ndjson:
            self.text = "\n".join(json.dumps(obj) for obj in payload)
            self.headers = {"content-type": "application/x-ndjson"}
        else:
            self.headers = {"content-type": "application/json"}
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._json  # type: ignore[attr-defined]

    def iter_lines(self, decode_unicode: bool = False):  # noqa: D401 – generator
        for obj in self._json:  # type: ignore[attr-defined]
            yield json.dumps(obj).encode()


@pytest.fixture(autouse=True)
def _no_console(monkeypatch):
    # prevent Rich from actually writing to stdout during tests
    monkeypatch.setattr(bc, "_console", SimpleNamespace(print=lambda *a, **k: None, clear=lambda: None))


def test_get_json_regular(monkeypatch):
    payload = {"foo": "bar"}
    monkeypatch.setattr(bc.requests, "get", lambda *_a, **_k: _DummyResp(payload))
    assert bc._get_json("url") == payload


def test_list_broadcasts(monkeypatch):
    # fake API returns ndjson list of tours
    payload = [{"tour": {"id": "T1", "name": "Event", "startsAt": 1}}]
    monkeypatch.setattr(bc.requests, "get", lambda *_a, **_k: _DummyResp(payload, ndjson=True))
    tours = bc._list_broadcasts()
    assert tours and tours[0]["id"] == "T1"


def test_choose_from_table_back(monkeypatch):
    # stub input to send "b"
    inputs = iter(["b"])
    monkeypatch.setattr(builtins, "input", lambda *_: next(inputs))
    idx = bc._choose_from_table([("row",)], "title", ["c"], allow_back=True)
    assert idx == -1
