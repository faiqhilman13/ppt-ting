import json
import logging
from time import perf_counter
from typing import Any

from openai import OpenAI

from app.config import settings
from app.providers.base import BaseLLMProvider, SlideContent
from app.services.prompt_templates import build_generation_prompts, build_revision_prompts


logger = logging.getLogger("ppt_agent.providers")


def _preview_text(text: str, limit: int | None = None) -> str:
    raw = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    cap = int(limit or settings.log_preview_chars)
    if len(raw) <= cap:
        return raw
    return raw[:cap].rstrip() + " ..."


def _slides_preview(rows: list[SlideContent], max_rows: int = 4) -> list[dict]:
    preview: list[dict] = []
    for row in rows[:max_rows]:
        slots: dict[str, str] = {}
        for idx, (slot, value) in enumerate((row.slots or {}).items()):
            if idx >= 4:
                break
            slots[str(slot)] = _preview_text(str(value), 110)
        preview.append({"template_slide_index": row.template_slide_index, "slots": slots})
    return preview


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, api_key: str):
        super().__init__()
        self.client = OpenAI(api_key=api_key)

    @staticmethod
    def _fallback(template_manifest: dict, fallback_count: int, text: str) -> list[SlideContent]:
        slides = template_manifest.get("slides", [])[:fallback_count]
        payload: list[SlideContent] = []
        for idx, slide in enumerate(slides):
            slots = {
                slot: (text[:700] if i == 0 else f"Generated content {idx + 1}")
                for i, slot in enumerate(slide.get("slots", []))
            }
            payload.append(SlideContent(template_slide_index=slide.get("index", idx), slots=slots))
        return payload

    @staticmethod
    def _schema_for_slides(selected_slides: list[dict]) -> dict[str, Any]:
        slide_variants: list[dict[str, Any]] = []
        dedupe: set[int] = set()

        for idx, slide in enumerate(selected_slides):
            slide_index = int(slide.get("index", idx))
            if slide_index in dedupe:
                continue
            dedupe.add(slide_index)

            slots = [str(slot) for slot in (slide.get("slots") or []) if str(slot).strip()]
            slot_props = {slot: {"type": "string"} for slot in slots}
            slot_required = list(slot_props.keys())

            slide_variants.append(
                {
                    "type": "object",
                    "properties": {
                        "template_slide_index": {"type": "integer", "enum": [slide_index]},
                        "slots": {
                            "type": "object",
                            "properties": slot_props,
                            "required": slot_required,
                            "additionalProperties": False,
                        },
                    },
                    "required": ["template_slide_index", "slots"],
                    "additionalProperties": False,
                }
            )

        if not slide_variants:
            slide_variants = [
                {
                    "type": "object",
                    "properties": {
                        "template_slide_index": {"type": "integer"},
                        "slots": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                            "additionalProperties": True,
                        },
                    },
                    "required": ["template_slide_index", "slots"],
                    "additionalProperties": False,
                }
            ]

        return {
            "type": "object",
            "properties": {
                "slides": {
                    "type": "array",
                    "items": {"anyOf": slide_variants},
                }
            },
            "required": ["slides"],
            "additionalProperties": False,
        }

    @staticmethod
    def _parse(
        payload: dict[str, Any],
        template_manifest: dict,
        fallback_count: int,
        fallback_text: str,
    ) -> tuple[list[SlideContent], bool]:
        try:
            rows = payload.get("slides", [])
            parsed: list[SlideContent] = []
            for idx, row in enumerate(rows):
                parsed.append(
                    SlideContent(
                        template_slide_index=row.get("template_slide_index", idx),
                        slots={k: str(v) for k, v in (row.get("slots") or {}).items()},
                    )
                )
            if parsed:
                return parsed, False
        except Exception:
            pass

        return OpenAIProvider._fallback(template_manifest, fallback_count, fallback_text), True

    def _run_structured_request(
        self,
        *,
        system: str,
        user: str,
        output_schema: dict[str, Any],
        request_label: str = "structured",
        retries: int = 2,
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            started = perf_counter()
            logger.info(
                "openai_request_start label=%s model=%s attempt=%d/%d input_chars=%d system_preview=%s user_preview=%s",
                request_label,
                settings.openai_model,
                attempt + 1,
                retries + 1,
                len(system) + len(user),
                _preview_text(system, 140),
                _preview_text(user, 220),
            )
            try:
                response = self.client.responses.create(
                    model=settings.openai_model,
                    input=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "slide_slot_payload",
                            "schema": output_schema,
                            "strict": True,
                        }
                    },
                )
                text = (response.output_text or "").strip()
                if not text:
                    raise ValueError("OpenAI returned empty structured output")
                logger.info(
                    "openai_request_done label=%s duration_sec=%.2f output_chars=%d output_preview=%s",
                    request_label,
                    perf_counter() - started,
                    len(text),
                    _preview_text(text, 220),
                )
                return json.loads(text)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "openai_request_error label=%s attempt=%d/%d duration_sec=%.2f reason=%s",
                    request_label,
                    attempt + 1,
                    retries + 1,
                    perf_counter() - started,
                    exc,
                )

        if last_error:
            raise last_error
        raise RuntimeError("OpenAI structured request failed with unknown error")

    def generate_slides(self, prompt, research_chunks, template_manifest, slide_count, extra_instructions=None, deck_thesis=None):
        self.reset_warnings()
        selected = (template_manifest.get("slides") or [])[:slide_count]
        system, user = build_generation_prompts(
            prompt=prompt,
            extra_instructions=extra_instructions,
            selected_slides=selected,
            research_chunks=research_chunks,
            template_bound=not str(template_manifest.get("version", "")).startswith("scratch"),
            deck_thesis=deck_thesis,
        )
        schema = self._schema_for_slides(selected)

        try:
            payload = self._run_structured_request(
                system=system,
                user=user,
                output_schema=schema,
                request_label="generate_slides",
            )
            fallback_text = json.dumps(payload, ensure_ascii=True)
            parsed, used_fallback = self._parse(payload, template_manifest, len(selected), fallback_text)
            if used_fallback:
                self.last_warnings.append("OpenAI returned invalid structured payload; fallback content was used.")
            logger.info(
                "openai_generate_parsed slides=%d fallback=%s preview=%s",
                len(parsed),
                used_fallback,
                _slides_preview(parsed),
            )
            return parsed
        except Exception as exc:
            self.last_warnings.append(f"OpenAI request failed; fallback content was used ({exc}).")
            return self._fallback(template_manifest, len(selected), f"OpenAI fallback: {exc}")

    def revise_slides(self, prompt, existing_slides, research_chunks, template_manifest):
        self.reset_warnings()
        system, user = build_revision_prompts(
            revision_prompt=prompt,
            existing_slides=existing_slides,
            template_manifest=template_manifest,
            research_chunks=research_chunks,
        )
        by_index = {int(slide.get("index", idx)): slide for idx, slide in enumerate(template_manifest.get("slides", []))}
        selected = [by_index.get(int(row.get("template_slide_index", -1)), {}) for row in existing_slides]
        selected = [row for row in selected if row]
        schema = self._schema_for_slides(selected or (template_manifest.get("slides") or []))

        try:
            payload = self._run_structured_request(
                system=system,
                user=user,
                output_schema=schema,
                request_label="revise_slides",
            )
            fallback_text = json.dumps(payload, ensure_ascii=True)
            parsed, used_fallback = self._parse(payload, template_manifest, len(existing_slides), fallback_text)
            if used_fallback:
                self.last_warnings.append("OpenAI returned invalid structured payload during revision; fallback content was used.")
            logger.info(
                "openai_revise_parsed slides=%d fallback=%s preview=%s",
                len(parsed),
                used_fallback,
                _slides_preview(parsed),
            )
            return parsed
        except Exception as exc:
            self.last_warnings.append(f"OpenAI revision request failed; fallback content was used ({exc}).")
            return self._fallback(template_manifest, len(existing_slides), f"OpenAI fallback: {exc}")

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 180,
        retries: int | None = None,
    ) -> str:
        schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
            "additionalProperties": False,
        }
        try:
            payload = self._run_structured_request(
                system=system_prompt,
                user=user_prompt,
                output_schema=schema,
                request_label="generate_text",
                retries=max(0, int(retries)) if retries is not None else 1,
            )
            output = str(payload.get("text", "")).strip()
            if output:
                return output
            raise ValueError("OpenAI generate_text returned empty text field")
        except Exception as exc:
            self.last_warnings.append(f"OpenAI text generation failed ({exc}).")
            return user_prompt.strip()

    def generate_outline(
        self,
        *,
        prompt: str,
        template_manifest: dict,
        slide_count: int,
        research_chunks: list[dict],
    ) -> dict:
        self.reset_warnings()
        all_slides = template_manifest.get("slides") or []

        slide_variants: list[dict[str, Any]] = []
        for idx, slide in enumerate(all_slides):
            slide_index = int(slide.get("index", idx))
            slide_variants.append(
                {
                    "type": "object",
                    "properties": {
                        "template_slide_index": {"type": "integer", "enum": [slide_index]},
                        "narrative_role": {"type": "string"},
                        "key_message": {"type": "string"},
                    },
                    "required": ["template_slide_index", "narrative_role", "key_message"],
                    "additionalProperties": False,
                }
            )

        if not slide_variants:
            slide_variants.append(
                {
                    "type": "object",
                    "properties": {
                        "template_slide_index": {"type": "integer"},
                        "narrative_role": {"type": "string"},
                        "key_message": {"type": "string"},
                    },
                    "required": ["template_slide_index", "narrative_role", "key_message"],
                    "additionalProperties": False,
                }
            )

        schema = {
            "type": "object",
            "properties": {
                "thesis": {"type": "string"},
                "slides": {
                    "type": "array",
                    "items": {"anyOf": slide_variants},
                },
            },
            "required": ["thesis", "slides"],
            "additionalProperties": False,
        }

        candidates = []
        for row in all_slides:
            candidates.append(
                {
                    "template_slide_index": row.get("index"),
                    "archetype": row.get("archetype"),
                    "slots": row.get("slots", []),
                    "name": row.get("name"),
                }
            )

        user_payload = json.dumps(
            {
                "prompt": prompt,
                "slide_count": slide_count,
                "candidate_slides": candidates,
                "research_titles": [chunk.get("title") for chunk in research_chunks[:6]],
            }
        )

        system = (
            "You are planning a presentation narrative. Create a coherent thesis and select slides "
            "from the provided template candidates in narrative order."
        )

        try:
            payload = self._run_structured_request(
                system=system,
                user=user_payload,
                output_schema=schema,
                request_label="generate_outline",
            )
            thesis = str(payload.get("thesis", "")).strip()
            slides = payload.get("slides", [])
            if thesis and isinstance(slides, list) and slides:
                trimmed = []
                seen: set[int] = set()
                for row in slides:
                    idx = int(row.get("template_slide_index", -1))
                    if idx < 0 or idx in seen:
                        continue
                    seen.add(idx)
                    trimmed.append(row)
                    if len(trimmed) >= max(1, slide_count):
                        break
                if trimmed:
                    logger.info(
                        "openai_outline_parsed thesis=%s slides=%d preview=%s",
                        _preview_text(thesis),
                        len(trimmed),
                        [
                            {
                                "template_slide_index": int(row.get("template_slide_index", -1)),
                                "narrative_role": _preview_text(str(row.get("narrative_role", "")), 120),
                                "key_message": _preview_text(str(row.get("key_message", "")), 120),
                            }
                            for row in trimmed[:5]
                        ],
                    )
                    return {"thesis": thesis, "slides": trimmed}
            self.last_warnings.append("OpenAI outline payload was incomplete; fallback outline used.")
        except Exception as exc:
            self.last_warnings.append(f"OpenAI outline generation failed; fallback outline used ({exc}).")

        fallback_slides = []
        for idx, row in enumerate(all_slides[: max(1, slide_count)], start=1):
            fallback_slides.append(
                {
                    "template_slide_index": int(row.get("index", idx - 1)),
                    "narrative_role": f"Step {idx}: advance the argument with {row.get('archetype', 'general')} content.",
                    "key_message": f"Primary takeaway for step {idx}.",
                }
            )
        return {"thesis": prompt.strip(), "slides": fallback_slides}
