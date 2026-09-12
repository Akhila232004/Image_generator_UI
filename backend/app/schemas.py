from pydantic import BaseModel


class Canvas(BaseModel):
    width: int
    height: int
    orientation: str
    aspect_ratio: float


class ColorInfo(BaseModel):
    hex: str
    percentage: float


class VisualAnalysis(BaseModel):
    width: int
    height: int
    format: str
    mode: str
    canvas: Canvas
    dominant_colors: list[ColorInfo]
    average_brightness: float


class LayoutInfo(BaseModel):
    type: str
    alignment: str
    preserve_reference_structure: bool


class PromptAnalysis(BaseModel):
    original_prompt: str
    layout: LayoutInfo
    style_keywords: list[str]
    content_keywords: list[str]


class GeneratedTemplate(BaseModel):
    template_id: str
    version: str
    name: str
    canvas: Canvas
    layout: LayoutInfo
    regions: list[dict]
    style: dict
    content: dict
    reference_analysis: VisualAnalysis


class TemplateResponse(BaseModel):
    template_id: str
    template_name: str
    reference: VisualAnalysis
    prompt: PromptAnalysis
    template: GeneratedTemplate
    template_file: str


class ImageTagResponse(BaseModel):
    filename: str
    tag: str


class ImageTagAllResponse(BaseModel):
    tags: dict[str, str]