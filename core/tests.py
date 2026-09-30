from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from .models import Organization, FoodCategory, FoodListing, Pickup, Reservation, Courier
from .services import reserve_listing, transition_pickup

class WorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='recipient', password='safe-password')
        self.partner = Organization.objects.create(name='Green Bowl Kitchen', organization_type='RESTAURANT', contact_person='Ops', email='partner@example.test', verification_status='APPROVED')
        self.recipient = Organization.objects.create(name='Community Kitchen A', organization_type='COMMUNITY_KITCHEN', contact_person='Coordinator', email='recipient@example.test', verification_status='APPROVED')
        self.membership = self.recipient.members.create(user=self.user, role='RECIPIENT')
        self.category = FoodCategory.objects.create(name='Cooked Meals')
        now = timezone.now()
        self.listing = FoodListing.objects.create(organization=self.partner, category=self.category, name='Vegetable Rice', quantity_listed=20, unit='PORTIONS', servings=20, preparation_at=now, available_from=now, available_until=now + timedelta(hours=2), storage_condition='HOT_HOLD')

    def test_reservation_cannot_overbook(self):
        reservation = reserve_listing(listing_id=self.listing.id, organization=self.recipient, user=self.user, quantity=15, start=self.listing.available_from, end=self.listing.available_until)
        self.assertEqual(reservation.quantity, 15)
        with self.assertRaises(ValueError):
            reserve_listing(listing_id=self.listing.id, organization=self.recipient, user=self.user, quantity=6, start=self.listing.available_from, end=self.listing.available_until)

    def test_pickup_cannot_skip_collection(self):
        reservation = reserve_listing(listing_id=self.listing.id, organization=self.recipient, user=self.user, quantity=5, start=self.listing.available_from, end=self.listing.available_until)
        courier_user = User.objects.create_user(username='courier', password='safe-password')
        courier = Courier.objects.create(user=courier_user)
        pickup = Pickup.objects.create(reservation=reservation, courier=courier, source=self.partner, destination=self.recipient, expected_quantity=5, window_start=self.listing.available_from, window_end=self.listing.available_until)
        with self.assertRaises(ValueError): transition_pickup(pickup_id=pickup.id, to_status='DELIVERED', user=courier_user)
        pickup.collected_quantity = 5; pickup.save(update_fields=['collected_quantity'])
        transition_pickup(pickup_id=pickup.id, to_status='COLLECTED', user=courier_user)
        pickup.delivered_quantity = 5; pickup.save(update_fields=['delivered_quantity'])
        transition_pickup(pickup_id=pickup.id, to_status='DELIVERED', user=courier_user)
        transition_pickup(pickup_id=pickup.id, to_status='COMPLETED', user=courier_user)
        self.assertEqual(pickup.__class__.objects.get(pk=pickup.pk).status, 'COMPLETED')
