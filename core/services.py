from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import (
    AuditLog,
    DeliveryConfirmation,
    FoodListing,
    ImpactRecord,
    Notification,
    Pickup,
    PickupStatusHistory,
    Reservation,
)


PICKUP_TRANSITIONS = {
    "ASSIGNED": {"ACCEPTED", "RESCHEDULED"},
    "ACCEPTED": {"EN_ROUTE", "RESCHEDULED"},
    "EN_ROUTE": {"ARRIVED", "ISSUE"},
    "ARRIVED": {"COLLECTED", "ISSUE"},
    "COLLECTED": {"DELIVERED", "ISSUE"},
    "DELIVERED": {"COMPLETED", "ISSUE"},
    "COMPLETED": set(),
    "CANCELLED": set(),
    "ISSUE": {"ASSIGNED", "RESCHEDULED"},
    "RESCHEDULED": {"ASSIGNED", "CANCELLED"},
}


def _audit_status(pickup, old_status, new_status, user, note=""):
    PickupStatusHistory.objects.create(
        pickup=pickup,
        from_status=old_status,
        to_status=new_status,
        changed_by=user,
        note=note,
    )
    AuditLog.objects.create(
        actor=user,
        action="pickup_status_changed",
        entity_type="pickup",
        entity_id=str(pickup.pk),
        details={"from": old_status, "to": new_status, "note": note},
    )


def _refresh_listing_availability_status(listing):
    if listing.remaining > 0:
        listing.status = "PUBLISHED" if listing.quantity_reserved == 0 else "PARTIAL"
    elif listing.quantity_reserved > 0:
        listing.status = "FULL"
    elif listing.quantity_collected > 0:
        listing.status = "COLLECTED"


@transaction.atomic
def reserve_listing(*, listing_id, organization, user, quantity, start, end):
    listing = FoodListing.objects.select_for_update().get(pk=listing_id)
    now = timezone.now()
    if organization.verification_status != "APPROVED" or not organization.active:
        raise ValueError("Your organization must be verified and active before reserving food.")
    if listing.organization_id == organization.id:
        raise ValueError("An organization cannot reserve its own listing.")
    if start >= end or start < listing.available_from or end > listing.available_until:
        raise ValueError("The collection window is outside the listing availability window.")
    if now >= listing.available_until:
        raise ValueError("This listing is no longer available for reservation.")
    if listing.available_from > now:
        raise ValueError("This listing is not available yet.")
    if listing.status not in {"PUBLISHED", "PARTIAL"}:
        raise ValueError("This listing is not accepting reservations.")
    if not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("Enter a valid quantity.")
    if quantity > listing.remaining:
        raise ValueError(f"Only {listing.remaining} units remain available.")

    reservation = Reservation.objects.create(
        listing=listing,
        organization=organization,
        requested_by=user,
        quantity=quantity,
        collection_window_start=start,
        collection_window_end=end,
    )
    listing.quantity_reserved += quantity
    listing.status = "FULL" if listing.remaining == 0 else "PARTIAL"
    listing.save(update_fields=["quantity_reserved", "status", "updated_at"])
    AuditLog.objects.create(
        actor=user,
        action="reservation_created",
        entity_type="reservation",
        entity_id=str(reservation.pk),
        details={"quantity": quantity, "listing": listing.reference},
    )
    return reservation


@transaction.atomic
def cancel_reservation(*, reservation_id, user):
    reservation = (
        Reservation.objects.select_for_update()
        .select_related("listing", "organization")
        .get(pk=reservation_id)
    )
    if reservation.status not in {"REQUESTED", "ACCEPTED", "PICKUP"}:
        raise ValueError("This reservation can no longer be cancelled.")

    if not (
        user.is_superuser
        or reservation.requested_by_id == user.id
        or reservation.organization.members.filter(user_id=user.id).exists()
    ):
        raise PermissionError("You do not have permission to cancel this reservation.")

    pickup = getattr(reservation, "pickup", None)
    if reservation.status == "PICKUP" and pickup and pickup.status not in {
        "ASSIGNED",
        "ACCEPTED",
        "RESCHEDULED",
    }:
        raise ValueError("This reservation can no longer be cancelled because the pickup is already in progress.")

    listing = FoodListing.objects.select_for_update().get(pk=reservation.listing_id)
    listing.quantity_reserved = max(0, listing.quantity_reserved - reservation.quantity)
    if listing.available_until > timezone.now() and listing.status in {
        "PUBLISHED",
        "PARTIAL",
        "FULL",
    }:
        _refresh_listing_availability_status(listing)
    listing.save(update_fields=["quantity_reserved", "status", "updated_at"])

    reservation.status = "CANCELLED"
    reservation.save(update_fields=["status", "updated_at"])

    if pickup and pickup.status not in {"CANCELLED", "COMPLETED"}:
        old_pickup_status = pickup.status
        pickup.status = "CANCELLED"
        pickup.save(update_fields=["status", "updated_at"])
        _audit_status(
            pickup,
            old_pickup_status,
            "CANCELLED",
            user,
            "Pickup cancelled with the reservation.",
        )
        if pickup.courier:
            notify(
                pickup.courier.user,
                "Pickup cancelled",
                f"Pickup {pickup.reference} was cancelled because reservation {reservation.reference} was cancelled.",
                "pickup",
                pickup.pk,
            )

    AuditLog.objects.create(
        actor=user,
        action="reservation_cancelled",
        entity_type="reservation",
        entity_id=str(reservation.pk),
        details={"quantity_released": reservation.quantity},
    )
    return reservation


@transaction.atomic
def transition_pickup(
    *,
    pickup_id,
    to_status,
    user,
    collected_quantity=None,
    delivered_quantity=None,
    note="",
):
    pickup = (
        Pickup.objects.select_for_update()
        .select_related("reservation", "courier", "source", "destination")
        .get(pk=pickup_id)
    )
    if pickup.courier_id is None:
        raise ValueError("A courier must be assigned before this pickup can progress.")
    if not (user.is_superuser or pickup.courier.user_id == user.id):
        raise PermissionError("You are not assigned to this pickup.")
    if to_status not in PICKUP_TRANSITIONS.get(pickup.status, set()):
        raise ValueError(f"Invalid pickup transition: {pickup.status} -> {to_status}")

    old_status = pickup.status
    reservation = Reservation.objects.select_for_update().get(pk=pickup.reservation_id)
    listing = FoodListing.objects.select_for_update().get(pk=reservation.listing_id)

    if to_status == "COLLECTED":
        if collected_quantity is None or collected_quantity <= 0:
            raise ValueError("Collection quantity is required.")
        if (
            collected_quantity > pickup.expected_quantity
            or collected_quantity > reservation.quantity
            or collected_quantity > listing.quantity_reserved
        ):
            raise ValueError("Collected quantity exceeds the available reserved quantity.")
        if pickup.collected_quantity is not None:
            raise ValueError("Collection has already been recorded.")

        original_quantity = reservation.quantity
        shortfall = original_quantity - collected_quantity
        pickup.collected_quantity = collected_quantity
        pickup.collection_at = timezone.now()
        reservation.quantity = collected_quantity
        reservation.status = "COLLECTED"
        reservation.save(update_fields=["quantity", "status", "updated_at"])

        listing.quantity_reserved = max(0, listing.quantity_reserved - original_quantity)
        listing.quantity_collected += collected_quantity
        _refresh_listing_availability_status(listing)
        listing.save(
            update_fields=[
                "quantity_reserved",
                "quantity_collected",
                "status",
                "updated_at",
            ]
        )

        if shortfall:
            AuditLog.objects.create(
                actor=user,
                action="collection_shortfall",
                entity_type="pickup",
                entity_id=str(pickup.pk),
                details={
                    "expected": original_quantity,
                    "collected": collected_quantity,
                    "released": shortfall,
                },
            )

    elif to_status == "DELIVERED":
        if delivered_quantity is None or delivered_quantity <= 0:
            raise ValueError("Delivered quantity is required.")
        if delivered_quantity > (pickup.collected_quantity or 0):
            raise ValueError("Delivered quantity cannot exceed collected quantity.")

        pickup.delivered_quantity = delivered_quantity
        pickup.delivery_at = timezone.now()
        pickup.delivery_notes = note
        reservation.status = "RECEIVED"
        reservation.save(update_fields=["status", "updated_at"])
        listing.save(update_fields=["updated_at"])

    elif to_status == "COMPLETED":
        if pickup.status != "DELIVERED" or pickup.delivered_quantity is None:
            raise ValueError("A delivered quantity is required before completing the pickup.")

        reservation.status = "COMPLETED"
        reservation.save(update_fields=["status", "updated_at"])

        other_active_pickups = (
            Pickup.objects.filter(reservation__listing_id=listing.pk)
            .exclude(pk=pickup.pk)
            .exclude(status__in=["COMPLETED", "CANCELLED"])
            .exists()
        )

        weight_kg = (
            Decimal(pickup.delivered_quantity)
            if listing.unit == "KILOGRAMS"
            else None
        )
        ImpactRecord.objects.update_or_create(
            pickup=pickup,
            defaults={
                "organization": pickup.source,
                "portions": pickup.delivered_quantity * listing.servings,
                "weight_kg": weight_kg,
            },
        )
        if not other_active_pickups:
            listing.status = "COMPLETED"
            listing.save(update_fields=["status", "updated_at"])

    pickup.status = to_status
    if note and to_status not in {"COLLECTED", "DELIVERED"}:
        pickup.issue_notes = note
    pickup.save()

    _audit_status(pickup, old_status, to_status, user, note)

    label = to_status.replace("_", " ").title()
    recipient_membership = (
        pickup.destination.members.select_related("user")
        .filter(role="RECIPIENT")
        .first()
    )
    donor_membership = (
        pickup.source.members.select_related("user")
        .filter(role="FOOD_PARTNER")
        .first()
    )

    if (
        to_status
        in {
            "ACCEPTED",
            "EN_ROUTE",
            "ARRIVED",
            "COLLECTED",
            "DELIVERED",
            "ISSUE",
            "RESCHEDULED",
        }
        and recipient_membership
    ):
        notify(
            recipient_membership.user,
            f"Pickup {label}",
            f"Pickup {pickup.reference} is now {label.lower()}.",
            "pickup",
            pickup.pk,
        )
    if (
        to_status in {"DELIVERED", "COMPLETED", "ISSUE"}
        and donor_membership
    ):
        notify(
            donor_membership.user,
            f"Pickup {label}",
            f"Pickup {pickup.reference} is now {label.lower()}.",
            "pickup",
            pickup.pk,
        )
    return pickup


def notify(user: User, title: str, message: str, related_type="", related_id=""):
    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        related_type=related_type,
        related_id=str(related_id),
    )
