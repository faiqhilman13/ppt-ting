from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

TOKEN_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_:-]+)\s*\}\}")

app = FastAPI(title="Template Fidelity PPTX Renderer")


class SlideInstruction(BaseModel):
    template_slide_index: int
    slots: dict[str, str] = Field(default_factory=dict)


class RenderRequest(BaseModel):
    deckId: str
    version: int
    slides: list[SlideInstruction]
    templateManifest: dict = Field(default_factory=dict)
    templatePath: str | None = None
    basePptxPath: str | None = None
    outputPath: str


@app.get("/health")
def health():
    return {"status": "ok"}


def _iter_shapes(shape_collection):
    for shape in shape_collection:
        yield shape
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(shape.shapes)


def _replace_tokens(text: str, token_map: dict[str, str]) -> str:
    if not text:
        return text

    def repl(match):
        key = match.group(1).upper()
        return token_map.get(key, match.group(0))

    return TOKEN_PATTERN.sub(repl, text)


def _apply_token_replacements(slide, token_map: dict[str, str]) -> None:
    for shape in _iter_shapes(slide.shapes):
        if getattr(shape, "has_text_frame", False):
            new_text = _replace_tokens(shape.text_frame.text or "", token_map)
            if new_text != (shape.text_frame.text or ""):
                shape.text = new_text

        if getattr(shape, "has_table", False):
            for row in shape.table.rows:
                for cell in row.cells:
                    new_cell_text = _replace_tokens(cell.text or "", token_map)
                    if new_cell_text != (cell.text or ""):
                        cell.text = new_cell_text


def _find_shape_by_id(slide, shape_id: int):
    for shape in _iter_shapes(slide.shapes):
        if int(getattr(shape, "shape_id", -1)) == shape_id:
            return shape
    return None


def _apply_shape_bindings(slide, slide_manifest: dict, slot_values: dict[str, str]) -> None:
    for binding in slide_manifest.get("bindings", []):
        slot_name = str(binding.get("slot", "")).upper()
        if slot_name not in slot_values:
            continue

        if binding.get("kind") != "shape_text":
            continue

        shape_id = int(binding.get("shape_id", -1))
        shape = _find_shape_by_id(slide, shape_id)
        if not shape or not getattr(shape, "has_text_frame", False):
            continue

        shape.text = slot_values[slot_name]


def _prune_unselected_slides(prs: Presentation, selected_indices: set[int]) -> None:
    # Keep selected slides only to avoid leaking untouched template content.
    for idx in range(len(prs.slides) - 1, -1, -1):
        if idx in selected_indices:
            continue
        slide_id = prs.slides._sldIdLst[idx].rId
        prs.part.drop_rel(slide_id)
        del prs.slides._sldIdLst[idx]


def _render(req: RenderRequest) -> None:
    source_path = Path(req.basePptxPath or req.templatePath or "")
    if not source_path.exists():
        raise FileNotFoundError(f"Source PPTX does not exist: {source_path}")

    output_path = Path(req.outputPath)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, output_path)

    prs = Presentation(str(output_path))
    manifest_by_index = {int(slide.get("index", i)): slide for i, slide in enumerate(req.templateManifest.get("slides", []))}

    for instruction in req.slides:
        idx = instruction.template_slide_index
        if idx < 0 or idx >= len(prs.slides):
            continue

        slide = prs.slides[idx]
        slot_values = {k.upper(): str(v) for k, v in instruction.slots.items()}
        _apply_token_replacements(slide, slot_values)
        _apply_shape_bindings(slide, manifest_by_index.get(idx, {}), slot_values)

    selected_indices = {int(item.template_slide_index) for item in req.slides}
    _prune_unselected_slides(prs, selected_indices)

    prs.save(str(output_path))


@app.post("/render")
def render(req: RenderRequest):
    try:
        _render(req)
        return {"status": "ok", "outputPath": req.outputPath}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Render failed: {exc}") from exc
