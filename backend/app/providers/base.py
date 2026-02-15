from dataclasses import dataclass


@dataclass
class SlideContent:
    template_slide_index: int
    slots: dict[str, str]


class BaseLLMProvider:
    name = "base"

    def generate_slides(
        self,
        prompt: str,
        research_chunks: list[dict],
        template_manifest: dict,
        slide_count: int,
        extra_instructions: str | None = None,
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
