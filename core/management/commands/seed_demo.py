from datetime import timedelta
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    Organization, Membership, Address, FoodCategory, FoodListing,
    Reservation, Courier, Pickup, PickupStatusHistory, Notification,
)


class Command(BaseCommand):
    help = "Create a complete SharePlate demo dataset."

    def handle(self, *args, **options):
        password = "Demo@12345"
        now = timezone.now()

        def user(username, email, first, last, staff=False, superuser=False):
            u, created = User.objects.get_or_create(username=username, defaults={
                "email": email, "first_name": first, "last_name": last,
                "is_staff": staff, "is_superuser": superuser,
            })
            u.email = email
            u.first_name = first
            u.last_name = last
            u.is_staff = staff
            u.is_superuser = superuser
            u.set_password(password)
            u.save()
            return u

        admin = user("demo_admin", "admin@shareplate.demo", "Demo", "Admin", True, True)
        donor_user = user("demo_donor", "donor@shareplate.demo", "Anu", "Thomas")
        recipient_user = user("demo_recipient", "recipient@shareplate.demo", "Rahul", "Nair")
        courier_user = user("demo_courier", "courier@shareplate.demo", "Arun", "Kumar")

        donor, _ = Organization.objects.update_or_create(
            email="donor@shareplate.demo",
            defaults={
                "name": "Green Leaf Restaurant",
                "organization_type": "RESTAURANT",
                "description": "Demo food partner supplying safe surplus meals.",
                "contact_person": "Anu Thomas",
                "phone": "+91 98765 43210",
                "operating_hours": "10:00 AM - 10:00 PM",
                "maximum_daily_capacity": 250,
                "verification_status": "APPROVED",
                "active": True,
            },
        )
        recipient, _ = Organization.objects.update_or_create(
            email="recipient@shareplate.demo",
            defaults={
                "name": "Hope Community Centre",
                "organization_type": "COMMUNITY_KITCHEN",
                "description": "Demo recipient organization serving local families.",
                "contact_person": "Rahul Nair",
                "phone": "+91 98765 43211",
                "operating_hours": "08:00 AM - 08:00 PM",
                "maximum_daily_capacity": 180,
                "verification_status": "APPROVED",
                "active": True,
            },
        )

        Membership.objects.get_or_create(user=donor_user, organization=donor, defaults={"role": "FOOD_PARTNER"})
        Membership.objects.get_or_create(user=recipient_user, organization=recipient, defaults={"role": "RECIPIENT"})
        Membership.objects.get_or_create(user=courier_user, organization=donor, defaults={"role": "COURIER"})
        Membership.objects.get_or_create(user=admin, organization=donor, defaults={"role": "ADMIN"})

        Address.objects.get_or_create(
            organization=donor, label="Primary",
            defaults={"line1": "MG Road", "city": "Kochi", "state": "Kerala", "postal_code": "682016",
                      "latitude": 9.9816, "longitude": 76.2999, "is_primary": True},
        )
        Address.objects.get_or_create(
            organization=recipient, label="Primary",
            defaults={"line1": "Market Road", "city": "Kochi", "state": "Kerala", "postal_code": "682011",
                      "latitude": 9.9670, "longitude": 76.2850, "is_primary": True},
        )

        category_names = ["Prepared Meals", "Bakery", "Rice & Curries", "Fruits & Vegetables", "Packaged Food"]
        categories = {}
        for name in category_names:
            categories[name], _ = FoodCategory.objects.get_or_create(name=name)

        available_from = now - timedelta(minutes=30)
        available_until = now + timedelta(hours=8)

        listing_specs = [
            ("Vegetable Meals", "Fresh vegetarian meals prepared today.", 80, "PORTIONS", 1, "Prepared Meals"),
            ("Assorted Bakery Packs", "Bread, buns and pastries from today's production.", 35, "PACKS", 2, "Bakery"),
            ("Rice & Curry Trays", "Packed rice meals with vegetable curry.", 45, "TRAYS", 2, "Rice & Curries"),
        ]
        listings = []
        for name, desc, qty, unit, servings, cat in listing_specs:
            listing, _ = FoodListing.objects.get_or_create(
                organization=donor, name=name,
                defaults={
                    "category": categories[cat], "description": desc,
                    "quantity_listed": qty, "quantity_reserved": 0, "quantity_collected": 0,
                    "unit": unit, "servings": servings,
                    "preparation_at": now - timedelta(hours=2),
                    "available_from": available_from, "available_until": available_until,
                    "storage_condition": "HOT_HOLD" if "Meals" in name or "Trays" in name else "AMBIENT",
                    "ingredients": "Contains common food ingredients.",
                    "allergens": "May contain dairy and gluten.",
                    "handling_instructions": "Keep sealed and transport promptly.",
                    "status": "PUBLISHED",
                },
            )
            listings.append(listing)

        # One realistic active reservation/pickup flow.
        listing = listings[0]
        reservation, _ = Reservation.objects.get_or_create(
            listing=listing, organization=recipient, requested_by=recipient_user,
            defaults={
                "quantity": 20, "status": "ACCEPTED",
                "collection_window_start": now + timedelta(hours=1),
                "collection_window_end": now + timedelta(hours=3),
            },
        )
        if reservation.status == "REQUESTED":
            reservation.status = "ACCEPTED"
            reservation.save(update_fields=["status"])
        if reservation.status in {"REQUESTED", "ACCEPTED", "PICKUP"} and listing.quantity_reserved < reservation.quantity:
            listing.quantity_reserved = reservation.quantity
            listing.status = "FULL" if listing.quantity_reserved >= listing.quantity_listed else "PARTIAL"
            listing.save(update_fields=["quantity_reserved", "status", "updated_at"])

        courier, _ = Courier.objects.get_or_create(
            user=courier_user, defaults={"vehicle_details": "Motorcycle · KL-07-DEMO-01", "active": True}
        )

        pickup, _ = Pickup.objects.get_or_create(
            reservation=reservation,
            defaults={
                "courier": courier, "source": donor, "destination": recipient,
                "status": "ASSIGNED",
                "window_start": now + timedelta(hours=1),
                "window_end": now + timedelta(hours=3),
                "expected_quantity": reservation.quantity,
            },
        )
        PickupStatusHistory.objects.get_or_create(
            pickup=pickup, to_status="ASSIGNED",
            defaults={"from_status": "", "changed_by": admin, "note": "Demo pickup assigned to courier."},
        )

        Notification.objects.get_or_create(
            user=recipient_user, title="Reservation accepted",
            related_type="reservation", related_id=str(reservation.pk),
            defaults={"message": f"{listing.name} reservation {reservation.reference} has been accepted."},
        )
        Notification.objects.get_or_create(
            user=courier_user, title="New pickup assigned",
            related_type="pickup", related_id=str(pickup.pk),
            defaults={"message": f"Pickup {pickup.reference} is assigned to you."},
        )
        Notification.objects.get_or_create(
            user=donor_user, title="Food listing published",
            related_type="listing", related_id=str(listing.pk),
            defaults={"message": f"{listing.name} is live for recipient organizations."},
        )

        self.stdout.write(self.style.SUCCESS("SharePlate demo data is ready."))
        self.stdout.write("Demo password for all demo accounts: Demo@12345")
        self.stdout.write("Admin:    demo_admin")
        self.stdout.write("Donor:    demo_donor")
        self.stdout.write("Recipient: demo_recipient")
        self.stdout.write("Courier:  demo_courier")
