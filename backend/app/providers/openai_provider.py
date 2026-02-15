import json

from openai import OpenAI

from app.providers.base import BaseLLMProvider, SlideContent
from app.services.prompt_templates import build_generation_prompts, build_revision_prompts


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self, api_key: str):
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

        return OpenAIProvider._fallback(template_manifest, fallback_count, text)

    def generate_slides(self, prompt, research_chunks, template_manifest, slide_count, extra_instructions=None):
        selected = (template_manifest.get("slides") or [])[:slide_count]
        system, user = build_generation_prompts(
            prompt=prompt,
            extra_instructions=extra_instructions,
            selected_slides=selected,
            research_chunks=research_chunks,
        )

        response = self.client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.35,
        )
        text = response.output_text or ""
        return self._parse(text, template_manifest, len(selected))

    def revise_slides(self, prompt, existing_slides, research_chunks, template_manifest):
        system, user = build_revision_prompts(
            revision_prompt=prompt,
            existing_slides=existing_slides,
            template_manifest=template_manifest,
            research_chunks=research_chunks,
        )

        response = self.client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
        )
        text = response.output_text or ""
        return self._parse(text, template_manifest, len(existing_slides))
