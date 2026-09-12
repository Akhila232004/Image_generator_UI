import json
import uuid

from pathlib import Path

from typing import (
    Dict,
    List,
    Tuple,
)

from PIL import Image


BASE_DIR = (
    Path(__file__)
    .resolve()
    .parents[2]
)

TEMPLATES_DIR = (
    BASE_DIR /
    "templates"
)

TEMPLATES_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def rgb_to_hex(
    rgb: Tuple[int, int, int],
) -> str:

    return "#{:02X}{:02X}{:02X}".format(
        *rgb
    )


def analyze_colors(
    image: Image.Image,
) -> List[Dict]:

    image = image.convert(
        "RGB"
    )

    max_size = 200

    if max(image.size) > max_size:

        image.thumbnail(
            (
                max_size,
                max_size,
            )
        )

    pixels = list(
        image.getdata()
    )

    if not pixels:
        return []

    reduced_pixels = [
        (
            pixel[0] // 32 * 32,
            pixel[1] // 32 * 32,
            pixel[2] // 32 * 32,
        )
        for pixel in pixels
    ]

    color_counts: Dict[
        Tuple[int, int, int],
        int,
    ] = {}

    for pixel in reduced_pixels:

        color_counts[pixel] = (
            color_counts.get(
                pixel,
                0,
            )
            + 1
        )

    sorted_colors = sorted(
        color_counts.items(),
        key=lambda item:
            item[1],
        reverse=True,
    )

    total_pixels = len(
        reduced_pixels
    )

    colors = []

    for color, count in (
        sorted_colors[:5]
    ):

        percentage = round(
            (
                count /
                total_pixels
            )
            * 100,
            2,
        )

        colors.append({
            "hex":
                rgb_to_hex(
                    color
                ),
            "percentage":
                percentage,
        })

    return colors


def calculate_brightness(
    image: Image.Image,
) -> float:

    image = image.convert(
        "L"
    )

    histogram = (
        image.histogram()
    )

    total = sum(
        histogram
    )

    if total == 0:
        return 0.0

    weighted_sum = sum(
        index * value
        for index, value
        in enumerate(histogram)
    )

    return round(
        weighted_sum /
        total,
        2,
    )


def analyze_reference(
    image: Image.Image,
) -> Dict:

    width, height = (
        image.size
    )

    aspect_ratio = (
        round(
            width / height,
            4,
        )
        if height
        else 0
    )

    if width > height:
        orientation = "landscape"

    elif height > width:
        orientation = "portrait"

    else:
        orientation = "square"

    return {
        "width":
            width,

        "height":
            height,

        "format":
            image.format or "unknown",

        "mode":
            image.mode,

        "canvas": {
            "width":
                width,

            "height":
                height,

            "aspect_ratio":
                aspect_ratio,

            "orientation":
                orientation,
        },

        "dominant_colors":
            analyze_colors(
                image
            ),

        "average_brightness":
            calculate_brightness(
                image
            ),
    }


def contains_any(
    text: str,
    keywords: List[str],
) -> bool:

    return any(
        keyword in text
        for keyword in keywords
    )


def detect_layout(
    prompt: str,
) -> Dict:

    text = prompt.lower()

    if contains_any(
        text,
        [
            "poster",
            "flyer",
            "banner",
            "social media",
            "training",
            "announcement",
        ],
    ):

        layout_type = "poster"

    elif contains_any(
        text,
        [
            "presentation",
            "slide",
            "ppt",
            "powerpoint",
        ],
    ):

        layout_type = "presentation"

    elif contains_any(
        text,
        [
            "card",
            "learning card",
            "content card",
        ],
    ):

        layout_type = "card"

    else:

        layout_type = (
            "reference-based"
        )


    sections = []


    if contains_any(
        text,
        [
            "title",
            "heading",
            "header",
        ],
    ):

        sections.append(
            "header"
        )


    if contains_any(
        text,
        [
            "image",
            "illustration",
            "visual",
            "photo",
            "graphic",
        ],
    ):

        sections.append(
            "main_visual"
        )


    if contains_any(
        text,
        [
            "point",
            "points",
            "content",
            "description",
            "objective",
            "objectives",
            "bullet",
            "bullets",
        ],
    ):

        sections.append(
            "content"
        )


    if contains_any(
        text,
        [
            "footer",
            "bottom",
            "logo",
            "contact",
        ],
    ):

        sections.append(
            "footer"
        )


    if not sections:

        sections = [
            "header",
            "main_visual",
            "content",
            "footer",
        ]


    if contains_any(
        text,
        [
            "center",
            "centered",
            "centre",
            "centred",
        ],
    ):

        alignment = "center"

    elif contains_any(
        text,
        [
            "left",
            "left aligned",
        ],
    ):

        alignment = "left"

    elif contains_any(
        text,
        [
            "right",
            "right aligned",
        ],
    ):

        alignment = "right"

    else:

        alignment = "reference"


    return {
        "type":
            layout_type,

        "alignment":
            alignment,

        "sections":
            sections,
    }


def extract_style_keywords(
    prompt: str,
) -> List[str]:

    text = prompt.lower()

    possible_keywords = [
        "professional",
        "modern",
        "minimal",
        "minimalist",
        "elegant",
        "clean",
        "corporate",
        "creative",
        "bold",
        "simple",
        "premium",
        "technical",
        "educational",
        "colorful",
        "dark",
        "light",
        "formal",
    ]

    return [
        keyword
        for keyword
        in possible_keywords
        if keyword in text
    ]


def extract_content_keywords(
    prompt: str,
) -> List[str]:

    text = prompt.lower()

    possible_keywords = [
        "title",
        "heading",
        "subtitle",
        "description",
        "content",
        "objective",
        "objectives",
        "point",
        "points",
        "bullet",
        "bullets",
        "logo",
        "image",
        "illustration",
        "visual",
        "footer",
        "contact",
    ]

    return [
        keyword
        for keyword
        in possible_keywords
        if keyword in text
    ]


def analyze_prompt(
    prompt: str,
) -> Dict:

    return {
        "original_prompt":
            prompt,

        "layout":
            detect_layout(
                prompt
            ),

        "style_keywords":
            extract_style_keywords(
                prompt
            ),

        "content_keywords":
            extract_content_keywords(
                prompt
            ),
    }


def create_regions(
    width: int,
    height: int,
    sections: List[str],
) -> List[Dict]:

    regions = []

    if not sections:
        return regions

    weights = {
        "header": 0.18,
        "main_visual": 0.42,
        "content": 0.28,
        "footer": 0.12,
    }

    total_weight = sum(
        weights.get(
            section,
            0.25,
        )
        for section in sections
    )

    y = 0

    for index, section in enumerate(
        sections
    ):

        weight = weights.get(
            section,
            0.25,
        )

        region_height = round(
            height *
            (
                weight /
                total_weight
            )
        )

        if (
            index ==
            len(sections) - 1
        ):

            region_height = (
                height - y
            )

        regions.append({
            "name":
                section,

            "x":
                0,

            "y":
                y,

            "width":
                width,

            "height":
                region_height,

            "order":
                index + 1,
        })

        y += region_height

    return regions


def build_template(
    image_analysis: Dict,
    prompt_analysis: Dict,
) -> Dict:

    canvas = (
        image_analysis["canvas"]
    )

    width = canvas[
        "width"
    ]

    height = canvas[
        "height"
    ]

    sections = (
        prompt_analysis
        ["layout"]
        ["sections"]
    )

    template_id = str(
        uuid.uuid4()
    )

    return {
        "template_id":
            template_id,

        "version":
            "1.0",

        "name":
            "Generated Reference Template",

        "canvas": {
            "width":
                width,

            "height":
                height,

            "orientation":
                canvas[
                    "orientation"
                ],

            "aspect_ratio":
                canvas[
                    "aspect_ratio"
                ],
        },

        "layout": {
            "type":
                prompt_analysis
                ["layout"]
                ["type"],

            "alignment":
                prompt_analysis
                ["layout"]
                ["alignment"],

            "preserve_reference_structure":
                True,
        },

        "regions":
            create_regions(
                width,
                height,
                sections,
            ),

        "style": {
            "keywords":
                prompt_analysis
                ["style_keywords"],

            "dominant_colors":
                image_analysis
                ["dominant_colors"],

            "average_brightness":
                image_analysis
                ["average_brightness"],

            "preserve_reference_colors":
                True,
        },

        "content": {
            "keywords":
                prompt_analysis
                ["content_keywords"],

            "source_prompt":
                prompt_analysis
                ["original_prompt"],
        },

        "reference_analysis":
            image_analysis,
    }


def save_template(
    template: Dict,
) -> str:

    filename = (
        f'{template["template_id"]}.json'
    )

    file_path = (
        TEMPLATES_DIR /
        filename
    )

    with open(
        file_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            template,
            file,
            indent=2,
        )

    return str(
        Path("templates") /
        filename
    )


def generate_template(
    reference_path: Path,
    prompt: str = "",
):
    """
    Generate a reusable template
    directly from a reference image.

    The reference is the source of
    the canvas, colors and visual
    structure.

    The prompt is optional and is
    intentionally kept separate so
    that the template can be created
    immediately when a reference is
    added.
    """

    if not reference_path.exists():

        raise FileNotFoundError(
            f"Reference image not found: "
            f"{reference_path}"
        )

    with Image.open(
        reference_path
    ) as image:

        image_analysis = (
            analyze_reference(
                image
            )
        )

    prompt_analysis = (
        analyze_prompt(
            prompt or ""
        )
    )


    # With no prompt, use a reference-preserving layout rather than
# inventing a content-specific layout. This keeps the template
# faithful to the supplied reference and leaves content decisions
# to the separate prompt/Canva stage.

    if not prompt.strip():

        prompt_analysis = {
            "original_prompt":
                "",

            "layout": {
                "type":
                    "reference-based",

                "alignment":
                    "reference",

                "sections": [
                    "header",
                    "main_visual",
                    "content",
                    "footer",
                ],
            },

            "style_keywords":
                [],

            "content_keywords":
                [],
        }


    template = (
        build_template(
            image_analysis,
            prompt_analysis,
        )
    )

    template["source"] = {
        "type":
            "reference-image",

        "filename":
            reference_path.name,
    }

    template_file = (
        save_template(
            template
        )
    )

    return {
        "template_id":
            template["template_id"],

        "template_name":
            template["name"],

        "reference":
            image_analysis,

        "prompt":
            prompt_analysis,

        "template":
            template,

        "template_file":
            template_file,
    }