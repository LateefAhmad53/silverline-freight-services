from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
FLYER_DIR = ROOT / "static" / "flyer"
LOGO_PATH = ROOT / "Assets" / "image-5.jpg"

WIDTH = 1080
HEIGHT = 1350


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    if bold:
        candidates = [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ] + candidates

    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    image = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(image)
    for y in range(h):
        ratio = y / max(h - 1, 1)
        color = (
            int(top[0] + (bottom[0] - top[0]) * ratio),
            int(top[1] + (bottom[1] - top[1]) * ratio),
            int(top[2] + (bottom[2] - top[2]) * ratio),
        )
        draw.line([(0, y), (w, y)], fill=color)
    return image


def draw_orb(canvas: Image.Image, box: tuple[int, int, int, int], color: tuple[int, int, int, int]) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse(box, fill=color)
    canvas.alpha_composite(layer)


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if draw.textlength(trial, font=text_font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    text_font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
    line_spacing: int = 8,
) -> int:
    line_height = text_font.getbbox("Ag")[3] - text_font.getbbox("Ag")[1]
    for line in wrap_lines(draw, text, text_font, max_width):
        draw.text((x, y), line, font=text_font, fill=fill)
        y += line_height + line_spacing
    return y


def draw_logo(canvas: Image.Image, position: tuple[int, int], size: int) -> None:
    x, y = position
    if not LOGO_PATH.exists():
        return
    logo = Image.open(LOGO_PATH).convert("RGB")
    logo = ImageOps.fit(logo, (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)
    circle_logo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    circle_logo.paste(logo, (0, 0))
    circle_logo.putalpha(mask)
    canvas.alpha_composite(circle_logo, dest=(x, y))

    border_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border_layer)
    border_draw.ellipse((x - 4, y - 4, x + size + 4, y + size + 4), outline=(255, 255, 255, 230), width=5)
    canvas.alpha_composite(border_layer)


def draw_bullets(
    draw: ImageDraw.ImageDraw,
    items: Iterable[str],
    start_x: int,
    start_y: int,
    max_width: int,
    bullet_color: tuple[int, int, int],
    text_color: tuple[int, int, int],
    text_font: ImageFont.ImageFont,
) -> int:
    y = start_y
    bullet_r = 6
    for item in items:
        draw.ellipse((start_x, y + 13, start_x + bullet_r * 2, y + 13 + bullet_r * 2), fill=bullet_color)
        y = draw_wrapped(
            draw=draw,
            x=start_x + 28,
            y=y,
            text=item,
            text_font=text_font,
            fill=text_color,
            max_width=max_width - 28,
            line_spacing=6,
        )
        y += 8
    return y


def create_front() -> Image.Image:
    base = vertical_gradient((WIDTH, HEIGHT), (5, 35, 56), (20, 100, 145)).convert("RGBA")
    draw_orb(base, (740, -120, 1180, 310), (115, 193, 231, 70))
    draw_orb(base, (-200, 930, 320, 1450), (109, 180, 222, 75))

    draw = ImageDraw.Draw(base)
    title_font = font(68, bold=True)
    subtitle_font = font(30, bold=False)
    body_font = font(29)
    section_font = font(40, bold=True)
    small_font = font(24)
    cta_font = font(30, bold=True)

    draw.rounded_rectangle((50, 46, WIDTH - 50, 250), radius=28, fill=(255, 255, 255, 30))
    draw_logo(base, (82, 74), 142)
    draw.text((252, 108), "SILVERLINE", font=title_font, fill=(11, 70, 103))
    draw.text((257, 177), "Freight Services", font=subtitle_font, fill=(42, 92, 121))
    draw.text((715, 86), "TRACK", font=font(18, bold=True), fill=(12, 62, 92))
    draw.text((710, 112), "SHIP", font=font(18, bold=True), fill=(12, 62, 92))
    draw.text((705, 138), "DELIVER", font=font(18, bold=True), fill=(12, 62, 92))

    draw.rounded_rectangle((70, 295, WIDTH - 70, 1190), radius=30, fill=(248, 253, 255, 248))
    draw.text((110, 360), "Client Tracking Portal", font=section_font, fill=(18, 82, 120))

    feature_lines = [
        "Track shipment instantly with a valid tracking number.",
        "Live movement progress updates from 0% to 100%.",
        "Item details, route path, and shipment status visible.",
        "Hold alerts appear when processing charges apply.",
        "Updated order receipt downloads as JPG per shipment.",
        "Full Terms and Conditions available on the website.",
    ]
    y = draw_bullets(
        draw=draw,
        items=feature_lines,
        start_x=120,
        start_y=440,
        max_width=WIDTH - 190,
        bullet_color=(15, 92, 134),
        text_color=(24, 66, 94),
        text_font=body_font,
    )

    draw.rounded_rectangle((110, y + 18, WIDTH - 110, y + 250), radius=22, fill=(13, 81, 120))
    draw.text((140, y + 52), "Important Notice", font=font(28, bold=True), fill=(226, 245, 255))
    notice = (
        "Your order may be placed on hold when specific processing charges apply. "
        "Kindly complete payment to continue shipment movement. "
        "All such processing charges are fully refundable after successful delivery."
    )
    draw_wrapped(
        draw=draw,
        x=140,
        y=y + 98,
        text=notice,
        text_font=small_font,
        fill=(230, 246, 255),
        max_width=WIDTH - 300,
        line_spacing=7,
    )

    draw.rounded_rectangle((186, 1080, WIDTH - 186, 1160), radius=18, fill=(8, 52, 78))
    draw.text((250, 1120), "silverline-freight-services.online", font=cta_font, fill=(255, 255, 255))
    draw.text((296, 1235), "Transparent Freight Operations. Reliable Delivery.", font=font(28), fill=(218, 241, 253))
    return base.convert("RGB")


def create_back() -> Image.Image:
    base = vertical_gradient((WIDTH, HEIGHT), (243, 249, 255), (209, 231, 246)).convert("RGBA")
    draw_orb(base, (760, -110, 1220, 330), (19, 104, 149, 38))
    draw_orb(base, (-220, 1040, 300, 1460), (15, 97, 143, 35))

    draw = ImageDraw.Draw(base)
    header_font = font(58, bold=True)
    sub_font = font(24)
    section_font = font(36, bold=True)
    body_font = font(27)
    small_font = font(23)

    draw.rounded_rectangle((60, 56, WIDTH - 60, 240), radius=26, fill=(255, 255, 255, 240))
    draw.text((100, 116), "Operations + Backend Features", font=header_font, fill=(12, 66, 99))
    draw.text(
        (102, 190),
        "Built for control, transparency, and customer confidence",
        font=sub_font,
        fill=(46, 93, 120),
    )

    draw.rounded_rectangle((62, 286, 698, 1020), radius=24, fill=(10, 72, 108))
    draw.text((100, 350), "Dashboard Controls", font=section_font, fill=(236, 248, 255))
    admin_lines = [
        "Generate real tracking numbers from order details.",
        "Search and locate any shipment by tracking number.",
        "Edit shipment details, item description, and route.",
        "Set hold status when charges apply.",
        "Release hold immediately after payment confirmation.",
        "Update live shipment progress from 0% to 100%.",
        "Delete completed or old shipment records safely.",
        "Download fresh JPG receipt after every update.",
        "Review date-based shipment analytics summary.",
    ]
    draw_bullets(
        draw=draw,
        items=admin_lines,
        start_x=95,
        start_y=430,
        max_width=570,
        bullet_color=(147, 215, 244),
        text_color=(235, 247, 255),
        text_font=small_font,
    )

    draw.rounded_rectangle((732, 286, WIDTH - 62, 780), radius=24, fill=(255, 255, 255, 242))
    draw.text((760, 342), "Shipping Stages", font=font(34, bold=True), fill=(16, 79, 113))
    stages = [
        "1. Security and Safety Processing",
        "2. Clearance Procedures",
        "3. Regulatory Agency Processing",
        "4. Final Handling and Delivery",
    ]
    stage_y = 415
    for stage in stages:
        draw.rounded_rectangle((760, stage_y, 980, stage_y + 76), radius=14, fill=(14, 91, 132))
        draw_wrapped(
            draw=draw,
            x=774,
            y=stage_y + 18,
            text=stage,
            text_font=font(20, bold=True),
            fill=(240, 249, 255),
            max_width=190,
            line_spacing=3,
        )
        stage_y += 96

    draw.rounded_rectangle((732, 800, WIDTH - 62, 1040), radius=20, fill=(16, 76, 112))
    draw.text((760, 846), "Charges Policy", font=font(30, bold=True), fill=(232, 247, 255))
    policy = (
        "Processing charges are mandatory and temporary. "
        "A full refund is issued after successful delivery. "
        "The original shipping fee remains non-refundable."
    )
    draw_wrapped(
        draw=draw,
        x=760,
        y=894,
        text=policy,
        text_font=font(19),
        fill=(232, 247, 255),
        max_width=250,
        line_spacing=3,
    )

    draw.rounded_rectangle((60, 1060, WIDTH - 60, 1264), radius=24, fill=(10, 64, 94))
    draw.text((102, 1126), "Website: silverline-freight-services.online", font=font(34, bold=True), fill=(255, 255, 255))
    draw.text((102, 1180), "Client tracking, hold/release workflow, and dynamic JPG receipts.", font=font(24), fill=(223, 244, 255))

    return base.convert("RGB")


def main() -> None:
    FLYER_DIR.mkdir(parents=True, exist_ok=True)
    front = create_front()
    back = create_back()

    front_path = FLYER_DIR / "silverline-flyer-front.jpg"
    back_path = FLYER_DIR / "silverline-flyer-back.jpg"

    front.save(front_path, "JPEG", quality=95, optimize=True, progressive=True)
    back.save(back_path, "JPEG", quality=95, optimize=True, progressive=True)

    print(f"Created: {front_path}")
    print(f"Created: {back_path}")


if __name__ == "__main__":
    main()
