"""Importing this package registers every image analyzer."""

from realis.common import provenance  # noqa: F401  (shared C2PA analyzer)
from realis.image.analyzers import (  # noqa: F401
    ai_generated,
    copy_move,
    ela,
    jpeg_structure,
    metadata,
    noise,
    trufor,
)
