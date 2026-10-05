"""Compatibility entry point; implementation lives in the extraction service."""

from app.nodes.rule_extract import rule_extract
from app.tools.ai_extract import ai_extract
from app.tools.document_reader import read_document
from app.services.merge import comparable_value
from app.services.extraction import run_pipeline


def extract(documents: list[dict], mode: str, on_progress=None) -> dict:
    return run_pipeline(documents, mode, reader=read_document, rule_engine=rule_extract,
                        ai_engine=ai_extract, on_progress=on_progress)
