"""Modern document engines with explicit execution and preserved raw outputs.

Adapters follow upstream APIs; model inference has not been validated here.
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4


@dataclass
class ParsedDocument:
    source: str
    engine: str
    output_dir: str
    markdown: str
    blocks: list[dict] = field(default_factory=list)
    chunks: list[dict] = field(default_factory=list)


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _chunks(blocks, source, size, overlap):
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Require chunk_size > 0 and 0 <= overlap < chunk_size")
    chunks = []
    for block_id, block in enumerate(blocks):
        text = block.get("text", "").strip()
        if not text:
            continue
        # Tables/equations are atomic, even when larger than the character budget.
        atomic = any(x in block.get("kind", "") for x in ("table", "equation", "formula"))
        start = 0
        while start < len(text):
            end = len(text) if atomic else min(len(text), start + size)
            chunks.append({**block, "text": text[start:end], "source": source,
                           "block_id": block_id, "char_start": start, "char_end": end,
                           "chunk_id": len(chunks)})
            if end == len(text):
                break
            start = end - overlap
    return chunks


def _content_text(value):
    """Preserve unfamiliar structured content rather than silently dropping it."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_content_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "html", "content", "table_body", "latex"):
            if key in value:
                return _content_text(value[key])
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _mineru(path, out, tier="standard"):
    from mineru.parser import parse
    from mineru.parser.writer import FileBasedDataWriter

    if tier not in {"standard", "advanced"}:
        raise ValueError("This adapter uses MinerU standard or advanced tiers")
    result = parse(str(path), tier=tier)
    result.save(FileBasedDataWriter(str(out)))
    saved = out / "structured_content.json"
    raw = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else result.structured_content()
    _write_json(out / "engine.json", raw)
    blocks = []
    for page in raw.get("pages", []):
        for block in page.get("blocks", []):
            index = page.get("page_idx")
            blocks.append({"kind": block.get("type", "unknown"),
                           "text": _content_text(block.get("content", block)),
                           "page": index + 1 if index is not None else None,
                           "raw": block})
    if not blocks:
        raise RuntimeError("MinerU returned no structured blocks; inspect engine.json")
    md_path = out / "markdown.md"
    markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else result.markdown()
    return markdown, blocks


def _docling(path, out):
    from docling.document_converter import DocumentConverter

    input_path = path
    if path.suffix.lower() == ".tsv":
        input_path = out / "converted-input.csv"
        with path.open(encoding="utf-8-sig", newline="") as source:
            with input_path.open("w", encoding="utf-8", newline="") as target:
                csv.writer(target).writerows(csv.reader(source, delimiter="\t"))
    converted = DocumentConverter().convert(str(input_path))
    status = getattr(converted.status, "value", str(converted.status))
    if status != "success":
        raise RuntimeError(f"Docling conversion status: {status}; errors: {converted.errors}")
    doc = converted.document
    _write_json(out / "engine.json", doc.export_to_dict())
    blocks = []
    for item, depth in doc.iterate_items():
        label = getattr(item.label, "value", str(item.label))
        text = getattr(item, "text", "")
        if label == "table":
            text = item.export_to_markdown(doc=doc)
        elif label == "picture":
            text = item.caption_text(doc) or "[Picture: see engine.json]"
        if not text:
            continue
        provenance = [p.model_dump(mode="json") for p in getattr(item, "prov", [])]
        blocks.append({"kind": label, "text": text, "depth": depth,
                       "page": provenance[0].get("page_no") if provenance else None,
                       "provenance": provenance, "reference": item.self_ref})
    return doc.export_to_markdown(), blocks


def _paddle(path, out, device=None):
    from paddleocr import PaddleOCRVL

    options = {"pipeline_version": "v1.6", "use_chart_recognition": True}
    if device:
        options["device"] = device
    for env, key in (("PADDLE_LAYOUT_MODEL_DIR", "layout_detection_model_dir"),
                     ("PADDLE_VL_MODEL_DIR", "vl_rec_model_dir")):
        if os.environ.get(env):
            options[key] = os.environ[env]
    pipeline = PaddleOCRVL(**options)
    blocks, markdown = [], []
    for index, result in enumerate(pipeline.predict(input=str(path))):
        page_dir = out / f"page-{index + 1}"
        page_dir.mkdir()
        result.save_to_json(save_path=str(page_dir))
        result.save_to_markdown(save_path=str(page_dir))
        json_files = list(page_dir.glob("*.json"))
        if len(json_files) != 1:
            raise RuntimeError(f"Expected one PaddleOCR page JSON in {page_dir}")
        raw = json.loads(json_files[0].read_text(encoding="utf-8"))
        raw = raw.get("res", raw)
        for block in raw.get("parsing_res_list", []):
            blocks.append({"kind": block.get("block_label", "unknown"),
                           "text": _content_text(block.get("block_content", "")),
                           "page": index + 1, "bbox": block.get("block_bbox"), "raw": block})
        # Keep each Markdown alongside its image assets; the index links to it.
        for md in page_dir.glob("*.md"):
            markdown.append(f"[Page {index + 1}]({md.relative_to(out).as_posix()})")
    if not blocks:
        raise RuntimeError("PaddleOCR-VL returned no blocks; inspect page outputs")
    return "\n\n".join(markdown), blocks


def _qwen(path, out, device=None, timestamps=True):
    import torch
    from qwen_asr import Qwen3ASRModel

    device = device or os.getenv("QWEN_ASR_DEVICE", "cuda:0")
    dtype = torch.float32 if device == "cpu" else torch.bfloat16
    options = {"dtype": dtype, "device_map": device,
               "max_inference_batch_size": 1, "max_new_tokens": 4096}
    if timestamps:
        options.update(forced_aligner=os.getenv("QWEN_ALIGNER_MODEL", "Qwen/Qwen3-ForcedAligner-0.6B"),
                       forced_aligner_kwargs={"dtype": dtype, "device_map": device})
    model = Qwen3ASRModel.from_pretrained(os.getenv("QWEN_ASR_MODEL", "Qwen/Qwen3-ASR-1.7B"), **options)
    results = model.transcribe(audio=str(path), language=None, return_time_stamps=timestamps)
    blocks, transcripts = [], []
    for result in results:
        transcripts.append(result.text)
        stamps = result.time_stamps if timestamps else None
        if timestamps and result.text.strip() and not stamps:
            raise RuntimeError("Requested alignment is unavailable; set timestamps=False for transcript only")
        if stamps:
            # Aggregate aligned words into roughly 30-second passages.
            group = []
            for stamp in stamps:
                if group and stamp.end_time - group[0].start_time > 30:
                    blocks.append(_audio_block(group, result.language))
                    group = []
                group.append(stamp)
            if group:
                blocks.append(_audio_block(group, result.language))
        else:
            blocks.append({"kind": "transcript", "text": result.text, "language": result.language})
    _write_json(out / "engine.json", {"transcripts": transcripts, "segments": blocks})
    return "\n\n".join(transcripts), blocks


def _audio_block(group, language):
    words = [{"text": x.text, "start": float(x.start_time), "end": float(x.end_time)} for x in group]
    return {"kind": "transcript", "text": " ".join(x["text"] for x in words),
            "language": language, "start": words[0]["start"], "end": words[-1]["end"],
            "words": words}


ROUTES = {**dict.fromkeys([".pdf"], "mineru"),
          **dict.fromkeys([".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"], "paddleocr"),
          **dict.fromkeys([".docx", ".pptx", ".xlsx", ".csv", ".tsv", ".html", ".htm", ".eml", ".msg"], "docling"),
          **dict.fromkeys([".wav", ".mp3", ".flac", ".m4a", ".ogg"], "qwen-asr")}


def parse_document(file_path, *, engine="auto", output_dir="outputs", chunk_size=1200,
                   overlap=150, **engine_options):
    """Calling this function explicitly starts parsing and may download weights.

    Missing dependencies/model failures propagate; no fallback engine is used.
    All lengths are characters. Chunk times cover their parent aligned segment.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if chunk_size <= 0 or not 0 <= overlap < chunk_size:
        raise ValueError("Invalid chunk_size/overlap")
    engine = ROUTES.get(path.suffix.lower()) if engine == "auto" else engine
    adapters = {"mineru": _mineru, "docling": _docling, "paddleocr": _paddle, "qwen-asr": _qwen}
    if engine not in adapters:
        raise ValueError(f"Unsupported engine or file extension: {engine}, {path.suffix}")
    out = Path(output_dir).resolve() / f"{path.stem}-{uuid4().hex[:12]}"
    out.mkdir(parents=True)
    markdown, blocks = adapters[engine](path, out, **engine_options)
    result = ParsedDocument(str(path), engine, str(out), markdown, blocks,
                            _chunks(blocks, str(path), chunk_size, overlap))
    (out / "document.md").write_text(markdown, encoding="utf-8")
    _write_json(out / "document.json", asdict(result))
    _write_json(out / "chunks.json", result.chunks)
    return result
