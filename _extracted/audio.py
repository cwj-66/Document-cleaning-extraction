"""音频 / Qwen3-ASR + ForcedAligner. Thin adapter; importing does not load models.

The former notebook-specific APIs are replaced by extract / extract_and_chunk.
"""
from document_cleaning import parse_document


def extract(file_path, **options):
    settings = {'timestamps': True}
    settings.update(options)
    return parse_document(file_path, engine='qwen-asr', **settings)


def extract_and_chunk(file_path, **options):
    return extract(file_path, **options).chunks
