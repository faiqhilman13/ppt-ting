from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.pptx_skill_paths import resolve_skill_path


def _run_python_script(script_path: Path, args: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(script_path), *args]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=max(10, int(timeout_seconds)),
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{script_path.name} failed: {err}")
    return result


def _shape_distance(binding: dict[str, Any], shape: dict[str, Any]) -> float:
    return (
        abs(float(shape.get("left", 0.0)) - float(binding.get("left_inches", 0.0)))
        + abs(float(shape.get("top", 0.0)) - float(binding.get("top_inches", 0.0)))
        + abs(float(shape.get("width", 0.0)) - float(binding.get("width_inches", 0.0)))
        + abs(float(shape.get("height", 0.0)) - float(binding.get("height_inches", 0.0)))
    )


def _match_shape_key(slide_shapes: dict[str, Any], binding: dict[str, Any]) -> str | None:
    best_key: str | None = None
    best_score: float | None = None
    for shape_key, shape_value in slide_shapes.items():
        if not isinstance(shape_value, dict):
            continue
        score = _shape_distance(binding, shape_value)
        if best_score is None or score < best_score:
            best_key = str(shape_key)
            best_score = score
    return best_key


def _text_to_paragraphs(text: str) -> list[dict[str, Any]]:
    raw = str(text or "").replace("\r", "\n")
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    if not lines:
        return [{"text": ""}]

    out: list[dict[str, Any]] = []
    for line in lines:
        bullet = False
        clean = line
        if clean.startswith("• "):
            bullet = True
            clean = clean[2:].strip()
        elif clean.startswith("- "):
            bullet = True
            clean = clean[2:].strip()
        elif clean.startswith("* "):
            bullet = True
            clean = clean[2:].strip()
        elif len(clean) > 2 and clean[0].isdigit() and clean[1] in {".", ")"} and clean[2] == " ":
            bullet = True
            clean = clean[3:].strip()
        row: dict[str, Any] = {"text": clean}
        if bullet:
            row["bullet"] = True
        out.append(row)
    return out


def _find_slide_spec(template_manifest: dict[str, Any], template_slide_index: int, payload_position: int) -> dict[str, Any] | None:
    slides = template_manifest.get("slides") or []
    for slide in slides:
        if int(slide.get("index", -1)) == int(template_slide_index):
            return slide
    if 0 <= payload_position < len(slides):
        return slides[payload_position]
    return None


def _resolve_local_slide_index(
    *,
    payload_position: int,
    template_slide_index: int,
    slide_sequence: list[int],
    inventory_keys: set[str],
) -> int | None:
    preferred = f"slide-{payload_position}"
    if preferred in inventory_keys:
        return payload_position

    by_template = f"slide-{template_slide_index}"
    if by_template in inventory_keys:
        return template_slide_index

    if payload_position < len(slide_sequence):
        seq_index = int(slide_sequence[payload_position])
        seq_key = f"slide-{seq_index}"
        if seq_key in inventory_keys:
            return seq_index
    return None


def _build_replacements(
    *,
    inventory: dict[str, Any],
    slides_payload: list[dict[str, Any]],
    template_manifest: dict[str, Any],
    slide_sequence: list[int],
) -> tuple[dict[str, Any], int]:
    replacements = copy.deepcopy(inventory)
    replaced_slots = 0
    inventory_keys = set(inventory.keys())

    for payload_pos, slide_payload in enumerate(slides_payload):
        template_slide_index = int(slide_payload.get("template_slide_index", -1))
        local_slide_index = _resolve_local_slide_index(
            payload_position=payload_pos,
            template_slide_index=template_slide_index,
            slide_sequence=slide_sequence,
            inventory_keys=inventory_keys,
        )
        if local_slide_index is None:
            continue
        slide_key = f"slide-{local_slide_index}"
        slide_shapes = replacements.get(slide_key)
        if not isinstance(slide_shapes, dict):
            continue

        slide_spec = _find_slide_spec(template_manifest, template_slide_index, payload_pos)
        if not isinstance(slide_spec, dict):
            continue

        slot_bindings: dict[str, dict[str, Any]] = {}
        for binding in slide_spec.get("bindings", []):
            slot = str(binding.get("slot", "")).strip()
            if not slot:
                continue
            slot_bindings.setdefault(slot, binding)

        for slot_name, slot_value in (slide_payload.get("slots") or {}).items():
            binding = slot_bindings.get(str(slot_name))
            if not binding:
                continue
            kind = str(binding.get("kind", ""))
            if kind not in {"shape_text", "token_text"}:
                continue
            shape_key = _match_shape_key(slide_shapes, binding)
            if not shape_key or shape_key not in slide_shapes:
                continue
            shape_entry = slide_shapes[shape_key]
            if not isinstance(shape_entry, dict):
                continue
            shape_entry["paragraphs"] = _text_to_paragraphs(str(slot_value or ""))
            replaced_slots += 1

    return replacements, replaced_slots


def render_template_with_replace(
    *,
    source_pptx_path: Path,
    output_path: Path,
    slides_payload: list[dict[str, Any]],
    template_manifest: dict[str, Any],
    slide_sequence: list[int] | None = None,
) -> dict[str, Any]:
    rearrange_script = resolve_skill_path("scripts/rearrange.py")
    inventory_script = resolve_skill_path("scripts/inventory.py")
    replace_script = resolve_skill_path("scripts/replace.py")
    if not rearrange_script or not inventory_script or not replace_script:
        raise FileNotFoundError("Template replace scripts are not available from PPTX skill root")

    timeout = int(settings.pptx_replace_timeout_seconds)
    sequence = [int(row) for row in (slide_sequence or [])]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pptx-replace-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        working_input = temp_dir / "working-input.pptx"
        shutil.copy2(source_pptx_path, working_input)
        working_pptx = working_input

        if sequence:
            rearranged = temp_dir / "working-rearranged.pptx"
            sequence_arg = ",".join(str(row) for row in sequence)
            _run_python_script(
                rearrange_script,
                [str(working_input), str(rearranged), sequence_arg],
                timeout_seconds=timeout,
            )
            working_pptx = rearranged

        inventory_path = temp_dir / "inventory.json"
        _run_python_script(
            inventory_script,
            [str(working_pptx), str(inventory_path)],
            timeout_seconds=timeout,
        )
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

        replacements, replaced_slots = _build_replacements(
            inventory=inventory,
            slides_payload=slides_payload,
            template_manifest=template_manifest,
            slide_sequence=sequence,
        )
        replacements_path = temp_dir / "replacements.json"
        replacements_path.write_text(json.dumps(replacements, ensure_ascii=False, indent=2), encoding="utf-8")

        _run_python_script(
            replace_script,
            [str(working_pptx), str(replacements_path), str(output_path)],
            timeout_seconds=timeout,
        )

        issues_path = temp_dir / "issues.json"
        _run_python_script(
            inventory_script,
            [str(output_path), str(issues_path), "--issues-only"],
            timeout_seconds=timeout,
        )
        issues = json.loads(issues_path.read_text(encoding="utf-8"))
        issue_count = sum(len(v) for v in issues.values() if isinstance(v, dict))

    return {
        "engine": "template_replace",
        "replaced_slots": replaced_slots,
        "issue_count": issue_count,
    }

