from __future__ import annotations

"""Convert a structured AI scene graph into a real editable PPTX.

The generated PNG is used only as the pixel source from which image/background
regions are cropped. Canva receives a PPTX containing native text boxes,
native shapes, separate image objects, and a separate background object. No
Canva image-to-design/Magic Layers conversion is used.
"""

from pathlib import Path
from typing import Any
import io

from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _hex_rgb(value: Any, default: str = "#FFFFFF") -> RGBColor:
    text = str(value or default).strip().lstrip("#")
    if len(text) != 6:
        text = default.lstrip("#")
    try:
        return RGBColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return RGBColor(255, 255, 255)


def _hex_alpha(value: Any) -> int:
    text = str(value or "").strip().lstrip("#")
    if len(text) == 8:
        try:
            return int(text[6:8], 16)
        except ValueError:
            pass
    return 255


def _crop(image: Image.Image, element: dict) -> Image.Image:
    x = max(0, int(_safe_float(element.get("x"))))
    y = max(0, int(_safe_float(element.get("y"))))
    w = max(1, int(_safe_float(element.get("width"), image.width)))
    h = max(1, int(_safe_float(element.get("height"), image.height)))
    x2 = min(image.width, x + w)
    y2 = min(image.height, y + h)
    return image.crop((x, y, x2, y2)).convert("RGBA")


def _mask_boxes(image: Image.Image, elements: list[dict]) -> Image.Image:
    """Remove foreground object boxes from the background using inpainting."""
    try:
        import cv2
        import numpy as np
        array = np.array(image.convert("RGB"))
        mask = np.zeros((array.shape[0], array.shape[1]), dtype=np.uint8)
        for element in elements:
            x = max(0, int(_safe_float(element.get("x"))))
            y = max(0, int(_safe_float(element.get("y"))))
            w = max(1, int(_safe_float(element.get("width"), 100)))
            h = max(1, int(_safe_float(element.get("height"), 50)))
            x2 = min(array.shape[1] - 1, x + w)
            y2 = min(array.shape[0] - 1, y + h)
            cv2.rectangle(mask, (x, y), (x2, y2), 255, -1)
        if mask.any():
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.dilate(mask, kernel, iterations=1)
            array = cv2.inpaint(array, mask, 5, cv2.INPAINT_TELEA)
        return Image.fromarray(array).convert("RGBA")
    except Exception:
        return image.convert("RGBA")


def _shape_type(name: str):
    name = name.lower().replace(" ", "_")
    if name in {"circle", "ellipse", "oval"}:
        return MSO_SHAPE.OVAL
    if name in {"roundrect", "rounded_rectangle", "rounded_rect", "pill"}:
        return MSO_SHAPE.ROUNDED_RECTANGLE
    if name == "triangle":
        return MSO_SHAPE.ISOSCELES_TRIANGLE
    if name == "diamond":
        return MSO_SHAPE.DIAMOND
    if name == "hexagon":
        return MSO_SHAPE.HEXAGON
    return MSO_SHAPE.RECTANGLE


def _add_image(slide, image: Image.Image, element: dict, sx: float, sy: float, slide_width: float, slide_height: float, temp_dir: Path, index: int):
    path = temp_dir / f"asset_{index}.png"
    image.save(path, format="PNG")
    x = max(0.0, _safe_float(element.get("x")) * sx)
    y = max(0.0, _safe_float(element.get("y")) * sy)
    w = max(0.02, _safe_float(element.get("width"), 1) * sx)
    h = max(0.02, _safe_float(element.get("height"), 1) * sy)
    slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))


def build_editable_pptx(template: dict, source_image: Path, output_path: Path) -> Path:
    """Build a structured, Canva-importable PPTX from the AI scene graph."""
    source_image = Path(source_image)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_image) as original:
        source = original.convert("RGBA")

    canvas = template.get("canvas") or {}
    width = max(40.0, _safe_float(canvas.get("width"), source.width))
    height = max(40.0, _safe_float(canvas.get("height"), source.height))
    max_slide_width = 13.333
    slide_width = max_slide_width
    slide_height = slide_width * height / width
    if slide_height > 7.5:
        slide_height = 7.5
        slide_width = slide_height * width / height

    prs = Presentation()
    prs.slide_width = Inches(slide_width)
    prs.slide_height = Inches(slide_height)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    sx, sy = slide_width / width, slide_height / height

    text_elements = [x for x in (template.get("text_elements") or []) if isinstance(x, dict)]
    image_elements = [x for x in (template.get("image_elements") or []) if isinstance(x, dict)]
    shapes = [x for x in (template.get("shapes") or []) if isinstance(x, dict)]
    foreground = text_elements + image_elements + shapes

    # 1. Native slide background color: editable as a Canva/PPT background.
    background = template.get("background") or {}
    bg_color = str(background.get("color") or "#000000")
    try:
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = _hex_rgb(bg_color, "#000000")
    except Exception:
        pass

    # 2. Background visual object: all foreground boxes are removed from a copy
    # so editable overlays do not have duplicate text/images.
    background_image = _mask_boxes(source, foreground)
    bg_path = output_path.with_name(output_path.stem + "_background.png")
    background_image.save(bg_path, format="PNG")
    slide.shapes.add_picture(str(bg_path), 0, 0, width=prs.slide_width, height=prs.slide_height)

    # 3. Separate image objects.
    temp_dir = output_path.with_name(output_path.stem + "_assets")
    temp_dir.mkdir(parents=True, exist_ok=True)
    for index, element in enumerate(sorted(image_elements, key=lambda x: _safe_float(x.get("z_index"), 10))):
        crop = _crop(source, element)
        _add_image(slide, crop, element, sx, sy, slide_width, slide_height, temp_dir, index)

    # 4. Native shapes.
    for element in sorted(shapes, key=lambda x: _safe_float(x.get("z_index"), 5)):
        x = max(0.0, _safe_float(element.get("x")) * sx)
        y = max(0.0, _safe_float(element.get("y")) * sy)
        w = max(0.02, _safe_float(element.get("width"), 100) * sx)
        h = max(0.02, _safe_float(element.get("height"), 50) * sy)
        shape = slide.shapes.add_shape(_shape_type(str(element.get("shape") or "rectangle")), Inches(x), Inches(y), Inches(w), Inches(h))
        fill = str(element.get("fill") or "#00000000")
        if fill.startswith("#") and len(fill) in {7, 9} and _hex_alpha(fill) > 0:
            shape.fill.solid()
            shape.fill.fore_color.rgb = _hex_rgb(fill, "#000000")
            try:
                shape.fill.transparency = 1 - (_hex_alpha(fill) / 255)
            except Exception:
                pass
        else:
            shape.fill.background()
        stroke = str(element.get("stroke") or "#00000000")
        if stroke.startswith("#") and len(stroke) in {7, 9} and _hex_alpha(stroke) > 0:
            shape.line.color.rgb = _hex_rgb(stroke, "#000000")
        else:
            shape.line.fill.background()

    # 5. Native editable text boxes.
    for element in sorted(text_elements, key=lambda x: _safe_float(x.get("z_index"), 20)):
        text = str(element.get("text") or "")
        if not text:
            continue
        x = max(0.0, _safe_float(element.get("x")) * sx)
        y = max(0.0, _safe_float(element.get("y")) * sy)
        w = max(0.05, _safe_float(element.get("width"), 200) * sx)
        h = max(0.05, _safe_float(element.get("height"), 60) * sy)
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.clear()
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        paragraph = tf.paragraphs[0]
        paragraph.text = text
        paragraph.alignment = {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT, "justify": PP_ALIGN.JUSTIFY}.get(str(element.get("alignment") or "left").lower(), PP_ALIGN.LEFT)
        run = paragraph.runs[0]
        run.font.name = str(element.get("font_family") or "Arial")
        run.font.size = Pt(max(6.0, _safe_float(element.get("font_size"), 32) * sx))
        run.font.bold = str(element.get("font_weight") or "normal").lower() in {"bold", "700", "800", "900"}
        run.font.color.rgb = _hex_rgb(element.get("color"), "#FFFFFF")
        box.fill.background()
        box.line.fill.background()

    # Store a compact object manifest inside the PPTX metadata so the import
    # artifact can be audited without depending on Canva's Magic Layers.
    try:
        prs.core_properties.subject = "Structured editable AI design: background, images, shapes, text"
        prs.core_properties.keywords = "canva,editable,structured,background,image,shape,text,no-magic-layers"
    except Exception:
        pass

    prs.save(output_path)

    try:
        bg_path.unlink()
    except OSError:
        pass
    for child in temp_dir.glob("*.png"):
        try:
            child.unlink()
        except OSError:
            pass
    try:
        temp_dir.rmdir()
    except OSError:
        pass

    return output_path
