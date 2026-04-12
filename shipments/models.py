import secrets
import string
from decimal import Decimal, InvalidOperation

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class ShipmentOrder(models.Model):
    class ShipmentStatus(models.TextChoices):
        PENDING = "pending", "Pending Pickup"
        IN_TRANSIT = "in_transit", "In Transit"
        ON_HOLD = "on_hold", "On Hold"
        DELIVERED = "delivered", "Delivered"

    class NoticeOption(models.TextChoices):
        DEFAULT_NOTICE = "default_notice", "Option 1 - Processing Charges Notice"
        ORDER_CHARGES = "order_charges", "Option 2 - Order Charges Notice"

    tracking_number = models.CharField(max_length=14, unique=True, editable=False, db_index=True)
    from_address = models.TextField()
    to_address = models.TextField()
    item_name = models.CharField(max_length=180, default="General Cargo")
    item_description = models.TextField(blank=True)
    item_quantity = models.PositiveIntegerField(default=1)
    item_weight_kg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    sender_name = models.CharField(max_length=140, blank=True)
    receiver_name = models.CharField(max_length=140, blank=True)
    current_location = models.CharField(max_length=180, blank=True, default="Processing Hub")
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    status = models.CharField(
        max_length=24,
        choices=ShipmentStatus.choices,
        default=ShipmentStatus.PENDING,
    )
    client_notice_option = models.CharField(
        max_length=24,
        choices=NoticeOption.choices,
        default=NoticeOption.DEFAULT_NOTICE,
    )
    hold_active = models.BooleanField(default=False)
    hold_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hold_reason = models.TextField(blank=True)
    hold_message = models.TextField(
        blank=True,
        default=(
            "Your order is currently on hold due to certain applicable charges. Kindly proceed with the "
            "payment to resume processing. Please note that this charge is fully refundable."
        ),
    )
    expected_delivery_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tracking_number} - {self.get_status_display()}"

    @staticmethod
    def _build_tracking_number():
        alphabet = string.ascii_uppercase + string.digits
        suffix = "".join(secrets.choice(alphabet) for _ in range(10))
        return f"SLF{suffix}"

    def save(self, *args, **kwargs):
        if not self.tracking_number:
            candidate = self._build_tracking_number()
            while ShipmentOrder.objects.filter(tracking_number=candidate).exists():
                candidate = self._build_tracking_number()
            self.tracking_number = candidate

        if self.progress_percent > 100:
            self.progress_percent = 100
        if self.status == self.ShipmentStatus.DELIVERED and self.progress_percent < 100:
            self.progress_percent = 100

        if self.hold_active:
            self.status = self.ShipmentStatus.ON_HOLD
            if not self.hold_message:
                self.hold_message = (
                    "Your order is currently on hold due to certain applicable charges. Kindly proceed with the "
                    "payment to resume processing. Please note that this charge is fully refundable."
                )
        else:
            self.hold_amount = None
            self.hold_reason = ""
            self.hold_message = ""
        super().save(*args, **kwargs)

    def place_on_hold(self, amount, reason, message=None):
        self.hold_active = True
        self.hold_amount = amount
        self.hold_reason = reason
        self.hold_message = message or self.hold_message
        self.status = self.ShipmentStatus.ON_HOLD
        self.save(update_fields=["hold_active", "hold_amount", "hold_reason", "hold_message", "status"])

    def release_hold(self):
        self.hold_active = False
        self.status = self.ShipmentStatus.IN_TRANSIT
        self.hold_amount = None
        self.hold_reason = ""
        self.hold_message = ""
        self.save(
            update_fields=[
                "hold_active",
                "status",
                "hold_amount",
                "hold_reason",
                "hold_message",
            ]
        )


class ShipmentReceipt(models.Model):
    location = models.CharField(max_length=180, blank=True, default="")
    device_id = models.CharField(max_length=120, blank=True, default="")
    tid = models.CharField(max_length=120, blank=True, default="")
    item = models.CharField(max_length=200)
    recipient_address = models.CharField(max_length=260)
    recipient_name = models.CharField(max_length=160)
    recipient_number = models.CharField(max_length=90)
    schedule_delivery_date = models.DateField()
    pricing_option = models.CharField(max_length=120, default="Standard rate")
    shipping_subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    custom_charges = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_receipts",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Receipt #{self.id} - {self.recipient_name} ({self.schedule_delivery_date})"

    def save(self, *args, **kwargs):
        if self.total is None:
            try:
                subtotal = Decimal(str(self.shipping_subtotal or "0"))
                custom = Decimal(str(self.custom_charges or "0"))
            except InvalidOperation:
                subtotal = Decimal("0")
                custom = Decimal("0")
            self.total = subtotal + custom
        super().save(*args, **kwargs)
