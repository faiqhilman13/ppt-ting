import json

from anthropic import Anthropic

from app.providers.base import BaseLLMProvider, SlideContent
from app.services.prompt_templates import build_generation_prompts, build_revision_prompts


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)

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
    def _parse(text: str, template_manifest: dict, fallback_count: int) -> list[SlideContent]:
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
                return parsed
        except Exception:
            pass

        return AnthropicProvider._fallback(template_manifest, fallback_count, text)

    def generate_slides(self, prompt, research_chunks, template_manifest, slide_count, extra_instructions=None):
        selected = (template_manifest.get("slides") or [])[:slide_count]
        system, user = build_generation_prompts(
            prompt=prompt,
            extra_instructions=extra_instructions,
            selected_slides=selected,
            research_chunks=research_chunks,
        )
        msg = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=3500,
            temperature=0.35,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in msg.content if hasattr(block, "text"))
        return self._parse(text, template_manifest, len(selected))

    def revise_slides(self, prompt, existing_slides, research_chunks, template_manifest):
        system, user = build_revision_prompts(
            revision_prompt=prompt,
            existing_slides=existing_slides,
            template_manifest=template_manifest,
            research_chunks=research_chunks,
        )
        msg = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=3500,
            temperature=0.3,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in msg.content if hasattr(block, "text"))
        return self._parse(text, template_manifest, len(existing_slides))
