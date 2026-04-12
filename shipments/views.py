import json
from io import BytesIO
from datetime import timedelta
from pathlib import Path
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from PIL import Image, ImageDraw, ImageFont

from .forms import (
    ShipmentHoldForm,
    ShipmentOrderCreateForm,
    ShipmentOrderEditForm,
    ShipmentProgressForm,
    ShipmentReceiptGeneratorForm,
    ShipmentStatusForm,
    TrackShipmentForm,
)
from .models import ShipmentOrder, ShipmentReceipt

TERMS_SHORT_NOTE = (
    "Processing charges can apply during security, clearance, and regulatory stages. "
    "These processing charges are temporary and fully refundable after successful delivery."
)

MANUAL_RECEIPT_BASE_WIDTH = 853
MANUAL_RECEIPT_BASE_HEIGHT = 1280


def _load_receipt_font(size: int, *, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "DejaVuSans.ttf",
    ]
    if bold:
        candidates = [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "DejaVuSans-Bold.ttf",
        ] + candidates

    for font_path in candidates:
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _line_height(font) -> int:
    bbox = font.getbbox("Ag")
    return bbox[3] - bbox[1]


def _wrap_text_to_width(draw, text: str, font, max_width: int) -> list[str]:
    wrapped_lines: list[str] = []
    for paragraph in str(text).split("\n"):
        words = paragraph.split()
        if not words:
            wrapped_lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                wrapped_lines.append(current)
                current = word
        wrapped_lines.append(current)
    return wrapped_lines


def _draw_wrapped_text(draw, text, x, y, max_width=1400, font=None, fill="#1c2e40", line_spacing=10):
    lines = _wrap_text_to_width(draw, str(text), font, max_width)
    height = _line_height(font)
    for line in lines:
        draw.text((x, y), line, fill=fill, font=font)
        y += height + line_spacing
    return y


def _invoice_issued_timestamp() -> str:
    invoice_tz = ZoneInfo(getattr(settings, "INVOICE_TIME_ZONE", "America/New_York"))
    issued_at = timezone.now().astimezone(invoice_tz)
    return issued_at.strftime("%Y-%m-%d %I:%M %p %Z")


def _build_receipt_image(order: ShipmentOrder) -> BytesIO:
    width, height = 2200, 4200
    image = Image.new("RGB", (width, height), "#f4f7fb")
    draw = ImageDraw.Draw(image)
    title_font = _load_receipt_font(94, bold=True)
    subtitle_font = _load_receipt_font(52, bold=False)
    label_font = _load_receipt_font(44, bold=True)
    body_font = _load_receipt_font(40, bold=False)
    header_meta_font = _load_receipt_font(34, bold=False)
    note_title_font = _load_receipt_font(46, bold=True)
    note_body_font = _load_receipt_font(35, bold=False)

    # Header block: split into two fixed panels to prevent overlap.
    header_left = 60
    header_top = 40
    header_right = width - 60
    header_bottom = 420
    draw.rounded_rectangle((header_left, header_top, header_right, header_bottom), radius=26, fill="#0f5b84")

    left_panel = (95, 82, 1500, 378)
    right_panel = (1540, 82, width - 95, 378)
    draw.rounded_rectangle(left_panel, radius=20, fill="#0f5b84")
    draw.rounded_rectangle(right_panel, radius=20, fill="#0b4d71")

    left_x = left_panel[0] + 36
    left_y = left_panel[1] + 26
    left_width = (left_panel[2] - left_panel[0]) - 72

    title_lines = _wrap_text_to_width(draw, "SILVERLINE Freight Services", title_font, left_width)
    title_y = left_y
    title_gap = 8
    for line in title_lines:
        draw.text((left_x, title_y), line, fill="white", font=title_font)
        title_y += _line_height(title_font) + title_gap

    draw.text((left_x, title_y + 4), "Official Shipment Receipt (JPG)", fill="#d5ebf8", font=subtitle_font)

    right_x = right_panel[0] + 30
    right_y = right_panel[1] + 52
    right_width = (right_panel[2] - right_panel[0]) - 60
    right_y = _draw_wrapped_text(
        draw,
        f"Tracking: {order.tracking_number}",
        right_x,
        right_y,
        max_width=right_width,
        font=header_meta_font,
        fill="white",
        line_spacing=8,
    )
    _draw_wrapped_text(
        draw,
        f"Issued: {_invoice_issued_timestamp()}",
        right_x,
        right_y + 10,
        max_width=right_width,
        font=header_meta_font,
        fill="#d5ebf8",
        line_spacing=8,
    )

    # Main body card
    draw.rounded_rectangle((60, 430, width - 60, 2600), radius=26, fill="white", outline="#dbe4ee")
    y = 500
    left_x = 120
    value_x = 640
    value_width = width - value_x - 140

    hold_status = "On Hold" if order.hold_active else "Released / No active hold"
    hold_charge = f"${order.hold_amount}" if order.hold_active and order.hold_amount else "No active processing charge"
    hold_reason = order.hold_reason if order.hold_active and order.hold_reason else "-"

    rows = [
        ("Sender", order.sender_name or "-"),
        ("Receiver", order.receiver_name or "-"),
        ("From Address", order.from_address),
        ("To Address", order.to_address),
        ("Current Location", order.current_location or "-"),
        ("Status", order.get_status_display()),
        ("Progress", f"{order.progress_percent}%"),
        ("Item Name", order.item_name or "-"),
        ("Item Quantity", str(order.item_quantity)),
        ("Item Weight (kg)", str(order.item_weight_kg or "-")),
        ("Expected Delivery", str(order.expected_delivery_date or "-")),
        ("Hold Status", hold_status),
        ("Hold Charge", hold_charge),
        ("Hold Reason", hold_reason),
    ]

    for label, value in rows:
        draw.text((left_x, y), f"{label}:", fill="#35516b", font=label_font)
        y = _draw_wrapped_text(
            draw,
            value,
            value_x,
            y,
            max_width=value_width,
            font=body_font,
            line_spacing=10,
        )
        y += 16
        draw.line((left_x, y, width - 120, y), fill="#edf2f7", width=2)
        y += 28

    if order.item_description:
        draw.text((left_x, y), "Item Description:", fill="#35516b", font=label_font)
        y = _draw_wrapped_text(
            draw,
            order.item_description,
            value_x,
            y,
            max_width=value_width,
            font=body_font,
            line_spacing=10,
        )

    # Terms note block (required short note)
    note_top = y + 70
    note_x = 100
    note_width = width - 200
    terms_lines = _wrap_text_to_width(draw, TERMS_SHORT_NOTE, note_body_font, note_width - 40)
    terms_height = len(terms_lines) * (_line_height(note_body_font) + 10)
    hold_lines_height = 0
    if order.hold_active and order.hold_message:
        hold_lines = _wrap_text_to_width(
            draw,
            f"Current Order Hold Notice: {order.hold_message}",
            note_body_font,
            note_width - 40,
        )
        hold_lines_height = len(hold_lines) * (_line_height(note_body_font) + 10) + 24

    note_bottom = note_top + 70 + _line_height(note_title_font) + terms_height + hold_lines_height + 50
    draw.rounded_rectangle(
        (60, note_top, width - 60, note_bottom),
        radius=24,
        fill="#fff6eb",
        outline="#eed4ab",
        width=2,
    )
    draw.text((note_x, note_top + 28), "Processing Charges & Refund Note", fill="#8d4a12", font=note_title_font)
    hold_y = _draw_wrapped_text(
        draw,
        TERMS_SHORT_NOTE,
        note_x,
        note_top + 28 + _line_height(note_title_font) + 26,
        max_width=note_width,
        font=note_body_font,
        fill="#6d3f12",
        line_spacing=10,
    )
    if order.hold_active and order.hold_message:
        _draw_wrapped_text(
            draw,
            f"Current Order Hold Notice: {order.hold_message}",
            note_x,
            hold_y + 24,
            max_width=note_width,
            font=note_body_font,
            fill="#6d3f12",
            line_spacing=10,
        )

    final_height = min(height, note_bottom + 80)
    image = image.crop((0, 0, width, final_height))

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    return buffer


def _resolve_manual_receipt_template_path() -> Path:
    assets_dir = settings.BASE_DIR / "Assets"
    direct_candidates = (
        "image1.jpg",
        "Receipt1.jpg",
        "receipt1.jpg",
    )
    for name in direct_candidates:
        candidate = assets_dir / name
        if candidate.exists():
            return candidate

    pattern_candidates = (
        "*image1*.jpg",
        "*Receipt1*.jpg",
        "*receipt1*.jpg",
    )
    for pattern in pattern_candidates:
        matches = sorted(assets_dir.glob(pattern))
        if matches:
            return matches[0]

    raise FileNotFoundError("Receipt template image not found in Assets directory.")


def _draw_trimmed_text(draw, value: str, x: int, y: int, max_width: int, *, font, fill: str):
    text = str(value or "").strip()
    if not text:
        return
    if draw.textlength(text, font=font) <= max_width:
        draw.text((x, y), text, font=font, fill=fill)
        return

    trimmed = text
    while trimmed and draw.textlength(f"{trimmed}...", font=font) > max_width:
        trimmed = trimmed[:-1]
    draw.text((x, y), f"{trimmed}..." if trimmed else "...", font=font, fill=fill)


def _build_manual_receipt_image(receipt: ShipmentReceipt) -> BytesIO:
    template_path = _resolve_manual_receipt_template_path()
    image = Image.open(template_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    width_scale = image.width / MANUAL_RECEIPT_BASE_WIDTH
    height_scale = image.height / MANUAL_RECEIPT_BASE_HEIGHT
    scale = min(width_scale, height_scale)

    def sx(value: int) -> int:
        return int(round(value * width_scale))

    def sy(value: int) -> int:
        return int(round(value * height_scale))

    def sw(value: int) -> int:
        return max(1, int(round(value * width_scale)))

    base_font_size = max(14, int(round(18 * scale)))
    font = _load_receipt_font(base_font_size)
    amount_font = _load_receipt_font(max(13, int(round(16 * scale))))
    ink = "#1f1f1f"

    # Top identity fields.
    _draw_trimmed_text(draw, receipt.location, sx(248), sy(246), sw(205), font=font, fill=ink)
    _draw_trimmed_text(draw, receipt.device_id, sx(246), sy(268), sw(207), font=font, fill=ink)
    _draw_trimmed_text(draw, receipt.tid, sx(219), sy(290), sw(237), font=font, fill=ink)

    # Mid body fields.
    _draw_trimmed_text(draw, receipt.item, sx(224), sy(447), sw(304), font=font, fill=ink)
    _draw_trimmed_text(draw, receipt.recipient_address, sx(301), sy(628), sw(229), font=font, fill=ink)
    _draw_trimmed_text(draw, receipt.recipient_name, sx(313), sy(665), sw(217), font=font, fill=ink)
    _draw_trimmed_text(draw, receipt.recipient_number, sx(338), sy(703), sw(192), font=font, fill=ink)
    _draw_trimmed_text(
        draw,
        receipt.schedule_delivery_date.strftime("%m-%d-%Y"),
        sx(365),
        sy(742),
        sw(165),
        font=font,
        fill=ink,
    )
    pricing_text = str(receipt.pricing_option or "").strip()
    if pricing_text and pricing_text.lower() not in {"standard", "standard rate"}:
        _draw_trimmed_text(draw, pricing_text, sx(367), sy(767), sw(163), font=font, fill=ink)

    # Charges area.
    _draw_trimmed_text(
        draw,
        _format_receipt_amount(receipt.shipping_subtotal),
        sx(412),
        sy(848),
        sw(118),
        font=amount_font,
        fill=ink,
    )
    _draw_trimmed_text(
        draw,
        _format_receipt_amount(receipt.custom_charges),
        sx(419),
        sy(874),
        sw(111),
        font=amount_font,
        fill=ink,
    )
    _draw_trimmed_text(
        draw,
        _format_receipt_amount(receipt.total),
        sx(350),
        sy(889),
        sw(81),
        font=amount_font,
        fill=ink,
    )

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    return buffer


def _manual_receipt_download_response(receipt: ShipmentReceipt) -> HttpResponse:
    image_stream = _build_manual_receipt_image(receipt)
    response = HttpResponse(image_stream.getvalue(), content_type="image/jpeg")
    response["Content-Disposition"] = (
        f'attachment; filename="shipment-receipt-{receipt.id}-{receipt.schedule_delivery_date:%Y%m%d}.jpg"'
    )
    return response


def _format_currency(value) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError):
        amount = Decimal("0")
    return f"${amount:.2f}"


def _format_receipt_amount(value) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError):
        amount = Decimal("0")
    return f"{amount:.2f}"


def home(request: HttpRequest) -> HttpResponse:
    form = TrackShipmentForm(request.GET or None)
    order = None
    lookup_attempted = False
    tracking_number = ""

    if form.is_valid() and form.cleaned_data.get("tracking_number"):
        lookup_attempted = True
        tracking_number = form.cleaned_data["tracking_number"].strip().upper()
        order = ShipmentOrder.objects.filter(tracking_number__iexact=tracking_number).first()

    context = {
        "track_form": form,
        "order": order,
        "lookup_attempted": lookup_attempted,
        "tracking_number": tracking_number,
    }
    return render(request, "home.html", context)


def services(request: HttpRequest) -> HttpResponse:
    return render(request, "service.html")


@require_http_methods(["GET", "POST"])
def backend_login(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = AuthenticationForm(request, data=request.POST or None)
    form.fields["username"].widget.attrs.update(
        {"class": "input-field", "placeholder": "Admin email (username)"}
    )
    form.fields["password"].widget.attrs.update({"class": "input-field", "placeholder": "Password"})
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        messages.success(request, "Welcome back. Backend access granted.")
        return redirect("dashboard")

    return render(request, "backend/login.html", {"form": form})


@require_POST
def backend_logout(request: HttpRequest) -> HttpResponse:
    logout(request)
    messages.info(request, "You have signed out of the backend.")
    return redirect("backend_login")


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    search_query = request.GET.get("tracking", "").strip().upper()
    base_orders = ShipmentOrder.objects.all()
    orders = base_orders
    if search_query:
        orders = orders.filter(tracking_number__icontains=search_query)
        if not orders.exists():
            messages.info(request, f"No order found with tracking number matching '{search_query}'.")

    create_form = ShipmentOrderCreateForm()
    receipt_form = ShipmentReceiptGeneratorForm()
    hold_form = ShipmentHoldForm()
    status_form = ShipmentStatusForm()
    recent_receipts = ShipmentReceipt.objects.select_related("created_by")[:10]

    today = timezone.localdate()
    start_date = today - timedelta(days=6)
    daily_counts = (
        base_orders.filter(created_at__date__gte=start_date)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )
    daily_map = {item["day"]: item["total"] for item in daily_counts}
    chart_dates = [start_date + timedelta(days=offset) for offset in range(7)]
    chart_labels = [date.strftime("%b %d") for date in chart_dates]
    chart_values = [daily_map.get(date, 0) for date in chart_dates]

    context = {
        "create_form": create_form,
        "receipt_form": receipt_form,
        "hold_form": hold_form,
        "status_form": status_form,
        "recent_receipts": recent_receipts,
        "orders": orders,
        "search_query": search_query,
        "total_orders": base_orders.count(),
        "delivered_orders": base_orders.filter(status=ShipmentOrder.ShipmentStatus.DELIVERED).count(),
        "transit_orders": base_orders.filter(status=ShipmentOrder.ShipmentStatus.IN_TRANSIT).count(),
        "hold_orders": base_orders.filter(status=ShipmentOrder.ShipmentStatus.ON_HOLD).count(),
        "today_orders": base_orders.filter(created_at__date=today).count(),
        "chart_labels": json.dumps(chart_labels),
        "chart_values": json.dumps(chart_values),
    }
    return render(request, "backend/dashboard.html", context)


@login_required
@require_POST
def generate_manual_receipt(request: HttpRequest) -> HttpResponse:
    form = ShipmentReceiptGeneratorForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Receipt form is incomplete. Fill all required fields and try again.")
        return redirect("dashboard")

    receipt = form.save(commit=False)
    receipt.created_by = request.user
    receipt.save()

    try:
        return _manual_receipt_download_response(receipt)
    except FileNotFoundError:
        messages.error(
            request,
            "Receipt template image is missing in Assets. Add image1.jpg or Receipt1.jpg and try again.",
        )
        return redirect("dashboard")


@login_required
@require_http_methods(["GET", "POST"])
def edit_manual_receipt(request: HttpRequest, receipt_id: int) -> HttpResponse:
    receipt = get_object_or_404(ShipmentReceipt, id=receipt_id)
    form = ShipmentReceiptGeneratorForm(request.POST or None, instance=receipt)
    if request.method == "POST" and form.is_valid():
        updated_receipt = form.save()
        if request.POST.get("action") == "generate":
            try:
                return _manual_receipt_download_response(updated_receipt)
            except FileNotFoundError:
                messages.error(
                    request,
                    "Receipt template image is missing in Assets. Add image1.jpg or Receipt1.jpg and try again.",
                )
                return redirect("dashboard")

        messages.success(request, "Shipment receipt data updated.")
        return redirect("dashboard")

    return render(request, "backend/edit_receipt.html", {"form": form, "receipt": receipt})


@login_required
def download_manual_receipt(request: HttpRequest, receipt_id: int) -> HttpResponse:
    receipt = get_object_or_404(ShipmentReceipt, id=receipt_id)
    try:
        return _manual_receipt_download_response(receipt)
    except FileNotFoundError:
        messages.error(
            request,
            "Receipt template image is missing in Assets. Add image1.jpg or Receipt1.jpg and try again.",
        )
        return redirect("dashboard")


@login_required
@require_POST
def create_order(request: HttpRequest) -> HttpResponse:
    form = ShipmentOrderCreateForm(request.POST)
    if form.is_valid():
        order = form.save()
        messages.success(request, f"Order created. Tracking number: {order.tracking_number}")
    else:
        messages.error(request, "Unable to create order. Please review all required fields.")
    return redirect("dashboard")


@login_required
@require_POST
def place_hold(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(ShipmentOrder, id=order_id)
    form = ShipmentHoldForm(request.POST)
    if form.is_valid():
        order.place_on_hold(
            amount=form.cleaned_data["hold_amount"],
            reason=form.cleaned_data["hold_reason"],
            message=form.cleaned_data.get("hold_message"),
        )
        messages.warning(request, f"Shipment {order.tracking_number} is now on hold.")
    else:
        messages.error(request, "Could not place shipment on hold. Check hold details and try again.")
    return redirect("dashboard")


@login_required
@require_POST
def release_hold(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(ShipmentOrder, id=order_id)
    order.release_hold()
    messages.success(request, f"Hold released for {order.tracking_number}. Shipment resumed.")
    return redirect("dashboard")


@login_required
@require_POST
def update_status(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(ShipmentOrder, id=order_id)
    form = ShipmentStatusForm(request.POST, instance=order)
    if form.is_valid():
        updated_order = form.save(commit=False)
        if updated_order.status != ShipmentOrder.ShipmentStatus.ON_HOLD:
            updated_order.hold_active = False
        updated_order.save()
        messages.success(request, f"Shipment {order.tracking_number} status updated.")
    else:
        messages.error(request, "Status update failed. Please confirm values and try again.")
    return redirect("dashboard")


@login_required
@require_POST
def update_progress(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(ShipmentOrder, id=order_id)
    form = ShipmentProgressForm(request.POST, instance=order)
    if form.is_valid():
        updated_order = form.save(commit=False)
        if updated_order.progress_percent == 100 and updated_order.status != ShipmentOrder.ShipmentStatus.ON_HOLD:
            updated_order.status = ShipmentOrder.ShipmentStatus.DELIVERED
        elif (
            updated_order.progress_percent > 0
            and updated_order.status == ShipmentOrder.ShipmentStatus.PENDING
        ):
            updated_order.status = ShipmentOrder.ShipmentStatus.IN_TRANSIT
        updated_order.save()
        messages.success(request, f"Progress updated for {order.tracking_number}: {updated_order.progress_percent}%.")
    else:
        messages.error(request, "Progress update failed. Enter a value from 0 to 100.")
    return redirect("dashboard")


@login_required
@require_http_methods(["GET", "POST"])
def edit_order(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(ShipmentOrder, id=order_id)
    form = ShipmentOrderEditForm(request.POST or None, instance=order)
    if request.method == "POST" and form.is_valid():
        updated_order = form.save(commit=False)
        if updated_order.status == ShipmentOrder.ShipmentStatus.ON_HOLD:
            updated_order.hold_active = True
        elif updated_order.hold_active:
            updated_order.hold_active = False
        updated_order.save()
        messages.success(request, f"Order {updated_order.tracking_number} has been updated.")
        return redirect("dashboard")
    return render(request, "backend/edit_order.html", {"form": form, "order": order})


@login_required
@require_POST
def delete_order(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(ShipmentOrder, id=order_id)
    tracking_number = order.tracking_number
    order.delete()
    messages.success(request, f"Order {tracking_number} was deleted.")
    return redirect("dashboard")


@login_required
def download_receipt_jpg(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(ShipmentOrder, id=order_id)
    image_stream = _build_receipt_image(order)
    response = HttpResponse(image_stream.getvalue(), content_type="image/jpeg")
    response["Content-Disposition"] = f'attachment; filename="{order.tracking_number}-receipt.jpg"'
    return response
