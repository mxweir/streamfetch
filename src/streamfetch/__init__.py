"""Core package for StreamFetch."""

from .models import DownloadRequest, DownloadResult, MediaType, ProgressEvent, SourcePreview

__all__ = [
    "DownloadRequest",
    "DownloadResult",
    "MediaType",
    "ProgressEvent",
    "SourcePreview",
]

__version__ = "1.0.0"
