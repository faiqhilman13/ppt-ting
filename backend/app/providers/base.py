from dataclasses import dataclass


@dataclass
class SlideContent:
    template_slide_index: int
    slots: dict[str, str]


class BaseLLMProvider:
    name = "base"
    last_warnings: list[str]

    def __init__(self):
        self.last_warnings = []

    def reset_warnings(self) -> None:
        self.last_warnings = []

    def generate_slides(
        self,
        prompt: str,
        research_chunks: list[dict],
        template_manifest: dict,
        slide_count: int,
        extra_instructions: str | None = None,
        deck_thesis: str | None = None,
    ) -> list[SlideContent]:
        raise NotImplementedError

    def revise_slides(
        self,
        prompt: str,
        existing_slides: list[dict],
        research_chunks: list[dict],
        template_manifest: dict,
    ) -> list[SlideContent]:
        raise NotImplementedError

    def generate_text(self, *, system_prompt: str, user_prompt: str, max_tokens: int = 180) -> str:
        return user_prompt.strip()

    def generate_outline(
        self,
        *,
        prompt: str,
        template_manifest: dict,
        slide_count: int,
        research_chunks: list[dict],
    ) -> dict:
        slides = (template_manifest.get("slides") or [])[:slide_count]
        return {
            "thesis": prompt.strip(),
            "slides": [
                {
                    "template_slide_index": int(row.get("index", idx)),
                    "narrative_role": f"Develop slide {idx + 1} of the narrative.",
                    "key_message": f"Core point for slide {idx + 1}",
                }
                for idx, row in enumerate(slides)
            ],
        }
