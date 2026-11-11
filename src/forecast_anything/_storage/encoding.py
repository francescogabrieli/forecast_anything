"""Canonical encoding and deterministic identities for ledger records."""

import json
from hashlib import sha256


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(namespace: str, *parts: str) -> str:
    return sha256("/".join((namespace, *parts)).encode("utf-8")).hexdigest()


def _hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()
