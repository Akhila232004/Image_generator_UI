import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def analyze_colors(image: Image.Image) -> List[Dict[str, Any]]:
    image = image.convert("RGB")
    max_size = 240
    if max(image.size) > max_size:
        image.thumbnail((max_size, max_size))

    pixels = list(image.getdata())
    if not pixels:
        return []

    reduced_pixels = [
        (pixel[0] // 32 * 32, pixel[1] // 32 * 32, pixel[2] // 32 * 32)
        for pixel in pixels
    ]

    color_counts: Dict[Tuple[int, int, int], int] = {}
    for pixel in reduced_pixels:
        color_counts[pixel] = color_counts.get(pixel, 0) + 1

    sorted_colors = sorted(color_counts.items(), key=lambda item: item[1], reverse=True)
    total_pixels = len(reduced_pixels)
    return [
        {"hex": rgb_to_hex(color), "percentage": round((count / total_pixels) * 100, 2)}
        for color, count in sorted_colors[:8]
    ]


def calculate_brightness(image: Image.Image) -> float:
    histogram = image.convert("L").histogram()
    total = sum(histogram)
    if total == 0:
        return 0.0
    return round(sum(index * value for index, value in enumerate(histogram)) / total, 2)


def analyze_reference(image: Image.Image) -> Dict[str, Any]:
    width, height = image.size
    aspect_ratio = round(width / height, 4) if height else 0
    orientation = "landscape" if width > height else "portrait" if height > width else "square"
    return {
        "width": width,
        "height": height,
        "format": image.format or "unknown",
        "mode": image.mode,
        "canvas": {
            "width": width,
            "height": height,
            "aspect_ratio": aspect_ratio,
            "orientation": orientation,
        },
        "dominant_colors": analyze_colors(image),
        "average_brightness": calculate_brightness(image),
    }


def create_regions(width: int, height: int) -> List[Dict[str, Any]]:
    return [
        {"name": "header", "x": 0, "y": 0, "width": width, "height": round(height * 0.18), "order": 1},
        {"name": "main_visual", "x": 0, "y": round(height * 0.18), "width": width, "height": round(height * 0.42), "order": 2},
        {"name": "content", "x": 0, "y": round(height * 0.60), "width": width, "height": round(height * 0.28), "order": 3},
        {"name": "footer", "x": 0, "y": round(height * 0.88), "width": width, "height": height - round(height * 0.88), "order": 4},
    ]


def _clean_json_text(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    return value.strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_color(value: Any, fallback: str = "#FFFFFF") -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
        return text.upper()
    if re.fullmatch(r"#[0-9A-Fa-f]{3}", text):
        return "#" + "".join(ch * 2 for ch in text[1:]).upper()
    return fallback


def _normalize_role(value: Any, text: str) -> str:
    role = re.sub(r"[^a-z0-9_ -]", "", str(value or "").lower()).strip().replace(" ", "_")
    if role:
        return role
    low = text.lower()
    if any(token in low for token in ("nicat", "tinitiate", "group of education", "group of institutions")):
        return "logo"
    if "career" in low or "join" in low:
        return "cta"
    if "service" in low:
        return "section_heading"
    if any(token in low for token in ("phone", "www", ".com", "+91")) or re.search(r"\d{5,}", low):
        return "contact"
    return "body"


def _normalize_text_element(item: Dict[str, Any], index: int, width: int, height: int) -> Dict[str, Any] | None:
    text = str(item.get("text") or "").strip()
    if not text:
        return None

    bbox = item.get("bbox") or {}
    x = max(0, min(max(0, width - 1), _safe_int(item.get("x", bbox.get("x", 0)))))
    y = max(0, min(max(0, height - 1), _safe_int(item.get("y", bbox.get("y", 0)))))
    box_width = max(20, _safe_int(item.get("width", bbox.get("width", width - x)), max(20, width - x)))
    box_height = max(16, _safe_int(item.get("height", bbox.get("height", 60)), 60))
    box_width = min(box_width, max(20, width - x))
    box_height = min(box_height, max(16, height - y))

    font_size = max(10, _safe_int(item.get("font_size", 28), 28))
    role = _normalize_role(item.get("role"), text)
    group_id = str(item.get("group_id") or "").strip()
    if not group_id:
        group_id = f"group_{index + 1}"

    return {
        "id": str(item.get("id") or f"text_{index + 1}"),
        "group_id": group_id,
        "role": role,
        "text": text,
        "x": x,
        "y": y,
        "width": box_width,
        "height": box_height,
        "font_size": font_size,
        "font_family": str(item.get("font_family") or "Arial").strip() or "Arial",
        "font_weight": str(item.get("font_weight") or "bold").strip().lower(),
        "alignment": str(item.get("alignment") or "left").strip().lower(),
        "color": _normalize_color(item.get("color"), "#FFFFFF"),
        "uppercase": bool(item.get("uppercase", text == text.upper())),
        "line_spacing": max(0.8, min(2.0, _safe_float(item.get("line_spacing", 1.0), 1.0))),
        "confidence": round(max(0.0, min(1.0, _safe_float(item.get("confidence", 0.75), 0.75))), 3),
    }


def _union_bbox(elements: List[Dict[str, Any]]) -> Dict[str, int]:
    x1 = min(int(e["x"]) for e in elements)
    y1 = min(int(e["y"]) for e in elements)
    x2 = max(int(e["x"]) + int(e["width"]) for e in elements)
    y2 = max(int(e["y"]) + int(e["height"]) for e in elements)
    return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}


def _build_text_groups(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create stable groups used for multi-line replacements.

    Gemini is asked for group_id, but this post-processing also catches cases
    where the model returns one ID per line. Lines with the same role/style and
    close vertical spacing are grouped. This is particularly important for
    titles such as DIGITAL / MARKETING and two-line logos.
    """
    if not elements:
        return []

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for element in elements:
        groups.setdefault(str(element.get("group_id") or element["id"]), []).append(element)

    # Merge likely title/logo lines that Gemini separated.
    changed = True
    while changed:
        changed = False
        keys = list(groups)
        for i, key_a in enumerate(keys):
            if key_a not in groups:
                continue
            a = groups[key_a]
            if len(a) == 0:
                continue
            for key_b in keys[i + 1:]:
                if key_b not in groups:
                    continue
                b = groups[key_b]
                if len(b) == 0:
                    continue
                a0, b0 = a[0], b[0]
                same_role = a0.get("role") == b0.get("role") or a0.get("role") in {"body", "headline", "title"} or b0.get("role") in {"body", "headline", "title"}
                close_x = abs(int(a0["x"]) - int(b0["x"])) <= max(12, int(min(a0["width"], b0["width"]) * 0.08))
                a_bottom = max(int(e["y"]) + int(e["height"]) for e in a)
                b_top = min(int(e["y"]) for e in b)
                b_bottom = max(int(e["y"]) + int(e["height"]) for e in b)
                a_top = min(int(e["y"]) for e in a)
                vertical_gap = min(abs(b_top - a_bottom), abs(a_top - b_bottom))
                font_close = abs(int(a0["font_size"]) - int(b0["font_size"])) <= max(8, int(max(a0["font_size"], b0["font_size"]) * 0.22))
                if same_role and close_x and font_close and vertical_gap <= max(24, int(max(a0["height"], b0["height"]) * 0.75)):
                    groups[key_a].extend(groups.pop(key_b))
                    changed = True
                    break
            if changed:
                break

    result: List[Dict[str, Any]] = []
    for key, items in groups.items():
        items.sort(key=lambda e: (int(e["y"]), int(e["x"])))
        bbox = _union_bbox(items)
        source_text = " ".join(str(e["text"]).strip() for e in items if str(e["text"]).strip())
        role = str(items[0].get("role") or "body")
        if role == "body" and len(items) > 1:
            # Two adjacent large uppercase lines are usually a headline/title.
            if all(str(e["text"]).strip().isupper() for e in items) and max(int(e["font_size"]) for e in items) >= 30:
                role = "title"
        result.append({
            "id": key,
            "role": role,
            "text": source_text,
            "element_ids": [str(e["id"]) for e in items],
            "bbox": bbox,
            "line_count": len(items),
            "lines": [
                {
                    "element_id": str(e["id"]),
                    "text": e["text"],
                    "x": e["x"],
                    "y": e["y"],
                    "width": e["width"],
                    "height": e["height"],
                    "font_size": e["font_size"],
                    "font_family": e["font_family"],
                    "font_weight": e["font_weight"],
                    "alignment": e["alignment"],
                    "color": e["color"],
                    "uppercase": e["uppercase"],
                    "line_spacing": e["line_spacing"],
                }
                for e in items
            ],
        })
    result.sort(key=lambda g: (g["bbox"]["y"], g["bbox"]["x"]))
    return result


def _canonicalize_text_groups(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize important logical groups after Gemini OCR.

    Gemini sometimes returns visually related lines with different group IDs.
    For reference-preserving editing, deterministic grouping is essential.
    In particular, a two-line title such as DIGITAL / MARKETING and a two-line
    brand lockup such as NiCAT / Group Of Education must behave as one logical
    editable object.
    """
    if not elements:
        return elements

    # Canonicalize the logo lockup.
    logo_tokens = {"nicat", "group of education", "group of institutions"}
    logo_items = [
        e for e in elements
        if any(token in str(e.get("text", "")).lower() for token in logo_tokens)
        or str(e.get("role", "")).lower() == "logo"
    ]
    if logo_items:
        for e in logo_items:
            e["group_id"] = "logo"
            e["role"] = "logo"

    # Canonicalize the two-line DIGITAL MARKETING title when those words are
    # detected. This is deliberately based on actual OCR text, not coordinates
    # or hard-coded positions.
    title_items = [
        e for e in elements
        if str(e.get("text", "")).strip().lower() in {"digital", "marketing", "digital marketing"}
    ]
    if len(title_items) >= 2:
        for e in title_items:
            e["group_id"] = "main_title"
            e["role"] = "title"

    # If Gemini returned the complete phrase as one element, still give it a
    # stable title group ID.
    if any(str(e.get("text", "")).strip().lower() == "digital marketing" for e in title_items):
        for e in title_items:
            e["group_id"] = "main_title"
            e["role"] = "title"

    return elements

def extract_text_elements_with_gemini(image: Image.Image) -> List[Dict[str, Any]]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or genai is None or types is None:
        return []

    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"
    width, height = image.size
    prompt = f"""
You are building an editable template from a poster image.

Canvas: {width} x {height} pixels.

Your job is VISUAL ANALYSIS ONLY. Do not redesign the poster and do not create
an alternative design.

Identify every visible text region that can reasonably be replaced while
keeping the poster's visual design unchanged.

IMPORTANT:
1. Include ordinary text AND text inside a logo/brand lockup if it is visibly
   rendered as text. For a logo, do NOT include the surrounding white/colored
   shape as a text box; only locate the actual letters. The background/logo
   container must remain untouched.
2. Multi-line phrases that belong together MUST share the same group_id.
   Example: DIGITAL on one line and MARKETING on the next line should share a
   group_id such as main_title. A two-line logo such as a brand name plus a
   subtitle should share one logo group.
3. Assign a semantic role such as logo, headline, title, subtitle, cta,
   section_heading, service_item, contact, body, or other.
4. For each line, give a tight bounding box around the visible letters only.
   Use ORIGINAL image pixels, not normalized 0..100 coordinates.
5. Preserve exact visible spelling and capitalization.
6. Do not omit small but readable text if it is a meaningful content field.
7. Do not include decorative dots, patterns, icons, or numbers that are part
   of a graphic unless they are actual editable text.
8. If several service names are listed separately, create one text element per
   service line, but keep all service lines in the same group_id.
9. If a heading and its list are separate visual structures, use different
   group_id values.

Return ONLY JSON:
{{
  "text_elements": [
    {{
      "id": "stable_line_id",
      "group_id": "stable_group_id",
      "role": "title",
      "text": "exact visible text",
      "x": 0,
      "y": 0,
      "width": 100,
      "height": 40,
      "font_size": 40,
      "font_family": "Arial",
      "font_weight": "bold",
      "alignment": "left",
      "color": "#FFFFFF",
      "uppercase": true,
      "line_spacing": 1.0,
      "confidence": 0.95
    }}
  ]
}}
""".strip()

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=[prompt, image.convert("RGB")],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        payload = json.loads(_clean_json_text(getattr(response, "text", "")))
        raw_elements = payload.get("text_elements", [])
        if not isinstance(raw_elements, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for index, item in enumerate(raw_elements[:100]):
            if not isinstance(item, dict):
                continue
            element = _normalize_text_element(item, index, width, height)
            if element:
                normalized.append(element)

        return _canonicalize_text_groups(normalized)
    except Exception as exc:
        print("Gemini text-region extraction failed:", repr(exc))
        return []


def build_template(image_analysis: Dict[str, Any], text_elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    canvas = image_analysis["canvas"]
    width = canvas["width"]
    height = canvas["height"]
    return {
        "template_id": str(uuid.uuid4()),
        "version": "4.0",
        "name": "Generated Reference Template",
        "canvas": {
            "width": width,
            "height": height,
            "orientation": canvas["orientation"],
            "aspect_ratio": canvas["aspect_ratio"],
        },
        "layout": {
            "type": "reference-based",
            "alignment": "reference",
            "preserve_reference_structure": True,
            "preserve_reference_composition": True,
            "editable_text_only": True,
        },
        "regions": create_regions(width, height),
        "text_elements": text_elements,
        "text_groups": _build_text_groups(text_elements),
        "style": {
            "keywords": ["reference-preserved", "professional", "editable-text"],
            "dominant_colors": image_analysis["dominant_colors"],
            "average_brightness": image_analysis["average_brightness"],
            "preserve_reference_colors": True,
        },
        "content": {
            "keywords": ["editable-text", "content-replacement"],
            "source_prompt": "",
        },
        "reference_analysis": image_analysis,
    }


def save_template(template: Dict[str, Any]) -> str:
    filename = f'{template["template_id"]}.json'
    file_path = TEMPLATES_DIR / filename
    file_path.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(Path("templates") / filename)


def generate_template(reference_path: Path, prompt: str = "") -> Dict[str, Any]:
    reference_path = Path(reference_path)
    if not reference_path.exists():
        raise FileNotFoundError(f"Reference image was not found: {reference_path}")

    with Image.open(reference_path) as source:
        if source.format == "GIF" or reference_path.suffix.lower() == ".gif":
            source.seek(0)
        image = source.convert("RGB")
        image_analysis = analyze_reference(image)
        text_elements = extract_text_elements_with_gemini(image)

    if not text_elements:
        raise RuntimeError(
            "Gemini could not detect editable text regions in the reference image. "
            "Check the Gemini API configuration and regenerate the template."
        )

    template = build_template(image_analysis, text_elements)
    template_file = save_template(template)

    return {
        "template_id": template["template_id"],
        "template_name": template["name"],
        "reference": image_analysis,
        "prompt": {
            "original_prompt": prompt or "",
            "layout": {
                "type": "reference-based",
                "alignment": "reference",
                "sections": ["header", "main_visual", "content", "footer"],
            },
            "style_keywords": template["style"]["keywords"],
            "content_keywords": template["content"]["keywords"],
        },
        "template": template,
        "template_file": template_file,
    }
