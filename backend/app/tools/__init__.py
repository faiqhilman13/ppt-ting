from app.tools.builtin import (
    QAContentCheckTool,
    QAVisualCheckTool,
    RenderThumbnailGridTool,
    ResearchRouteSourcesTool,
)
from app.tools.registry import register_many


def register_builtin_tools() -> None:
    register_many(
        [
            ResearchRouteSourcesTool(),
            QAContentCheckTool(),
            QAVisualCheckTool(),
            RenderThumbnailGridTool(),
        ]
    )

