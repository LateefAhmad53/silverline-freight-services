import json
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

from .forms import (
    ShipmentHoldForm,
    ShipmentOrderCreateForm,
    ShipmentOrderEditForm,
    ShipmentProgressForm,
    ShipmentStatusForm,
    TrackShipmentForm,
)
from .models import ShipmentOrder


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
