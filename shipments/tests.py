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
            username="smithlinda99360@gmail.com",
            email="smithlinda99360@gmail.com",
            password="Admin2026",
        )

    def test_login_and_dashboard_access(self):
        logged_in = self.client.login(username=self.user.username, password="Admin2026")
        self.assertTrue(logged_in)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_progress_can_be_updated_from_backend(self):
        order = ShipmentOrder.objects.create(from_address="A", to_address="B")
        self.client.login(username=self.user.username, password="Admin2026")
        response = self.client.post(
            reverse("update_progress", kwargs={"order_id": order.id}),
            {"progress_percent": 75},
        )
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.progress_percent, 75)
