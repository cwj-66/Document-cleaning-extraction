"""图文混排 PDF / MinerU. Thin adapter; importing does not load models.

The former notebook-specific APIs are replaced by extract / extract_and_chunk.
"""
from document_cleaning import parse_document


def extract(file_path, **options):
    settings = {'tier': 'advanced'}
    settings.update(options)
    return parse_document(file_path, engine='mineru', **settings)


def extract_and_chunk(file_path, **options):
    return extract(file_path, **options).chunks
