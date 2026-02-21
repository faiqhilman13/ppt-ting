from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.pptx_skill_paths import resolve_skill_path


def _run_python_script(
    script_path: Path,
    args: list[str],
    *,
    timeout_seconds: int,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(script_path), *args]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=max(10, int(timeout_seconds)),
    )
    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{script_path.name} failed: {err}")
    return result


def _resolve_ooxml_scripts() -> tuple[Path, Path, Path]:
    unpack_script = resolve_skill_path("ooxml/scripts/unpack.py")
    pack_script = resolve_skill_path("ooxml/scripts/pack.py")
    validate_script = resolve_skill_path("ooxml/scripts/validate.py")
    if not unpack_script or not pack_script or not validate_script:
        raise FileNotFoundError("OOXML scripts are not available from PPTX skill root")
    return unpack_script, pack_script, validate_script


def _validate_unpacked(
    *,
    unpacked_dir: Path,
    original_file: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    _, _, validate_script = _resolve_ooxml_scripts()
    result = _run_python_script(
        validate_script,
        [str(unpacked_dir), "--original", str(original_file)],
        timeout_seconds=timeout_seconds,
        check=False,
    )
    return {
        "ok": result.returncode == 0,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
    }


def run_ooxml_roundtrip(
    *,
    source_pptx_path: Path,
    output_path: Path,
    original_pptx_path: Path | None = None,
    patch_mode: str = "none",
) -> dict[str, Any]:
    unpack_script, pack_script, _ = _resolve_ooxml_scripts()
    timeout = int(settings.pptx_ooxml_timeout_seconds)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pptx-ooxml-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        unpacked_dir = temp_dir / "unpacked"
        _run_python_script(
            unpack_script,
            [str(source_pptx_path), str(unpacked_dir)],
            timeout_seconds=timeout,
        )

        # Placeholder patch hook for future structured OOXML transforms.
        applied_patch = str(patch_mode or "none").strip().lower() not in {"", "none"}

        _run_python_script(
            pack_script,
            [str(unpacked_dir), str(output_path), "--force"],
            timeout_seconds=timeout,
        )

        validation = _validate_unpacked(
            unpacked_dir=unpacked_dir,
            original_file=original_pptx_path or source_pptx_path,
            timeout_seconds=timeout,
        )

    return {
        "engine": "template_ooxml",
        "patch_mode": patch_mode or "none",
        "patch_applied": applied_patch,
        "validation_ok": bool(validation.get("ok", False)),
        "validation_stdout": validation.get("stdout", ""),
        "validation_stderr": validation.get("stderr", ""),
    }


def run_ooxml_validation_gate(
    *,
    pptx_path: Path,
    original_pptx_path: Path | None = None,
) -> dict[str, Any]:
    unpack_script, _, _ = _resolve_ooxml_scripts()
    timeout = int(settings.pptx_ooxml_timeout_seconds)

    with tempfile.TemporaryDirectory(prefix="pptx-ooxml-validate-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        unpacked_dir = temp_dir / "unpacked"
        working = temp_dir / "working.pptx"
        shutil.copy2(pptx_path, working)
        _run_python_script(
            unpack_script,
            [str(working), str(unpacked_dir)],
            timeout_seconds=timeout,
        )
        validation = _validate_unpacked(
            unpacked_dir=unpacked_dir,
            original_file=original_pptx_path or pptx_path,
            timeout_seconds=timeout,
        )

    return validation

