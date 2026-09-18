import io
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


WINDOWS_FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"


def _clean_json_text(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
        value = re.sub(r"\s*```$", "", value)
    return value.strip()


def _norm_text(value: str) -> str:
    value = str(value or "").replace("–", "-").replace("—", "-")
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def _find_font(font_family: str, font_weight: str) -> str | None:
    family = re.sub(r"[^a-z0-9]", "", (font_family or "Arial").lower())
    weight = (font_weight or "normal").lower()
    bold = "bold" in weight or "heavy" in weight or "black" in weight or "semibold" in weight

    candidates: List[str] = []
    if family in {"arial", "sansserif", "helvetica"}:
        candidates += ["arialbd.ttf" if bold else "arial.ttf"]
    elif family == "calibri":
        candidates += ["calibrib.ttf" if bold else "calibri.ttf"]
    elif family == "verdana":
        candidates += ["verdanab.ttf" if bold else "verdana.ttf"]
    elif family == "georgia":
        candidates += ["georgiab.ttf" if bold else "georgia.ttf"]
    elif family in {"timesnewroman", "times"}:
        candidates += ["timesbd.ttf" if bold else "times.ttf"]

    candidates += ["arialbd.ttf" if bold else "arial.ttf", "calibrib.ttf" if bold else "calibri.ttf"]
    for candidate in candidates:
        path = WINDOWS_FONT_DIR / candidate
        if path.exists():
            return str(path)
    return None


def _font(size: int, family: str, weight: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _find_font(family, weight)
    if path:
        try:
            return ImageFont.truetype(path, max(8, int(size)))
        except Exception:
            pass
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text or " ", font=font)
    return max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_size(draw, candidate, font)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_single_line_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    element: Dict[str, Any],
    max_size: int | None = None,
    min_size: int = 8,
) -> ImageFont.ImageFont:
    box_width = max(10, int(element.get("width", 100)))
    box_height = max(10, int(element.get("height", 40)))
    requested_size = max(8, int(element.get("font_size", 28)))
    if max_size is not None:
        requested_size = min(requested_size, max_size)

    family = str(element.get("font_family", "Arial"))
    weight = str(element.get("font_weight", "bold"))
    size = requested_size
    while size >= min_size:
        font = _font(size, family, weight)
        width, height = _text_size(draw, text, font)
        if width <= box_width and height <= box_height:
            return font
        size -= 1
    return _font(min_size, family, weight)


def _fit_multiline_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    element: Dict[str, Any],
) -> Tuple[ImageFont.ImageFont, List[str], int]:
    box_width = max(20, int(element.get("width", 100)))
    box_height = max(16, int(element.get("height", 40)))
    requested_size = max(8, int(element.get("font_size", 28)))
    family = str(element.get("font_family", "Arial"))
    weight = str(element.get("font_weight", "bold"))
    spacing = float(element.get("line_spacing", 1.0))

    for size in range(requested_size, 7, -1):
        font = _font(size, family, weight)
        lines = _wrap_text(draw, text, font, box_width)
        heights = [_text_size(draw, line, font)[1] for line in lines]
        total = int(sum(heights) * spacing)
        if total <= box_height and all(_text_size(draw, line, font)[0] <= box_width for line in lines):
            return font, lines, total

    font = _font(8, family, weight)
    lines = _wrap_text(draw, text, font, box_width)
    return font, lines, max(1, sum(_text_size(draw, line, font)[1] for line in lines))


def _element_catalog(template: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "id": e.get("id"),
            "group_id": e.get("group_id"),
            "role": e.get("role"),
            "text": e.get("text"),
            "x": e.get("x"),
            "y": e.get("y"),
            "width": e.get("width"),
            "height": e.get("height"),
        }
        for e in template.get("text_elements") or []
    ]


def _group_catalog(template: Dict[str, Any]) -> List[Dict[str, Any]]:
    groups = template.get("text_groups") or []
    if groups:
        return groups

    # Backward compatibility with old templates that have no text_groups.
    fallback = []
    for e in template.get("text_elements") or []:
        fallback.append({
            "id": e.get("id"),
            "role": e.get("role", "body"),
            "text": e.get("text"),
            "element_ids": [e.get("id")],
            "bbox": {
                "x": e.get("x", 0),
                "y": e.get("y", 0),
                "width": e.get("width", 100),
                "height": e.get("height", 40),
            },
            "line_count": 1,
            "lines": [e],
        })
    return fallback


def _find_group_for_exact_text(template: Dict[str, Any], source_text: str) -> Dict[str, Any] | None:
    """Find the existing logical group represented by source_text.

    The previous implementation relied on a single exact group string. Gemini
    can legitimately return a multi-line title as separate groups, so an exact
    lookup could fail for a phrase such as ``DIGITAL MARKETING``. We therefore
    compare both group text and the concatenation of nearby text elements.
    """
    wanted = _norm_text(source_text)
    if not wanted:
        return None

    groups = _group_catalog(template)

    # 1. Exact logical-group match.
    for group in groups:
        if _norm_text(group.get("text", "")) == wanted:
            return group

    # 2. Exact match after collapsing line breaks/punctuation.
    wanted_compact = re.sub(r"[^a-z0-9]+", "", wanted)
    for group in groups:
        group_compact = re.sub(r"[^a-z0-9]+", "", _norm_text(group.get("text", "")))
        if group_compact and group_compact == wanted_compact:
            return group

    # 3. Match the phrase across individual text elements. This is important
    # when Gemini returns DIGITAL and MARKETING as separate groups.
    elements = template.get("text_elements") or []
    ordered = sorted(
        elements,
        key=lambda e: (int(e.get("y", 0)), int(e.get("x", 0))),
    )
    wanted_words = wanted.split()
    for index in range(len(ordered)):
        collected: List[Dict[str, Any]] = []
        words: List[str] = []
        for candidate in ordered[index:index + max(1, len(wanted_words) + 2)]:
            text = _norm_text(candidate.get("text", ""))
            if not text:
                continue
            collected.append(candidate)
            words.extend(text.split())
            joined = " ".join(words)
            if joined == wanted:
                ids = {str(e.get("id")) for e in collected}
                matching_groups = [
                    g for g in groups
                    if ids.intersection({str(x) for x in (g.get("element_ids") or [])})
                ]
                if matching_groups:
                    # Prefer an already logical title/logo group.
                    preferred = next(
                        (
                            g for g in matching_groups
                            if str(g.get("role", "")).lower() in {"title", "headline", "logo"}
                        ),
                        None,
                    )
                    if preferred:
                        return preferred

                    # Merge the matched elements into a temporary group. This
                    # also protects old templates generated before text_groups.
                    base = matching_groups[0]
                    return base
            if len(words) >= len(wanted_words):
                break

    # 4. Substring matching as a final safe fallback.
    for group in groups:
        group_text = _norm_text(group.get("text", ""))
        if wanted in group_text or group_text in wanted:
            return group

    return None


def _find_logo_group(template: Dict[str, Any]) -> Dict[str, Any] | None:
    groups = _group_catalog(template)
    for group in groups:
        role = str(group.get("role", "")).lower()
        text = _norm_text(group.get("text", ""))
        if role == "logo" or any(
            token in text
            for token in ("nicat", "group of education", "group of institutions", "tinitiate")
        ):
            return group
    return None


def _extract_replacement_pairs(prompt: str) -> List[Tuple[str, str]]:
    """Extract explicit replacement statements without swallowing context.

    Handles:
      DIGITAL MARKETING -> PYTHON PROGRAMMING
      DIGITAL MARKETING → PYTHON PROGRAMMING
      DIGITAL MARKETING to PYTHON PROGRAMMING

    The old regex captured ``Change only:\nDIGITAL MARKETING`` as the source
    phrase, which caused the deterministic match to fail and allowed Gemini to
    choose an unrelated text group. This parser works line-by-line first.
    """
    pairs: List[Tuple[str, str]] = []
    lines = [line.strip() for line in prompt.splitlines() if line.strip()]

    arrow_re = re.compile(r"^(?:change|replace)\s+(?:only\s*:\s*)?(.+?)\s*(?:→|->|=>)\s*(.+?)\s*[.]?$", re.I)
    plain_arrow_re = re.compile(r"^(.+?)\s*(?:→|->|=>)\s*(.+?)\s*[.]?$", re.I)

    for line in lines:
        match = arrow_re.match(line) or plain_arrow_re.match(line)
        if match:
            old = match.group(1).strip(" \"'`:")
            new = match.group(2).strip(" \"'`.")
            if old and new:
                pairs.append((old, new))

    # Handle a common sentence containing two changes separated by "and".
    sentence_re = re.compile(
        r"(?:change|replace)\s+(.+?)\s+(?:to|with)\s+(.+?)(?=\s+and\s+(?:change|replace)\s+|$)",
        re.I,
    )
    for match in sentence_re.finditer(prompt):
        old = match.group(1).strip(" \"'`:")
        new = match.group(2).strip(" \"'`.;")
        if old and new and not any(_norm_text(old) == _norm_text(a) for a, _ in pairs):
            pairs.append((old, new))

    # Handle "NiCAT group of institutions to TinitiateAI" style wording.
    logo_re = re.compile(
        r"\b(?:nicat|the\s+nicat)\b.*?\b(?:group\s+of\s+(?:education|institutions)|institution(?:s)?|organization)\b\s+(?:to|as)\s+([A-Za-z][A-Za-z0-9 ._-]{1,60})",
        re.I,
    )
    match = logo_re.search(prompt)
    if match:
        replacement = re.split(r"\s+(?:and|keep|preserve|unchanged)\b", match.group(1).strip(), maxsplit=1, flags=re.I)[0].strip(" \"'`.;")
        if replacement:
            pairs.append(("__LOGO__", replacement))

    return pairs


def _parse_explicit_replacements(prompt: str, template: Dict[str, Any]) -> Tuple[Dict[str, str], List[str]]:
    """Resolve explicit user replacements deterministically before Gemini."""
    changes: Dict[str, str] = {}
    unmatched: List[str] = []

    for old, new in _extract_replacement_pairs(prompt):
        if old == "__LOGO__":
            group = _find_logo_group(template)
            if group:
                changes[str(group["id"])] = new
            else:
                unmatched.append("Could not locate the existing logo text region.")
            continue

        group = _find_group_for_exact_text(template, old)
        if group:
            changes[str(group["id"])] = new
        else:
            unmatched.append(f"Could not locate source text: {old}")

    return changes, unmatched

def parse_content_changes(content_prompt: str, template: Dict[str, Any]) -> Dict[str, Any]:
    """Map a natural-language prompt to existing editable text groups.

    Exact replacements are resolved locally first. Gemini is used only for
    remaining semantic instructions, and it is constrained to the existing
    template IDs. No new visual element can be created by this step.
    """
    prompt = (content_prompt or "").strip()
    if not prompt:
        raise ValueError("Content prompt is required.")

    elements = template.get("text_elements") or []
    groups = _group_catalog(template)
    if not elements or not groups:
        raise RuntimeError(
            "The generated template has no editable text regions. Regenerate the template with a configured Gemini API key."
        )

    local_changes, local_unmatched = _parse_explicit_replacements(prompt, template)

    # If the user supplied explicit replacements and every requested change was
    # resolved locally, do NOT send the instruction to Gemini. This makes exact
    # poster editing deterministic and prevents the model from moving a title
    # change into an unrelated service/body region.
    explicit_pairs = _extract_replacement_pairs(prompt)
    if explicit_pairs and local_changes and not local_unmatched:
        return {
            "changes": local_changes,
            "group_changes": local_changes,
            "unmatched_instructions": [],
        }

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or genai is None or types is None:
        if local_changes:
            return {"changes": local_changes, "group_changes": local_changes, "unmatched_instructions": local_unmatched}
        raise RuntimeError("GEMINI_API_KEY is not configured for content parsing.")

    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"
    catalog = json.dumps(
        {
            "groups": [
                {
                    "id": g.get("id"),
                    "role": g.get("role"),
                    "text": g.get("text"),
                    "element_ids": g.get("element_ids"),
                    "line_count": g.get("line_count"),
                }
                for g in groups
            ],
            "elements": _element_catalog(template),
        },
        ensure_ascii=False,
        indent=2,
    )

    instruction = f"""
You are a STRICT content-change parser for an existing poster template.

The reference design is already fixed. Your task is to identify which EXISTING
text groups should change. Never create a new text box and never change any
position, size, color, image, logo shape, background, layout, or decoration.

EXISTING TEMPLATE:
{catalog}

USER INSTRUCTION:
{prompt}

Already-resolved exact replacements:
{json.dumps(local_changes, ensure_ascii=False)}

Return ONLY JSON:
{{
  "changes": {{
    "existing_group_id": "new exact text"
  }},
  "unmatched_instructions": []
}}

Rules:
- Keys MUST be existing group IDs from the template.
- If the user says "A -> B" or "A to B", map A to the existing group whose
  original text is A.
- If the user asks to replace a multi-line title, map the entire title group,
  not just one line.
- If the user asks to change logo/brand wording, map the existing logo group.
  Keep the logo's surrounding shape unchanged.
- If the user requests a new value but does not identify an existing field,
  use the most semantically matching existing group only when unambiguous.
- Preserve the exact replacement wording supplied by the user.
- Never invent phone numbers, names, dates, URLs, services, or claims.
- Return only fields that the user asked to change.
""".strip()

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=[instruction],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        payload = json.loads(_clean_json_text(getattr(response, "text", "")))
        raw_changes = payload.get("changes", {})
        if not isinstance(raw_changes, dict):
            raw_changes = {}

        valid_group_ids = {str(g.get("id")) for g in groups}
        changes: Dict[str, str] = dict(local_changes)
        for key, value in raw_changes.items():
            key = str(key)
            if key in valid_group_ids and isinstance(value, str) and value.strip():
                # Local exact parsing wins over model interpretation.
                changes.setdefault(key, value.strip())

        unmatched = local_unmatched + [str(x) for x in (payload.get("unmatched_instructions") or [])[:10]]
        return {
            "changes": changes,
            "group_changes": changes,
            "unmatched_instructions": unmatched[:10],
        }
    except Exception as exc:
        if local_changes:
            return {
                "changes": local_changes,
                "group_changes": local_changes,
                "unmatched_instructions": local_unmatched + ["Gemini semantic parsing was unavailable; explicit replacements were applied locally."],
            }
        print("Gemini content-change parsing failed:", repr(exc))
        raise RuntimeError(f"Content change parsing failed: {exc}") from exc


def _expand_group_elements(group: Dict[str, Any], template: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids = {str(x) for x in (group.get("element_ids") or [])}
    return [e for e in (template.get("text_elements") or []) if str(e.get("id")) in ids]


def _mask_padding(element: Dict[str, Any], image: Image.Image) -> Tuple[int, int, int, int]:
    x = int(element.get("x", 0))
    y = int(element.get("y", 0))
    w = max(1, int(element.get("width", 1)))
    h = max(1, int(element.get("height", 1)))
    pad_x = max(3, min(14, round(w * 0.05)))
    pad_y = max(3, min(10, round(h * 0.12)))
    return (
        max(0, x - pad_x),
        max(0, y - pad_y),
        min(image.width, x + w + pad_x),
        min(image.height, y + h + pad_y),
    )


def _group_mask_box(group: Dict[str, Any], image: Image.Image) -> Tuple[int, int, int, int]:
    """Return a conservative mask around the complete logical text group.

    Gemini's OCR boxes are estimates. Using the group union plus a modest
    margin removes anti-aliased remnants (the visible ghosting seen around the
    old NiCAT logo) without touching the adjacent artwork.
    """
    bbox = group.get("bbox") or {}
    x = int(bbox.get("x", 0))
    y = int(bbox.get("y", 0))
    w = max(1, int(bbox.get("width", 1)))
    h = max(1, int(bbox.get("height", 1)))
    role = str(group.get("role", "")).lower()

    if role == "logo":
        pad_x = max(8, min(18, round(w * 0.045)))
        pad_y = max(6, min(12, round(h * 0.12)))
    else:
        pad_x = max(5, min(14, round(w * 0.035)))
        pad_y = max(4, min(10, round(h * 0.10)))

    return (
        max(0, x - pad_x),
        max(0, y - pad_y),
        min(image.width, x + w + pad_x),
        min(image.height, y + h + pad_y),
    )

def _inpaint_regions(
    image: Image.Image,
    elements: List[Dict[str, Any]],
    groups: List[Dict[str, Any]] | None = None,
) -> Image.Image:
    if not elements and not groups:
        return image.copy()

    if cv2 is None or np is None:
        result = image.copy()
        draw = ImageDraw.Draw(result)
        for group in groups or []:
            if str(group.get("role", "")).lower() == "logo":
                x1, y1, x2, y2 = _group_mask_box(group, image)
                # The NiCAT logo sits on a white container in the reference.
                # Filling only the text area prevents the old red letters from
                # bleeding through when OpenCV is unavailable.
                draw.rectangle((x1, y1, x2, y2), fill="white")
        return result

    rgb = np.array(image.convert("RGB"))
    mask = np.zeros((image.height, image.width), dtype=np.uint8)

    # Logos need special handling. In the supplied reference the NiCAT text
    # sits on a solid white rounded container. Generic inpainting can pull the
    # surrounding teal background into that white area, which creates the
    # ghosted/blurred logo seen in the previous output. Sample the border of
    # the logo text region and use its light neutral color to restore only the
    # lettering area.
    logo_fill_regions: List[Tuple[Tuple[int, int, int, int], Tuple[int, int, int]]] = []
    for group in groups or []:
        x1, y1, x2, y2 = _group_mask_box(group, image)
        role = str(group.get("role", "")).lower()
        if role == "logo":
            ring_x1 = max(0, x1 - 4)
            ring_y1 = max(0, y1 - 4)
            ring_x2 = min(image.width, x2 + 4)
            ring_y2 = min(image.height, y2 + 4)
            ring = rgb[ring_y1:ring_y2, ring_x1:ring_x2].reshape(-1, 3)
            if len(ring):
                median = tuple(int(v) for v in np.median(ring, axis=0))
                # Prefer white when the surrounding sampled pixels are clearly
                # part of a light logo container.
                brightness = sum(median) / 3.0
                spread = max(median) - min(median)
                if brightness >= 170 and spread <= 70:
                    logo_fill_regions.append(((x1, y1, x2, y2), median))
                    mask[y1:y2, x1:x2] = 255
                    continue
        mask[y1:y2, x1:x2] = 255

    for element in elements:
        x1, y1, x2, y2 = _mask_padding(element, image)
        mask[y1:y2, x1:x2] = 255

    restored = cv2.inpaint(rgb, mask, 3, cv2.INPAINT_TELEA)

    # Re-apply the sampled logo-container background after inpainting. This
    # guarantees that old logo pixels cannot remain visible under the new brand
    # text.
    for (x1, y1, x2, y2), fill in logo_fill_regions:
        restored[y1:y2, x1:x2] = np.array(fill, dtype=np.uint8)

    return Image.fromarray(restored)


def _split_replacement(text: str, count: int) -> List[str]:
    """Split replacement wording into the number of visual lines in source."""
    text = re.sub(r"\s+", " ", text.strip())
    if count <= 1:
        return [text]
    words = text.split()
    if len(words) <= count:
        return words + [""] * (count - len(words))

    # Balanced word split. For two lines, PYTHON PROGRAMMING naturally becomes
    # [PYTHON, PROGRAMMING], while longer phrases remain readable.
    result: List[str] = []
    remaining = words[:]
    for line_index in range(count - 1):
        remaining_slots = count - line_index
        target_words = max(1, round(len(remaining) / remaining_slots))
        result.append(" ".join(remaining[:target_words]))
        remaining = remaining[target_words:]
    result.append(" ".join(remaining))
    return result


def _draw_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    element: Dict[str, Any],
    forced_width: int | None = None,
    forced_height: int | None = None,
    color_override: str | None = None,
) -> None:
    if not text:
        return
    if bool(element.get("uppercase")):
        text = text.upper()

    box_width = forced_width or int(element.get("width", 100))
    box_height = forced_height or int(element.get("height", 40))
    local = dict(element)
    local["width"] = box_width
    local["height"] = box_height
    font = _fit_single_line_font(draw, text, local)
    tw, th = _text_size(draw, text, font)

    x = int(element.get("x", 0))
    y = int(element.get("y", 0))
    alignment = str(element.get("alignment", "left")).lower()
    if alignment in {"center", "centre"}:
        x += max(0, (box_width - tw) // 2)
    elif alignment == "right":
        x += max(0, box_width - tw)

    y += max(0, (box_height - th) // 2)
    draw.text((x, y), text, font=font, fill=color_override or str(element.get("color", "#FFFFFF")))


def _draw_logo_group(
    draw: ImageDraw.ImageDraw,
    replacement: str,
    group: Dict[str, Any],
    elements: List[Dict[str, Any]],
) -> None:
    """Render brand replacement inside the existing logo text area.

    When the original logo has a large brand line and a smaller subtitle, the
    replacement is rendered as one brand line using the large-line style. If a
    second logo line has a distinct color, trailing uppercase initials such as
    the 'AI' in TinitiateAI use that second color.
    """
    lines = sorted(elements, key=lambda e: (int(e.get("y", 0)), int(e.get("x", 0))))
    primary = lines[0] if lines else {"x": 0, "y": 0, "width": 100, "height": 40, "font_size": 30, "color": "#FFFFFF"}
    bbox = group.get("bbox") or {
        "x": primary.get("x", 0), "y": primary.get("y", 0),
        "width": primary.get("width", 100), "height": primary.get("height", 40),
    }
    local = dict(primary)
    local["x"] = bbox.get("x", 0)
    local["y"] = bbox.get("y", 0)
    local["width"] = bbox.get("width", 100)
    local["height"] = max(int(primary.get("height", 40)), int(bbox.get("height", 40)))
    local["uppercase"] = False

    # Fit the brand into the full logo width.
    font = _fit_single_line_font(draw, replacement, local, min_size=8)
    tw, th = _text_size(draw, replacement, font)
    x = int(bbox.get("x", 0)) + max(0, (int(bbox.get("width", 100)) - tw) // 2)
    y = int(bbox.get("y", 0)) + max(0, (int(bbox.get("height", 40)) - th) // 2)

    primary_color = str(primary.get("color", "#FFFFFF"))
    draw.text((x, y), replacement, font=font, fill=primary_color)

    # If the source logo has a distinct second-line color and the replacement
    # ends in 1-3 uppercase letters, overlay those suffix letters in that color.
    if len(lines) >= 2:
        secondary = lines[1]
        secondary_color = str(secondary.get("color", ""))
        match = re.search(r"([A-Z]{1,3})$", replacement)
        if secondary_color and match:
            suffix = match.group(1)
            prefix = replacement[:-len(suffix)]
            prefix_width = _text_size(draw, prefix, font)[0]
            draw.text((x + prefix_width, y), suffix, font=font, fill=secondary_color)


def _draw_group_change(
    image: Image.Image,
    replacement: str,
    group: Dict[str, Any],
    template: Dict[str, Any],
) -> None:
    draw = ImageDraw.Draw(image)
    elements = _expand_group_elements(group, template)
    if not elements:
        return

    role = str(group.get("role", "body")).lower()
    if role == "logo":
        _draw_logo_group(draw, replacement, group, elements)
        return

    lines = sorted(elements, key=lambda e: (int(e.get("y", 0)), int(e.get("x", 0))))
    target_lines = _split_replacement(replacement, len(lines))

    # A replacement that needs fewer/more lines than the source still uses the
    # source group. Empty old lines are already masked; the replacement is
    # fitted to the union of the original visual lines.
    if len(lines) == 1:
        _draw_line(draw, target_lines[0], lines[0])
        return

    for index, element in enumerate(lines):
        value = target_lines[index] if index < len(target_lines) else ""
        if not value:
            continue
        _draw_line(draw, value, element)


def render_content_changes(
    reference_bytes: bytes,
    content_prompt: str,
    template: Dict[str, Any],
) -> tuple[bytes, str, Dict[str, Any]]:
    image = Image.open(io.BytesIO(reference_bytes)).convert("RGB")
    parsed = parse_content_changes(content_prompt, template)
    group_changes = parsed.get("group_changes") or parsed.get("changes") or {}

    if not group_changes:
        raise ValueError(
            "No safe text changes were identified in the prompt. Specify which existing poster text/content should change."
        )

    groups_by_id = {str(g.get("id")): g for g in _group_catalog(template)}
    changed_elements: List[Dict[str, Any]] = []
    changed_groups: List[Dict[str, Any]] = []
    for group_id in group_changes:
        group = groups_by_id.get(str(group_id))
        if group:
            changed_groups.append(group)
            changed_elements.extend(_expand_group_elements(group, template))

    # Remove only the changed logical text groups. Background, photos, shapes
    # and the logo container remain part of the original reference image.
    clean_image = _inpaint_regions(
        image,
        changed_elements,
        changed_groups,
    )

    for group_id, replacement in group_changes.items():
        group = groups_by_id.get(str(group_id))
        if not group:
            continue
        _draw_group_change(clean_image, str(replacement), group, template)

    buffer = io.BytesIO()
    clean_image.save(buffer, format="PNG")
    return buffer.getvalue(), "Reference-Preserving Template Renderer", parsed
