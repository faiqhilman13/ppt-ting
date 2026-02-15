import json
import logging
import time
from time import perf_counter

from anthropic import Anthropic

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


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str):
        super().__init__()
        self.client = Anthropic(api_key=api_key)

    def _messages_create_with_retry(
        self,
        *,
        request_label: str,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
        retries: int = 2,
    ):
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            started = perf_counter()
            logger.info(
                "anthropic_request_start label=%s model=%s attempt=%d/%d input_chars=%d system_preview=%s user_preview=%s",
                request_label,
                settings.anthropic_model,
                attempt + 1,
                retries + 1,
                len(system) + len(user),
                _preview_text(system, 140),
                _preview_text(user, 220),
            )
            try:
                response = self.client.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                text = "".join(block.text for block in response.content if hasattr(block, "text"))
                logger.info(
                    "anthropic_request_done label=%s duration_sec=%.2f output_chars=%d output_preview=%s",
                    request_label,
                    perf_counter() - started,
                    len(text),
                    _preview_text(text, 220),
                )
                return response
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "anthropic_request_error label=%s attempt=%d/%d duration_sec=%.2f reason=%s",
                    request_label,
                    attempt + 1,
                    retries + 1,
                    perf_counter() - started,
                    exc,
                )
                if attempt < retries:
                    time.sleep(0.6 * (2**attempt))

        if last_error:
            raise last_error
        raise RuntimeError("Anthropic request failed with unknown error")

    @staticmethod
    def _fallback(template_manifest: dict, fallback_count: int, text: str) -> list[SlideContent]:
        selected = (template_manifest.get("slides") or [])[:fallback_count]
        fallback: list[SlideContent] = []
        for idx, slide in enumerate(selected):
            slots = {
                slot: (text[:700] if i == 0 else f"Generated content {idx + 1}")
                for i, slot in enumerate(slide.get("slots", []))
            }
            fallback.append(SlideContent(template_slide_index=slide.get("index", idx), slots=slots))
        return fallback

    @staticmethod
    def _parse(text: str, template_manifest: dict, fallback_count: int) -> tuple[list[SlideContent], bool]:
        try:
            payload = json.loads(text)
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

        return AnthropicProvider._fallback(template_manifest, fallback_count, text), True

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
        try:
            msg = self._messages_create_with_retry(
                request_label="generate_slides",
                system=system,
                user=user,
                max_tokens=settings.anthropic_max_tokens,
                temperature=0.35,
            )
            text = "".join(block.text for block in msg.content if hasattr(block, "text"))
            parsed, used_fallback = self._parse(text, template_manifest, len(selected))
            if used_fallback:
                self.last_warnings.append("Anthropic returned invalid JSON payload; fallback content was used.")
            logger.info(
                "anthropic_generate_parsed slides=%d fallback=%s preview=%s",
                len(parsed),
                used_fallback,
                _slides_preview(parsed),
            )
            return parsed
        except Exception as exc:
            self.last_warnings.append(f"Anthropic request failed; fallback content was used ({exc}).")
            return self._fallback(template_manifest, len(selected), f"Anthropic fallback: {exc}")

    def revise_slides(self, prompt, existing_slides, research_chunks, template_manifest):
        self.reset_warnings()
        system, user = build_revision_prompts(
            revision_prompt=prompt,
            existing_slides=existing_slides,
            template_manifest=template_manifest,
            research_chunks=research_chunks,
        )
        try:
            msg = self._messages_create_with_retry(
                request_label="revise_slides",
                system=system,
                user=user,
                max_tokens=settings.anthropic_max_tokens,
                temperature=0.3,
            )
            text = "".join(block.text for block in msg.content if hasattr(block, "text"))
            parsed, used_fallback = self._parse(text, template_manifest, len(existing_slides))
            if used_fallback:
                self.last_warnings.append("Anthropic returned invalid JSON payload during revision; fallback content was used.")
            logger.info(
                "anthropic_revise_parsed slides=%d fallback=%s preview=%s",
                len(parsed),
                used_fallback,
                _slides_preview(parsed),
            )
            return parsed
        except Exception as exc:
            self.last_warnings.append(f"Anthropic revision request failed; fallback content was used ({exc}).")
            return self._fallback(template_manifest, len(existing_slides), f"Anthropic fallback: {exc}")

    def generate_text(self, *, system_prompt: str, user_prompt: str, max_tokens: int = 180) -> str:
        try:
            msg = self._messages_create_with_retry(
                request_label="generate_text",
                system=system_prompt,
                user=user_prompt,
                max_tokens=max_tokens,
                temperature=0.2,
            )
            return "".join(block.text for block in msg.content if hasattr(block, "text")).strip()
        except Exception as exc:
            self.last_warnings.append(f"Anthropic text generation failed ({exc}).")
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
        candidates = []
        for row in all_slides:
            candidates.append(
                {
                    "template_slide_index": row.get("index"),
                    "name": row.get("name"),
                    "archetype": row.get("archetype"),
                    "slots": row.get("slots", []),
                }
            )

        system = (
            "Return JSON only with keys: thesis (string), slides (array). "
            "Each slide object must include template_slide_index, narrative_role, key_message. "
            "Only use provided template_slide_index values."
        )
        user = json.dumps(
            {
                "prompt": prompt,
                "slide_count": slide_count,
                "candidate_slides": candidates,
                "research_titles": [chunk.get("title") for chunk in research_chunks[:6]],
            }
        )

        try:
            msg = self._messages_create_with_retry(
                request_label="generate_outline",
                system=system,
                user=user,
                max_tokens=min(settings.anthropic_max_tokens, 2000),
                temperature=0.25,
            )
            text = "".join(block.text for block in msg.content if hasattr(block, "text"))
            payload = json.loads(text)
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
                        "anthropic_outline_parsed thesis=%s slides=%d preview=%s",
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
            self.last_warnings.append("Anthropic outline payload was incomplete; fallback outline used.")
        except Exception as exc:
            self.last_warnings.append(f"Anthropic outline generation failed; fallback outline used ({exc}).")

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
