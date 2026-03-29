import json
from io import BytesIO
from textwrap import wrap
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
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
    ShipmentStatusForm,
    TrackShipmentForm,
)
from .models import ShipmentOrder

TERMS_SHORT_NOTE = (
    "Processing charges can apply during security, clearance, and regulatory stages. "
    "These processing charges are temporary and fully refundable after successful delivery."
)


def _draw_wrapped_text(draw, text, x, y, max_chars=86, font=None, fill="#1c2e40", line_height=22):
    lines = []
    for paragraph in str(text).split("\n"):
        wrapped = wrap(paragraph, width=max_chars) or [""]
        lines.extend(wrapped)
    for line in lines:
        draw.text((x, y), line, fill=fill, font=font)
        y += line_height
    return y


def _build_receipt_image(order: ShipmentOrder) -> BytesIO:
    width, height = 1400, 1750
    image = Image.new("RGB", (width, height), "#f4f7fb")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default()
    body_font = ImageFont.load_default()

    # Header block
    draw.rounded_rectangle((40, 30, width - 40, 220), radius=18, fill="#0f5b84")
    draw.text((75, 70), "SILVERLINE Freight Services", fill="white", font=title_font)
    draw.text((75, 110), "Official Shipment Receipt (JPG)", fill="#d5ebf8", font=body_font)
    draw.text((980, 75), f"Tracking: {order.tracking_number}", fill="white", font=body_font)
    draw.text(
        (980, 115),
        f"Issued: {timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')}",
        fill="#d5ebf8",
        font=body_font,
    )

    # Main body card
    draw.rounded_rectangle((40, 250, width - 40, 1320), radius=18, fill="white", outline="#dbe4ee")
    y = 290
    left_x = 80

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
        (
            "Hold Charge",
            f"${order.hold_amount}" if order.hold_amount else "No active processing charge",
        ),
    ]

    for label, value in rows:
        draw.text((left_x, y), f"{label}:", fill="#35516b", font=body_font)
        y = _draw_wrapped_text(draw, value, left_x + 220, y, max_chars=62, font=body_font, line_height=24)
        y += 10
        draw.line((left_x, y, width - 80, y), fill="#edf2f7", width=1)
        y += 20

    if order.item_description:
        draw.text((left_x, y), "Item Description:", fill="#35516b", font=body_font)
        y = _draw_wrapped_text(
            draw,
            order.item_description,
            left_x + 220,
            y,
            max_chars=62,
            font=body_font,
            line_height=24,
        )

    # Terms note block (required short note)
    note_top = 1360
    draw.rounded_rectangle((40, note_top, width - 40, 1650), radius=18, fill="#fff6eb", outline="#eed4ab")
    draw.text((75, note_top + 28), "Processing Charges & Refund Note", fill="#8d4a12", font=title_font)
    _draw_wrapped_text(
        draw,
        TERMS_SHORT_NOTE,
        75,
        note_top + 65,
        max_chars=96,
        font=body_font,
        fill="#6d3f12",
        line_height=24,
    )
    if order.hold_active and order.hold_message:
        _draw_wrapped_text(
            draw,
            f"Current Order Hold Notice: {order.hold_message}",
            75,
            note_top + 145,
            max_chars=96,
            font=body_font,
            fill="#6d3f12",
            line_height=24,
        )

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    buffer.seek(0)
    return buffer


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
    hold_form = ShipmentHoldForm()
    status_form = ShipmentStatusForm()

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
        "hold_form": hold_form,
        "status_form": status_form,
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
