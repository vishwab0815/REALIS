"""Importing this package registers every audio analyzer."""

from realis.audio.analyzers import (  # noqa: F401
    bandwidth,
    edits,
    enf,
    metadata,
    synthetic_voice,
)
from realis.common import provenance  # noqa: F401  (shared C2PA analyzer)
