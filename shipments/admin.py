from django.contrib import admin

from .models import ShipmentOrder


@admin.action(description="Mark selected shipments as in transit")
def release_shipments(modeladmin, request, queryset):
    queryset.update(hold_active=False, status=ShipmentOrder.ShipmentStatus.IN_TRANSIT)


@admin.action(description="Mark selected shipments as on hold")
def hold_shipments(modeladmin, request, queryset):
    queryset.update(hold_active=True, status=ShipmentOrder.ShipmentStatus.ON_HOLD)


@admin.register(ShipmentOrder)
class ShipmentOrderAdmin(admin.ModelAdmin):
    list_display = (
        "tracking_number",
        "item_name",
        "item_quantity",
        "sender_name",
        "receiver_name",
        "status",
        "progress_percent",
        "hold_active",
        "hold_amount",
        "updated_at",
    )
    search_fields = (
        "tracking_number",
        "item_name",
        "item_description",
        "from_address",
        "to_address",
        "sender_name",
        "receiver_name",
    )
    list_filter = ("status", "hold_active", "created_at")
    readonly_fields = ("tracking_number", "created_at", "updated_at")
    actions = [release_shipments, hold_shipments]
