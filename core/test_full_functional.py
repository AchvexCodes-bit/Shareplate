from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Address,
    AuditLog,
    Complaint,
    Courier,
    DeliveryConfirmation,
    FoodCategory,
    FoodListing,
    ImpactRecord,
    Membership,
    Notification,
    Organization,
    Pickup,
    PickupStatusHistory,
    Reservation,
    SavedFood,
)
from .services import (
    cancel_reservation,
    notify,
    reserve_listing,
    transition_pickup,
)


class FullFunctionalTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.partner_user = User.objects.create_user(
            username="partner", password="safe-password", first_name="Partner"
        )
        self.recipient_user = User.objects.create_user(
            username="recipient_full", password="safe-password", first_name="Recipient"
        )
        self.courier_user = User.objects.create_user(
            username="courier_full", password="safe-password", first_name="Courier"
        )
        self.admin_user = User.objects.create_user(
            username="admin_full", password="safe-password", is_staff=True
        )
        self.superuser = User.objects.create_superuser(
            username="root_full", password="safe-password", email="root@example.test"
        )

        self.partner = Organization.objects.create(
            name="Partner Kitchen",
            organization_type="RESTAURANT",
            contact_person="Partner",
            email="partner-full@example.test",
            verification_status="APPROVED",
            active=True,
        )
        self.recipient = Organization.objects.create(
            name="Recipient Kitchen",
            organization_type="COMMUNITY_KITCHEN",
            contact_person="Recipient",
            email="recipient-full@example.test",
            verification_status="APPROVED",
            active=True,
        )
        self.pending_org = Organization.objects.create(
            name="Pending Bakery",
            organization_type="BAKERY",
            contact_person="Pending",
            email="pending-full@example.test",
            verification_status="PENDING",
            active=True,
        )

        Membership.objects.create(
            user=self.partner_user, organization=self.partner, role="FOOD_PARTNER"
        )
        Membership.objects.create(
            user=self.recipient_user, organization=self.recipient, role="RECIPIENT"
        )
        Membership.objects.create(
            user=self.courier_user, organization=self.partner, role="COURIER"
        )
        Membership.objects.create(
            user=self.admin_user, organization=self.partner, role="ADMIN"
        )

        self.category = FoodCategory.objects.create(name="Prepared Meals")
        FoodCategory.objects.create(name="Bakery", active=False)

        self.listing = self.make_listing()
        self.courier = Courier.objects.create(
            user=self.courier_user, vehicle_details="Bike TEST-01", active=True
        )

    def make_listing(self, **overrides):
        defaults = {
            "organization": self.partner,
            "category": self.category,
            "name": "Veg Meals",
            "description": "Fresh meals",
            "quantity_listed": 20,
            "quantity_reserved": 0,
            "quantity_collected": 0,
            "unit": "PORTIONS",
            "servings": 2,
            "preparation_at": self.now - timedelta(hours=1),
            "available_from": self.now - timedelta(minutes=10),
            "available_until": self.now + timedelta(hours=4),
            "storage_condition": "HOT_HOLD",
            "status": "PUBLISHED",
        }
        defaults.update(overrides)
        return FoodListing.objects.create(**defaults)

    def make_reservation(self, quantity=5, user=None):
        user = user or self.recipient_user
        return reserve_listing(
            listing_id=self.listing.id,
            organization=self.recipient,
            user=user,
            quantity=quantity,
            start=self.listing.available_from,
            end=self.listing.available_until,
        )

    def make_pickup(self, reservation=None, status="ASSIGNED", courier=None):
        reservation = reservation or self.make_reservation()
        return Pickup.objects.create(
            reservation=reservation,
            courier=courier or self.courier,
            source=self.partner,
            destination=self.recipient,
            status=status,
            window_start=reservation.collection_window_start,
            window_end=reservation.collection_window_end,
            expected_quantity=reservation.quantity,
        )

    def advance_to(self, pickup, status):
        steps = {
            "ACCEPTED": ["ACCEPTED"],
            "EN_ROUTE": ["ACCEPTED", "EN_ROUTE"],
            "ARRIVED": ["ACCEPTED", "EN_ROUTE", "ARRIVED"],
        }
        for step in steps.get(status, []):
            transition_pickup(
                pickup_id=pickup.id,
                to_status=step,
                user=self.courier_user,
            )

    def test_model_helpers_and_constraints(self):
        self.assertTrue(self.listing.reference.startswith("SP-L-"))
        self.assertEqual(self.listing.remaining, 20)
        self.assertEqual(str(self.listing), f"{self.listing.name} ({self.listing.reference})")

        Address.objects.create(
            organization=self.partner,
            line1="MG Road",
            city="Kochi",
            state="Kerala",
            postal_code="682001",
        )
        SavedFood.objects.create(
            organization=self.partner,
            category=self.category,
            name="Meal Box",
            unit="BOXES",
        )
        with self.assertRaises(IntegrityError):
            Membership.objects.create(
                user=self.partner_user,
                organization=self.partner,
                role="FOOD_PARTNER",
            )

    def test_authentication_and_login_required_routes(self):
        protected = [
            "dashboard",
            "listings",
            "notifications",
            "impact",
            "courier",
            "impact_api",
        ]
        for name in protected:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn("/login/", response.url)

        response = self.client.post(
            reverse("login"),
            {"username": "recipient_full", "password": "safe-password"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))

        logout_response = self.client.post(reverse("logout"))
        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(logout_response.url, reverse("login"))

    def test_role_resolution_and_dashboard_pages(self):
        from .views import user_org, user_role

        self.assertEqual(user_role(self.recipient_user), "RECIPIENT")
        self.assertEqual(user_role(self.courier_user), "COURIER")
        self.assertEqual(user_role(self.partner_user), "FOOD_PARTNER")
        self.assertEqual(user_role(self.admin_user), "ADMIN")
        self.assertEqual(user_role(self.superuser), "ADMIN")
        self.assertEqual(user_org(self.recipient_user), self.recipient)

        for user in (
            self.partner_user,
            self.recipient_user,
            self.courier_user,
            self.admin_user,
            self.superuser,
        ):
            self.client.force_login(user)
            response = self.client.get(reverse("dashboard"))
            self.assertEqual(response.status_code, 200)

    def test_listings_search_and_visibility(self):
        self.listing.description = "Special rice and curry"
        self.listing.save(update_fields=["description", "updated_at"])
        self.client.force_login(self.recipient_user)

        self.assertEqual(self.client.get(reverse("listings")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("listings"), {"q": "rice"}).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("listings"), {"q": "Prepared Meals"}).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("listings"), {"q": self.partner.name}).status_code, 200
        )

        full = self.make_listing(
            name="Full Meals",
            reference="SP-L-FULLTEST1",
            quantity_reserved=10,
            quantity_listed=10,
            status="FULL",
        )
        response = self.client.get(reverse("listings"))
        self.assertNotContains(response, full.name)

        expired = self.make_listing(
            name="Expired Meals",
            reference="SP-L-EXPIRED1",
            available_until=self.now - timedelta(minutes=1),
            status="PUBLISHED",
        )
        response = self.client.get(reverse("listings"))
        self.assertNotContains(response, expired.name)

    def test_create_listing_validation_and_success(self):
        self.client.force_login(self.partner_user)

        get_response = self.client.get(reverse("create_listing"))
        self.assertEqual(get_response.status_code, 302)

        bad = self.client.post(
            reverse("create_listing"),
            {
                "name": "",
                "category": self.category.id,
                "quantity_listed": "0",
                "servings": "0",
                "unit": "INVALID",
                "storage_condition": "INVALID",
                "available_from": "",
                "available_until": "",
            },
            follow=True,
        )
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, "Listing could not be created")

        inactive_category = FoodCategory.objects.create(name="Closed Category", active=False)
        local_now = timezone.localtime(self.now)
        valid_data = {
            "name": "New Meal Batch",
            "category": inactive_category.id,
            "quantity_listed": "12",
            "servings": "2",
            "unit": "PORTIONS",
            "storage_condition": "HOT_HOLD",
            "preparation_at": (local_now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M"),
            "available_from": local_now.strftime("%Y-%m-%dT%H:%M"),
            "available_until": (local_now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
        }
        denied = self.client.post(reverse("create_listing"), valid_data, follow=True)
        self.assertContains(denied, "Listing could not be created")

        valid_data["category"] = self.category.id
        success = self.client.post(reverse("create_listing"), valid_data, follow=True)
        self.assertEqual(success.status_code, 200)
        self.assertTrue(
            FoodListing.objects.filter(name="New Meal Batch", organization=self.partner).exists()
        )

    def test_listing_actions_permissions_and_cancel(self):
        self.client.force_login(self.recipient_user)
        forbidden = self.client.post(
            reverse("listing_action", args=[self.listing.id, "cancel"])
        )
        self.assertEqual(forbidden.status_code, 403)

        self.client.force_login(self.partner_user)
        self.assertEqual(
            self.client.get(
                reverse("listing_action", args=[self.listing.id, "cancel"])
            ).status_code,
            400,
        )

        ok = self.client.post(
            reverse("listing_action", args=[self.listing.id, "cancel"])
        )
        self.assertEqual(ok.status_code, 302)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, "CANCELLED")

        unknown = self.client.post(
            reverse("listing_action", args=[self.listing.id, "unknown"])
        )
        self.assertEqual(unknown.status_code, 400)

    def test_reservation_creation_notifications_and_inventory(self):
        self.client.force_login(self.recipient_user)
        response = self.client.post(
            reverse("reserve", args=[self.listing.id]),
            {"quantity": "4"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity_reserved, 4)
        self.assertEqual(Notification.objects.filter(user=self.partner_user).count(), 1)

        own_listing = self.make_listing(
            organization=self.recipient,
            name="Recipient Own Listing",
            reference="SP-L-OWNTEST1",
        )
        forbidden = self.client.post(
            reverse("reserve", args=[own_listing.id]),
            {"quantity": "1"},
        )
        self.assertEqual(forbidden.status_code, 302)
        self.assertEqual(Reservation.objects.filter(listing=own_listing).count(), 0)

    def test_reservation_window_validation_and_inactive_recipient(self):
        inactive = Organization.objects.create(
            name="Inactive Recipient",
            organization_type="NGO",
            contact_person="Inactive",
            email="inactive@example.test",
            verification_status="APPROVED",
            active=False,
        )
        with self.assertRaises(ValueError):
            reserve_listing(
                listing_id=self.listing.id,
                organization=inactive,
                user=self.recipient_user,
                quantity=1,
                start=self.listing.available_from,
                end=self.listing.available_until,
            )

        with self.assertRaises(ValueError):
            reserve_listing(
                listing_id=self.listing.id,
                organization=self.recipient,
                user=self.recipient_user,
                quantity=1,
                start=self.listing.available_from - timedelta(minutes=5),
                end=self.listing.available_until,
            )

        future_listing = self.make_listing(
            name="Future Food",
            reference="SP-L-FUTURE1",
            available_from=self.now + timedelta(hours=1),
            available_until=self.now + timedelta(hours=3),
        )
        with self.assertRaises(ValueError):
            reserve_listing(
                listing_id=future_listing.id,
                organization=self.recipient,
                user=self.recipient_user,
                quantity=1,
                start=future_listing.available_from,
                end=future_listing.available_until,
            )

    def test_reservation_actions_accept_reject_permissions_and_idempotency(self):
        reservation = self.make_reservation(quantity=3)
        self.client.force_login(self.partner_user)

        self.assertEqual(
            self.client.get(
                reverse("reservation_action", args=[reservation.id, "accept"])
            ).status_code,
            400,
        )
        accept = self.client.post(
            reverse("reservation_action", args=[reservation.id, "accept"])
        )
        self.assertEqual(accept.status_code, 302)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, "ACCEPTED")
        self.assertEqual(Pickup.objects.filter(reservation=reservation).count(), 1)

        second_accept = self.client.post(
            reverse("reservation_action", args=[reservation.id, "accept"])
        )
        self.assertEqual(second_accept.status_code, 302)
        self.assertEqual(Pickup.objects.filter(reservation=reservation).count(), 1)

        reservation2 = self.make_reservation(quantity=2)
        reject = self.client.post(
            reverse("reservation_action", args=[reservation2.id, "reject"])
        )
        self.assertEqual(reject.status_code, 302)
        reservation2.refresh_from_db()
        self.assertEqual(reservation2.status, "REJECTED")

        self.client.force_login(self.recipient_user)
        forbidden = self.client.post(
            reverse("reservation_action", args=[reservation.id, "reject"])
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_cancel_reservation_permissions_and_pickup_cancellation(self):
        reservation = self.make_reservation(quantity=2)
        self.client.force_login(self.partner_user)
        forbidden = self.client.post(
            reverse("cancel_reservation", args=[reservation.id])
        )
        self.assertEqual(forbidden.status_code, 302)

        self.client.force_login(self.recipient_user)
        cancelled = self.client.post(
            reverse("cancel_reservation", args=[reservation.id])
        )
        self.assertEqual(cancelled.status_code, 302)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, "CANCELLED")

        reservation2 = self.make_reservation(quantity=3)
        pickup = self.make_pickup(reservation2)
        reservation2.status = "PICKUP"
        reservation2.save(update_fields=["status", "updated_at"])
        self.client.post(reverse("cancel_reservation", args=[reservation2.id]))
        pickup.refresh_from_db()
        reservation2.refresh_from_db()
        self.assertEqual(pickup.status, "CANCELLED")
        self.assertEqual(reservation2.status, "CANCELLED")

    def test_cancel_reservation_rejected_after_progress(self):
        reservation = self.make_reservation(quantity=3)
        pickup = self.make_pickup(reservation)
        reservation.status = "PICKUP"
        reservation.save(update_fields=["status"])
        transition_pickup(
            pickup_id=pickup.id, to_status="ACCEPTED", user=self.courier_user
        )
        transition_pickup(
            pickup_id=pickup.id, to_status="EN_ROUTE", user=self.courier_user
        )
        with self.assertRaises(ValueError):
            cancel_reservation(reservation_id=reservation.id, user=self.recipient_user)

    def test_full_courier_state_machine_and_history(self):
        reservation = self.make_reservation(quantity=5)
        pickup = self.make_pickup(reservation)

        self.client.force_login(self.courier_user)
        actions = [
            ("accepted", "ACCEPTED"),
            ("en_route", "EN_ROUTE"),
            ("arrived", "ARRIVED"),
        ]
        for action, expected in actions:
            response = self.client.post(
                reverse("pickup_action", args=[pickup.id, action])
            )
            self.assertEqual(response.status_code, 302)
            pickup.refresh_from_db()
            self.assertEqual(pickup.status, expected)

        collected = self.client.post(
            reverse("pickup_action", args=[pickup.id, "collect"]),
            {"quantity": "4"},
        )
        self.assertEqual(collected.status_code, 302)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, "COLLECTED")
        self.assertEqual(pickup.collected_quantity, 4)

        delivered = self.client.post(
            reverse("pickup_action", args=[pickup.id, "deliver"]),
            {"quantity": "4", "notes": "Received by coordinator"},
        )
        self.assertEqual(delivered.status_code, 302)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, "DELIVERED")
        self.assertEqual(pickup.delivered_quantity, 4)
        self.assertEqual(DeliveryConfirmation.objects.count(), 0)

        self.assertGreaterEqual(PickupStatusHistory.objects.filter(pickup=pickup).count(), 5)

    def test_courier_issue_reschedule_and_reopen(self):
        pickup = self.make_pickup()
        self.client.force_login(self.courier_user)

        self.client.post(
            reverse("pickup_action", args=[pickup.id, "accepted"])
        )
        self.client.post(
            reverse("pickup_action", args=[pickup.id, "issue"]),
            {"notes": "Vehicle problem"},
        )
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, "ISSUE")
        self.assertEqual(pickup.issue_notes, "Vehicle problem")

        self.client.post(
            reverse("pickup_action", args=[pickup.id, "assigned"])
        )
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, "ASSIGNED")

        self.client.post(
            reverse("pickup_action", args=[pickup.id, "rescheduled"])
        )
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, "RESCHEDULED")

        self.client.post(
            reverse("pickup_action", args=[pickup.id, "assigned"])
        )
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, "ASSIGNED")

    def test_courier_permission_and_validation_failures(self):
        pickup = self.make_pickup()

        self.client.force_login(self.partner_user)
        forbidden = self.client.post(
            reverse("pickup_action", args=[pickup.id, "accepted"])
        )
        self.assertEqual(forbidden.status_code, 403)

        self.client.force_login(self.courier_user)
        get_response = self.client.get(
            reverse("pickup_action", args=[pickup.id, "accepted"])
        )
        self.assertEqual(get_response.status_code, 400)

        self.client.post(
            reverse("pickup_action", args=[pickup.id, "accepted"])
        )
        self.client.post(
            reverse("pickup_action", args=[pickup.id, "en_route"])
        )
        invalid = self.client.post(
            reverse("pickup_action", args=[pickup.id, "collect"]),
            {"quantity": "0"},
        )
        self.assertEqual(invalid.status_code, 302)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, "EN_ROUTE")

    def test_courier_dashboard_requires_profile(self):
        no_profile = User.objects.create_user(
            username="no_courier", password="safe-password"
        )
        Membership.objects.create(
            user=no_profile, organization=self.partner, role="COURIER"
        )
        self.client.force_login(no_profile)
        response = self.client.get(reverse("courier"))
        self.assertEqual(response.status_code, 403)

    def test_recipient_delivery_confirmation_and_permissions(self):
        reservation = self.make_reservation(quantity=5)
        pickup = self.make_pickup(reservation)
        self.advance_to(pickup, "ARRIVED")
        transition_pickup(
            pickup_id=pickup.id,
            to_status="COLLECTED",
            user=self.courier_user,
            collected_quantity=5,
        )
        transition_pickup(
            pickup_id=pickup.id,
            to_status="DELIVERED",
            user=self.courier_user,
            delivered_quantity=5,
        )

        self.client.force_login(self.partner_user)
        self.assertEqual(
            self.client.post(reverse("confirm_delivery", args=[pickup.id])).status_code,
            403,
        )

        self.client.force_login(self.recipient_user)
        response = self.client.post(reverse("confirm_delivery", args=[pickup.id]))
        self.assertEqual(response.status_code, 302)

        pickup.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(pickup.status, "COMPLETED")
        self.assertEqual(reservation.status, "COMPLETED")
        self.assertEqual(DeliveryConfirmation.objects.count(), 1)
        self.assertEqual(ImpactRecord.objects.count(), 1)

        repeat = self.client.post(reverse("confirm_delivery", args=[pickup.id]))
        self.assertEqual(repeat.status_code, 302)

    def test_confirm_delivery_requires_delivered_state(self):
        pickup = self.make_pickup()
        self.client.force_login(self.recipient_user)
        response = self.client.post(reverse("confirm_delivery", args=[pickup.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "must mark the pickup as delivered")

    def test_admin_organization_actions_and_notifications(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("admin_organization_action", args=[self.pending_org.id, "approve"])
        )
        self.assertEqual(response.status_code, 302)
        self.pending_org.refresh_from_db()
        self.assertEqual(self.pending_org.verification_status, "APPROVED")
        self.assertTrue(self.pending_org.active)

        new_pending = Organization.objects.create(
            name="Second Pending",
            organization_type="NGO",
            contact_person="Second",
            email="second-pending@example.test",
        )
        org_user = User.objects.create_user(username="second_member")
        Membership.objects.create(user=org_user, organization=new_pending, role="RECIPIENT")

        self.client.post(
            reverse("admin_organization_action", args=[new_pending.id, "reject"])
        )
        new_pending.refresh_from_db()
        self.assertEqual(new_pending.verification_status, "REJECTED")
        self.assertFalse(new_pending.active)
        self.assertTrue(Notification.objects.filter(user=org_user).exists())

        bad = self.client.post(
            reverse("admin_organization_action", args=[new_pending.id, "unknown"])
        )
        self.assertEqual(bad.status_code, 400)

    def test_admin_assign_pickup_validation(self):
        reservation = self.make_reservation(quantity=2)
        pickup = self.make_pickup(reservation)

        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse("admin_assign_pickup", args=[pickup.id]),
            {"courier": self.courier.id},
        )
        self.assertEqual(response.status_code, 302)
        pickup.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(pickup.status, "ASSIGNED")
        self.assertEqual(pickup.courier_id, self.courier.id)
        self.assertEqual(reservation.status, "PICKUP")

        pickup.status = "EN_ROUTE"
        pickup.save(update_fields=["status"])
        blocked = self.client.post(
            reverse("admin_assign_pickup", args=[pickup.id]),
            {"courier": self.courier.id},
        )
        self.assertEqual(blocked.status_code, 302)

        inactive_courier = Courier.objects.create(
            user=User.objects.create_user(username="inactive_courier"),
            active=False,
        )
        pickup.status = "ASSIGNED"
        pickup.save(update_fields=["status"])
        invalid = self.client.post(
            reverse("admin_assign_pickup", args=[pickup.id]),
            {"courier": inactive_courier.id},
        )
        self.assertEqual(invalid.status_code, 302)
        pickup.refresh_from_db()
        self.assertEqual(pickup.courier_id, self.courier.id)

    def test_complaint_create_and_admin_lifecycle(self):
        self.client.force_login(self.recipient_user)
        empty = self.client.post(
            reverse("complaint_create"),
            {"category": "", "description": ""},
        )
        self.assertEqual(empty.status_code, 302)
        self.assertEqual(Complaint.objects.count(), 0)

        created = self.client.post(
            reverse("complaint_create"),
            {"category": "Pickup issue", "description": "Courier delayed"},
        )
        self.assertEqual(created.status_code, 302)
        complaint = Complaint.objects.get()
        self.assertEqual(complaint.status, "OPEN")
        self.assertEqual(complaint.organization, self.recipient)

        forbidden = self.client.post(
            reverse("complaint_action", args=[complaint.id, "RESOLVED"]),
            {"response": "No"},
        )
        self.assertEqual(forbidden.status_code, 403)

        self.client.force_login(self.admin_user)
        in_review = self.client.post(
            reverse("complaint_action", args=[complaint.id, "IN_REVIEW"]),
            {"response": "Investigating"},
        )
        self.assertEqual(in_review.status_code, 302)

        resolved = self.client.post(
            reverse("complaint_action", args=[complaint.id, "RESOLVED"]),
            {"response": "Resolved after review"},
        )
        self.assertEqual(resolved.status_code, 302)
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, "RESOLVED")
        self.assertEqual(complaint.resolution, "Resolved after review")

        bad = self.client.post(
            reverse("complaint_action", args=[complaint.id, "UNKNOWN"]),
            {"response": "x"},
        )
        self.assertEqual(bad.status_code, 400)

    def test_notifications_are_marked_read_and_notify_helper(self):
        notify(self.recipient_user, "Test notification", "Hello", "test", 123)
        self.client.force_login(self.recipient_user)
        response = self.client.get(reverse("notifications"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test notification")
        self.assertFalse(
            Notification.objects.filter(user=self.recipient_user, read_at__isnull=True).exists()
        )

    def test_impact_page_and_api(self):
        reservation = self.make_reservation(quantity=2)
        pickup = self.make_pickup(reservation)
        ImpactRecord.objects.create(
            organization=self.partner,
            pickup=pickup,
            portions=4,
            weight_kg="2.50",
        )
        self.client.force_login(self.recipient_user)
        page = self.client.get(reverse("impact"))
        self.assertEqual(page.status_code, 200)
        api = self.client.get(reverse("impact_api"))
        self.assertEqual(api.status_code, 200)
        data = api.json()
        self.assertEqual(data["pickups"], 1)
        self.assertEqual(float(data["weight"]), 2.5)
        self.assertEqual(data["portions"], 4)

    def test_admin_site_is_accessible_to_staff_and_protected_from_normal_user(self):
        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.recipient_user)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)

    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo")
        first_users = User.objects.filter(username__startswith="demo_").count()
        first_orgs = Organization.objects.filter(email__endswith="@shareplate.demo").count()
        first_listings = FoodListing.objects.filter(organization__email="donor@shareplate.demo").count()

        call_command("seed_demo")
        self.assertEqual(
            User.objects.filter(username__startswith="demo_").count(),
            first_users,
        )
        self.assertEqual(
            Organization.objects.filter(email__endswith="@shareplate.demo").count(),
            first_orgs,
        )
        self.assertEqual(
            FoodListing.objects.filter(organization__email="donor@shareplate.demo").count(),
            first_listings,
        )

    def test_service_transition_permissions_and_notify(self):
        reservation = self.make_reservation(quantity=2)
        pickup = self.make_pickup(reservation)
        stranger = User.objects.create_user(username="stranger", password="safe-password")

        with self.assertRaises(PermissionError):
            transition_pickup(
                pickup_id=pickup.id,
                to_status="ACCEPTED",
                user=stranger,
            )

        with self.assertRaises(ValueError):
            transition_pickup(
                pickup_id=pickup.id,
                to_status="ARRIVED",
                user=self.courier_user,
            )

        notification = notify(
            self.partner_user, "Manual notice", "Body", "pickup", pickup.id
        )
        self.assertEqual(notification.user, self.partner_user)
        self.assertEqual(notification.related_id, str(pickup.id))
