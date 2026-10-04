"""Lazy document adapters: importing this package never loads model weights."""

from .pipeline import ParsedDocument, parse_document

__all__ = ["ParsedDocument", "parse_document"]
