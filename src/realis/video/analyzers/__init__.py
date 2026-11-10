"""Importing this package registers every video analyzer.

The audio analyzers (AI voice, ENF, edits, bandwidth) also declare the video
modality and run on the soundtrack.
"""

from realis.audio import analyzers as _audio  # noqa: F401
from realis.common import provenance  # noqa: F401  (shared C2PA analyzer)
from realis.video.analyzers import frames, metadata, temporal_edits  # noqa: F401
