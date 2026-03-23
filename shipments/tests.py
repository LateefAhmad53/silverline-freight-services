from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import ShipmentOrder


class ShipmentOrderModelTests(TestCase):
    def test_tracking_number_is_generated(self):
        order = ShipmentOrder.objects.create(from_address="A", to_address="B")
        self.assertTrue(order.tracking_number.startswith("SLF"))
        self.assertEqual(len(order.tracking_number), 13)

    def test_place_hold_and_release(self):
        order = ShipmentOrder.objects.create(from_address="A", to_address="B")
        order.place_on_hold(amount=50, reason="Additional charge")
        order.refresh_from_db()
        self.assertTrue(order.hold_active)
        self.assertEqual(order.status, ShipmentOrder.ShipmentStatus.ON_HOLD)
        order.release_hold()
        order.refresh_from_db()
        self.assertFalse(order.hold_active)
        self.assertEqual(order.status, ShipmentOrder.ShipmentStatus.IN_TRANSIT)

    def test_delivered_status_forces_full_progress(self):
        order = ShipmentOrder.objects.create(
            from_address="A",
            to_address="B",
            status=ShipmentOrder.ShipmentStatus.DELIVERED,
            progress_percent=40,
        )
        order.refresh_from_db()
        self.assertEqual(order.progress_percent, 100)


class TrackingViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_tracking_page_loads(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

    def test_tracking_result_displays_order(self):
        order = ShipmentOrder.objects.create(
            from_address="A",
            to_address="B",
            item_name="Mobile Phones",
            item_description="12 sealed cartons",
            item_quantity=12,
        )
        response = self.client.get(reverse("home"), {"tracking_number": order.tracking_number})
        self.assertContains(response, order.tracking_number)
        self.assertContains(response, "Mobile Phones")
        self.assertContains(response, "Live Delivery Progress")

    def test_services_page_loads(self):
        response = self.client.get(reverse("services"))
        self.assertEqual(response.status_code, 200)


class BackendAuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="TestPass123!",
        )
        self.order = ShipmentOrder.objects.create(
            from_address="Lagos",
            to_address="Abuja",
            item_name="Office Chairs",
            item_quantity=20,
        )

    def test_login_and_dashboard_access(self):
        logged_in = self.client.login(username=self.user.username, password="TestPass123!")
        self.assertTrue(logged_in)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("chart_labels", response.context)
        self.assertIn("chart_values", response.context)

    def test_progress_can_be_updated_from_backend(self):
        self.client.login(username=self.user.username, password="TestPass123!")
        response = self.client.post(
            reverse("update_progress", kwargs={"order_id": self.order.id}),
            {"progress_percent": 75},
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.progress_percent, 75)

    def test_dashboard_search_filters_by_tracking_number(self):
        self.client.login(username=self.user.username, password="TestPass123!")
        response = self.client.get(reverse("dashboard"), {"tracking": self.order.tracking_number})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.tracking_number)

    def test_edit_order_updates_item_name(self):
        self.client.login(username=self.user.username, password="TestPass123!")
        response = self.client.post(
            reverse("edit_order", kwargs={"order_id": self.order.id}),
            {
                "sender_name": self.order.sender_name,
                "receiver_name": self.order.receiver_name,
                "from_address": self.order.from_address,
                "to_address": self.order.to_address,
                "item_name": "Updated Chairs",
                "item_description": self.order.item_description,
                "item_quantity": self.order.item_quantity,
                "item_weight_kg": self.order.item_weight_kg or "",
                "current_location": self.order.current_location,
                "progress_percent": self.order.progress_percent,
                "status": self.order.status,
                "expected_delivery_date": self.order.expected_delivery_date or "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.item_name, "Updated Chairs")

    def test_delete_order_removes_record(self):
        self.client.login(username=self.user.username, password="TestPass123!")
        response = self.client.post(reverse("delete_order", kwargs={"order_id": self.order.id}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ShipmentOrder.objects.filter(id=self.order.id).exists())
