from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .models import (
    DeliveryConfirmation,
    Organization,
    FoodCategory,
    FoodListing,
    Pickup,
    Reservation,
    Courier,
)
from .services import reserve_listing, transition_pickup


class WorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="recipient", password="safe-password")
        self.partner = Organization.objects.create(
            name="Green Bowl Kitchen",
            organization_type="RESTAURANT",
            contact_person="Ops",
            email="partner@example.test",
            verification_status="APPROVED",
        )
        self.recipient = Organization.objects.create(
            name="Community Kitchen A",
            organization_type="COMMUNITY_KITCHEN",
            contact_person="Coordinator",
            email="recipient@example.test",
            verification_status="APPROVED",
        )
        self.recipient.members.create(user=self.user, role="RECIPIENT")
        self.category = FoodCategory.objects.create(name="Cooked Meals")
        now = timezone.now()
        self.listing = FoodListing.objects.create(
            organization=self.partner,
            category=self.category,
            name="Vegetable Rice",
            quantity_listed=20,
            unit="PORTIONS",
            servings=20,
            preparation_at=now,
            available_from=now,
            available_until=now + timedelta(hours=2),
            storage_condition="HOT_HOLD",
            status="PUBLISHED",
        )


    def _advance_to_delivered(self, pickup, courier_user, quantity):
        for step in ["ACCEPTED", "EN_ROUTE", "ARRIVED"]:
            transition_pickup(
                pickup_id=pickup.id,
                to_status=step,
                user=courier_user,
            )
        transition_pickup(
            pickup_id=pickup.id,
            to_status="COLLECTED",
            user=courier_user,
            collected_quantity=quantity,
        )
        transition_pickup(
            pickup_id=pickup.id,
            to_status="DELIVERED",
            user=courier_user,
            delivered_quantity=quantity,
        )

    def test_reservation_cannot_overbook(self):
        reservation = reserve_listing(
            listing_id=self.listing.id,
            organization=self.recipient,
            user=self.user,
            quantity=15,
            start=self.listing.available_from,
            end=self.listing.available_until,
        )
        self.assertEqual(reservation.quantity, 15)
        self.assertEqual(self.listing.__class__.objects.get(pk=self.listing.pk).quantity_reserved, 15)
        with self.assertRaises(ValueError):
            reserve_listing(
                listing_id=self.listing.id,
                organization=self.recipient,
                user=self.user,
                quantity=6,
                start=self.listing.available_from,
                end=self.listing.available_until,
            )

    def test_pickup_workflow_requires_valid_transitions(self):
        reservation = reserve_listing(
            listing_id=self.listing.id,
            organization=self.recipient,
            user=self.user,
            quantity=5,
            start=self.listing.available_from,
            end=self.listing.available_until,
        )
        courier_user = User.objects.create_user(username="courier", password="safe-password")
        courier = Courier.objects.create(user=courier_user)
        pickup = Pickup.objects.create(
            reservation=reservation,
            courier=courier,
            source=self.partner,
            destination=self.recipient,
            expected_quantity=5,
            window_start=self.listing.available_from,
            window_end=self.listing.available_until,
        )

        with self.assertRaises(ValueError):
            transition_pickup(
                pickup_id=pickup.id,
                to_status="DELIVERED",
                user=courier_user,
            )

        for step in ["ACCEPTED", "EN_ROUTE", "ARRIVED"]:
            transition_pickup(pickup_id=pickup.id, to_status=step, user=courier_user)

        transition_pickup(
            pickup_id=pickup.id,
            to_status="COLLECTED",
            user=courier_user,
            collected_quantity=5,
        )
        transition_pickup(
            pickup_id=pickup.id,
            to_status="DELIVERED",
            user=courier_user,
            delivered_quantity=5,
        )
        transition_pickup(
            pickup_id=pickup.id,
            to_status="COMPLETED",
            user=courier_user,
        )

        pickup.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(pickup.status, "COMPLETED")
        self.assertEqual(reservation.status, "COMPLETED")
        self.assertEqual(DeliveryConfirmation.objects.count(), 0)


    def test_reservation_cannot_be_cancelled_after_collection(self):
        reservation = reserve_listing(
            listing_id=self.listing.id,
            organization=self.recipient,
            user=self.user,
            quantity=5,
            start=self.listing.available_from,
            end=self.listing.available_until,
        )
        courier_user = User.objects.create_user(username="courier_cancel", password="safe-password")
        courier = Courier.objects.create(user=courier_user)
        pickup = Pickup.objects.create(
            reservation=reservation,
            courier=courier,
            source=self.partner,
            destination=self.recipient,
            expected_quantity=5,
            window_start=self.listing.available_from,
            window_end=self.listing.available_until,
        )
        self._advance_to_delivered(pickup, courier_user, 5)

        from .services import cancel_reservation
        with self.assertRaises(ValueError):
            cancel_reservation(reservation_id=reservation.id, user=self.user)

    def test_delivery_confirmation_is_created_only_by_recipient(self):
        reservation = reserve_listing(
            listing_id=self.listing.id,
            organization=self.recipient,
            user=self.user,
            quantity=5,
            start=self.listing.available_from,
            end=self.listing.available_until,
        )
        courier_user = User.objects.create_user(username="courier_delivery", password="safe-password")
        courier = Courier.objects.create(user=courier_user)
        pickup = Pickup.objects.create(
            reservation=reservation,
            courier=courier,
            source=self.partner,
            destination=self.recipient,
            expected_quantity=5,
            window_start=self.listing.available_from,
            window_end=self.listing.available_until,
        )
        self._advance_to_delivered(pickup, courier_user, 5)

        self.assertEqual(DeliveryConfirmation.objects.count(), 0)

        self.client.force_login(self.user)
        response = self.client.post(f"/pickups/{pickup.id}/confirm/")
        self.assertEqual(response.status_code, 302)

        pickup.refresh_from_db()
        self.assertEqual(pickup.status, "COMPLETED")
        self.assertEqual(DeliveryConfirmation.objects.count(), 1)

    def test_multi_pickup_listing_does_not_complete_early(self):
        second_user = User.objects.create_user(username="recipient2", password="safe-password")
        self.recipient.members.create(user=second_user, role="RECIPIENT")

        first = reserve_listing(
            listing_id=self.listing.id,
            organization=self.recipient,
            user=self.user,
            quantity=5,
            start=self.listing.available_from,
            end=self.listing.available_until,
        )
        second = reserve_listing(
            listing_id=self.listing.id,
            organization=self.recipient,
            user=second_user,
            quantity=5,
            start=self.listing.available_from,
            end=self.listing.available_until,
        )

        courier_user_one = User.objects.create_user(username="courier_one", password="safe-password")
        courier_user_two = User.objects.create_user(username="courier_two", password="safe-password")
        courier_one = Courier.objects.create(user=courier_user_one)
        courier_two = Courier.objects.create(user=courier_user_two)

        pickup_one = Pickup.objects.create(
            reservation=first,
            courier=courier_one,
            source=self.partner,
            destination=self.recipient,
            expected_quantity=5,
            window_start=self.listing.available_from,
            window_end=self.listing.available_until,
        )
        pickup_two = Pickup.objects.create(
            reservation=second,
            courier=courier_two,
            source=self.partner,
            destination=self.recipient,
            expected_quantity=5,
            window_start=self.listing.available_from,
            window_end=self.listing.available_until,
        )

        self._advance_to_delivered(pickup_one, courier_user_one, 5)
        transition_pickup(pickup_id=pickup_one.id, to_status="COMPLETED", user=courier_user_one)

        self.listing.refresh_from_db()
        self.assertNotEqual(self.listing.status, "COMPLETED")

        self._advance_to_delivered(pickup_two, courier_user_two, 5)
        transition_pickup(pickup_id=pickup_two.id, to_status="COMPLETED", user=courier_user_two)

        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, "PUBLISHED")
        self.assertEqual(self.listing.remaining, 10)

    def test_full_listing_is_not_shown_as_available(self):
        self.listing.status = "FULL"
        self.listing.quantity_reserved = self.listing.quantity_listed
        self.listing.save(update_fields=["status", "quantity_reserved", "updated_at"])

        self.client.force_login(self.user)
        response = self.client.get("/listings/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.listing.name)
