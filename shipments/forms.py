from django import forms

from .models import ShipmentOrder, ShipmentReceipt


class TrackShipmentForm(forms.Form):
    tracking_number = forms.CharField(
        max_length=20,
        label="Tracking Number",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter your tracking number (e.g. SLF...)",
                "class": "input-field",
            }
        ),
    )

    def clean_tracking_number(self):
        return self.cleaned_data["tracking_number"].strip().upper()


class ShipmentOrderCreateForm(forms.ModelForm):
    class Meta:
        model = ShipmentOrder
        fields = [
            "sender_name",
            "receiver_name",
            "from_address",
            "to_address",
            "item_name",
            "item_description",
            "item_quantity",
            "item_weight_kg",
            "current_location",
            "progress_percent",
            "status",
            "client_notice_option",
            "expected_delivery_date",
        ]
        labels = {
            "client_notice_option": "Important Notice Option (Client Tracking Page)",
        }
        widgets = {
            "sender_name": forms.TextInput(attrs={"class": "input-field", "placeholder": "Sender full name"}),
            "receiver_name": forms.TextInput(attrs={"class": "input-field", "placeholder": "Receiver full name"}),
            "from_address": forms.Textarea(
                attrs={"class": "input-field", "rows": 3, "placeholder": "Origin address"}
            ),
            "to_address": forms.Textarea(
                attrs={"class": "input-field", "rows": 3, "placeholder": "Destination address"}
            ),
            "item_name": forms.TextInput(attrs={"class": "input-field", "placeholder": "e.g. Electronics"}),
            "item_description": forms.Textarea(
                attrs={"class": "input-field", "rows": 3, "placeholder": "What items are in this shipment?"}
            ),
            "item_quantity": forms.NumberInput(attrs={"class": "input-field", "min": 1}),
            "item_weight_kg": forms.NumberInput(
                attrs={"class": "input-field", "step": "0.01", "placeholder": "Weight in kilograms"}
            ),
            "current_location": forms.TextInput(
                attrs={"class": "input-field", "placeholder": "Current shipment location"}
            ),
            "progress_percent": forms.NumberInput(
                attrs={"class": "input-field", "min": 0, "max": 100, "placeholder": "0 to 100"}
            ),
            "status": forms.Select(attrs={"class": "input-field"}),
            "client_notice_option": forms.Select(attrs={"class": "input-field"}),
            "expected_delivery_date": forms.DateInput(attrs={"class": "input-field", "type": "date"}),
        }


class ShipmentOrderEditForm(ShipmentOrderCreateForm):
    """Uses the same editable fields as create form for backend order edits."""


class ShipmentHoldForm(forms.Form):
    hold_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "input-field", "step": "0.01", "placeholder": "Enter charge amount"}),
    )
    hold_reason = forms.CharField(
        widget=forms.Textarea(
            attrs={"class": "input-field", "rows": 2, "placeholder": "Reason for withholding this shipment"}
        )
    )
    hold_message = forms.CharField(
        required=False,
        initial=(
            "Your order is currently on hold due to certain applicable charges. Kindly proceed with the "
            "payment to resume processing. Please note that this charge is fully refundable."
        ),
        widget=forms.Textarea(
            attrs={
                "class": "input-field",
                "rows": 2,
                "placeholder": "Message shown to client on tracking page",
            }
        ),
    )


class ShipmentStatusForm(forms.ModelForm):
    class Meta:
        model = ShipmentOrder
        fields = ["status", "current_location", "expected_delivery_date"]
        widgets = {
            "status": forms.Select(attrs={"class": "input-field"}),
            "current_location": forms.TextInput(attrs={"class": "input-field"}),
            "expected_delivery_date": forms.DateInput(attrs={"class": "input-field", "type": "date"}),
        }


class ShipmentProgressForm(forms.ModelForm):
    class Meta:
        model = ShipmentOrder
        fields = ["progress_percent"]
        widgets = {
            "progress_percent": forms.NumberInput(
                attrs={"class": "input-field slim", "min": 0, "max": 100}
            )
        }


class ShipmentReceiptGeneratorForm(forms.ModelForm):
    class Meta:
        model = ShipmentReceipt
        fields = [
            "location",
            "device_id",
            "tid",
            "item",
            "recipient_address",
            "recipient_name",
            "recipient_number",
            "schedule_delivery_date",
            "pricing_option",
            "shipping_subtotal",
            "custom_charges",
            "total",
        ]
        widgets = {
            "location": forms.TextInput(attrs={"class": "input-field", "placeholder": "e.g. New York Hub"}),
            "device_id": forms.TextInput(attrs={"class": "input-field", "placeholder": "e.g. DEV-4041"}),
            "tid": forms.TextInput(attrs={"class": "input-field", "placeholder": "Transaction ID"}),
            "item": forms.TextInput(attrs={"class": "input-field", "placeholder": "e.g. Apple iPad Pro"}),
            "recipient_address": forms.TextInput(
                attrs={"class": "input-field", "placeholder": "Recipient address as it appears on receipt"}
            ),
            "recipient_name": forms.TextInput(attrs={"class": "input-field", "placeholder": "Recipient full name"}),
            "recipient_number": forms.TextInput(attrs={"class": "input-field", "placeholder": "Recipient phone"}),
            "schedule_delivery_date": forms.DateInput(attrs={"class": "input-field", "type": "date"}),
            "pricing_option": forms.TextInput(attrs={"class": "input-field", "placeholder": "Standard rate"}),
            "shipping_subtotal": forms.NumberInput(attrs={"class": "input-field", "step": "0.01", "min": "0"}),
            "custom_charges": forms.NumberInput(attrs={"class": "input-field", "step": "0.01", "min": "0"}),
            "total": forms.NumberInput(
                attrs={"class": "input-field", "step": "0.01", "min": "0", "placeholder": "Auto if left blank"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].required = False
        self.fields["device_id"].required = False
        self.fields["tid"].required = False
        self.fields["total"].required = False
