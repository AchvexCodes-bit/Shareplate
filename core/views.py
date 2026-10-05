from datetime import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    FoodListing, Reservation, Pickup, Notification, ImpactRecord,
    Organization, FoodCategory, Courier, Complaint, PickupStatusHistory,
    DeliveryConfirmation,
)
from .services import reserve_listing, transition_pickup, cancel_reservation, notify


def user_role(user):
    if user.is_superuser:
        return "ADMIN"
    roles = set(user.memberships.values_list("role", flat=True))
    for role in ("ADMIN", "COURIER", "FOOD_PARTNER", "RECIPIENT"):
        if role in roles:
            return role
    return None


def user_org(user, role=None):
    memberships = user.memberships.select_related("organization")
    if role:
        memberships = memberships.filter(role=role)
    membership = memberships.first()
    return membership.organization if membership else None


def require_role(request, *roles):
    role = user_role(request.user)
    if role not in roles:
        return HttpResponseForbidden("You do not have permission for this area.")
    return None


@login_required
def dashboard(request):
    role = user_role(request.user)
    org = user_org(request.user, "FOOD_PARTNER") or user_org(request.user, "RECIPIENT") or user_org(request.user, "ADMIN")

    context = {
        "role": role,
        "org": org,
        "active_listings": 0,
        "reservations": 0,
        "pickups": 0,
        "impact": {"weight": 0, "portions": 0},
        "my_listings": [],
        "incoming_reservations": [],
        "my_reservations": [],
        "recipient_pickups": [],
        "pending_orgs": [],
        "unassigned_pickups": [],
        "couriers": Courier.objects.filter(active=True).select_related("user"),
        "open_complaints": [],
        "categories": FoodCategory.objects.filter(active=True).order_by("name"),
    }

    if role == "FOOD_PARTNER" and org:
        context.update({
            "active_listings": FoodListing.objects.filter(
                organization=org, status__in=["PUBLISHED", "PARTIAL", "FULL"]
            ).count(),
            "reservations": Reservation.objects.filter(listing__organization=org).count(),
            "pickups": Pickup.objects.filter(source=org, window_start__date=timezone.localdate()).count(),
            "my_listings": FoodListing.objects.filter(organization=org).select_related("category").order_by("-created_at")[:12],
            "incoming_reservations": Reservation.objects.filter(
                listing__organization=org, status="REQUESTED"
            ).select_related("listing", "organization", "requested_by").order_by("-created_at")[:12],
        })
    elif role == "RECIPIENT" and org:
        context.update({
            "active_listings": FoodListing.objects.filter(
                status__in=["PUBLISHED", "PARTIAL", "FULL"],
                available_until__gt=timezone.now(),
            ).count(),
            "reservations": Reservation.objects.filter(organization=org).count(),
            "pickups": Pickup.objects.filter(destination=org, window_start__date=timezone.localdate()).count(),
            "my_reservations": Reservation.objects.filter(
                organization=org
            ).select_related("listing", "listing__organization").order_by("-created_at")[:12],
            "recipient_pickups": Pickup.objects.filter(
                destination=org
            ).select_related("reservation__listing", "source", "courier__user").order_by("-window_start")[:12],
        })
    elif role == "COURIER":
        try:
            courier = request.user.courier_profile
        except Courier.DoesNotExist:
            courier = None
        if courier:
            context["pickups"] = courier.pickups.exclude(status__in=["COMPLETED", "CANCELLED"]).count()
    elif role == "ADMIN":
        context.update({
            "active_listings": FoodListing.objects.filter(status__in=["PUBLISHED", "PARTIAL", "FULL"]).count(),
            "reservations": Reservation.objects.count(),
            "pickups": Pickup.objects.filter(window_start__date=timezone.localdate()).count(),
            "pending_orgs": Organization.objects.filter(verification_status="PENDING").order_by("created_at")[:12],
            "unassigned_pickups": Pickup.objects.filter(
                courier__isnull=True, status__in=["ASSIGNED", "RESCHEDULED"]
            ).select_related("reservation__listing", "source", "destination").order_by("window_start")[:12],
            "open_complaints": Complaint.objects.filter(
                status__in=["OPEN", "IN_REVIEW", "ACTION_REQUIRED"]
            ).select_related("reporter", "organization", "pickup").order_by("-created_at")[:12],
            "impact": ImpactRecord.objects.aggregate(
                weight=Sum("weight_kg"), portions=Sum("portions")
            ),
        })

    if role != "ADMIN":
        context["impact"] = ImpactRecord.objects.aggregate(weight=Sum("weight_kg"), portions=Sum("portions"))

    return render(request, "dashboard.html", context)


@login_required
def listings(request):
    qs = FoodListing.objects.select_related("organization", "category").filter(
        status__in=["PUBLISHED", "PARTIAL"],
        available_from__lte=timezone.now(),
        available_until__gt=timezone.now(),
    ).order_by("available_until")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(category__name__icontains=q)
            | Q(organization__name__icontains=q)
        )
    can_reserve = request.user.memberships.filter(role="RECIPIENT").exists()
    return render(
        request,
        "listings.html",
        {"listings": qs[:100], "can_reserve": can_reserve},
    )


@login_required
def create_listing(request):
    denied = require_role(request, "FOOD_PARTNER")
    if denied:
        return denied
    org = user_org(request.user, "FOOD_PARTNER")
    if not org or org.verification_status != "APPROVED":
        messages.error(request, "Your organization must be approved before publishing food.")
        return redirect("dashboard")

    if request.method != "POST":
        return redirect("dashboard")

    def dt(name, fallback=None):
        value = parse_datetime(request.POST.get(name, ""))
        if value and timezone.is_naive(value):
            value = timezone.make_aware(value)
        return value or fallback

    try:
        name = request.POST.get("name", "").strip()
        quantity = int(request.POST.get("quantity_listed", "0"))
        servings = int(request.POST.get("servings", "1"))
        category = FoodCategory.objects.get(
            pk=int(request.POST.get("category")),
            active=True,
        )
        unit = request.POST.get("unit", "PORTIONS")
        storage_condition = request.POST.get("storage_condition", "AMBIENT")
        start = dt("available_from")
        end = dt("available_until")
        preparation = dt("preparation_at", start or timezone.now())

        valid_units = {value for value, _ in FoodListing.UNITS}
        valid_storage = {value for value, _ in FoodListing.STORAGE}

        if not name:
            raise ValueError("Food name is required.")
        if quantity <= 0 or servings <= 0:
            raise ValueError("Quantity and servings must be greater than zero.")
        if unit not in valid_units or storage_condition not in valid_storage:
            raise ValueError("Choose a valid unit and storage condition.")
        if not start or not end or start >= end:
            raise ValueError("Enter a valid availability window.")
        if end <= timezone.now():
            raise ValueError("The availability window must end in the future.")
        if preparation > end:
            raise ValueError("Preparation time cannot be after the listing expires.")

        listing = FoodListing.objects.create(
            organization=org,
            category=category,
            name=name,
            description=request.POST.get("description", "").strip(),
            quantity_listed=quantity,
            unit=unit,
            servings=servings,
            preparation_at=preparation,
            available_from=start,
            available_until=end,
            storage_condition=storage_condition,
            ingredients=request.POST.get("ingredients", "").strip(),
            allergens=request.POST.get("allergens", "").strip(),
            handling_instructions=request.POST.get("handling_instructions", "").strip(),
            status="PUBLISHED",
        )
    except (ValueError, TypeError, FoodCategory.DoesNotExist) as exc:
        messages.error(request, f"Listing could not be created: {exc}")
        return redirect("dashboard")

    messages.success(request, f"{listing.name} is now available to recipient organizations.")
    return redirect("dashboard")


@login_required
def listing_action(request, pk, action):
    denied = require_role(request, "FOOD_PARTNER", "ADMIN")
    if denied:
        return denied
    listing = get_object_or_404(FoodListing, pk=pk)

    if request.user.is_superuser:
        allowed = True
    else:
        org = user_org(request.user, "FOOD_PARTNER")
        allowed = bool(org and listing.organization_id == org.id)
    if not allowed:
        return HttpResponseForbidden("You cannot modify this listing.")

    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    if action == "cancel":
        if listing.status not in {"PUBLISHED", "PARTIAL", "FULL"}:
            messages.error(request, "Only active listings can be cancelled.")
        elif listing.quantity_reserved:
            messages.error(request, "A listing with reservations cannot be cancelled here.")
        else:
            listing.status = "CANCELLED"
            listing.save(update_fields=["status", "updated_at"])
            messages.success(request, "Listing cancelled.")
    else:
        return HttpResponseBadRequest("Unknown action")
    return redirect("dashboard")


@login_required
def reserve(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    membership = request.user.memberships.filter(role="RECIPIENT").select_related("organization").first()
    if not membership:
        return HttpResponseForbidden("A recipient organization is required.")
    listing = get_object_or_404(FoodListing, pk=pk)
    try:
        quantity = int(request.POST.get("quantity", "0"))
        reservation = reserve_listing(
            listing_id=pk,
            organization=membership.organization,
            user=request.user,
            quantity=quantity,
            start=listing.available_from,
            end=listing.available_until,
        )
    except (ValueError, TypeError, FoodListing.DoesNotExist) as exc:
        messages.error(request, str(exc))
        return redirect("listings")
    notify(
        listing.organization.members.select_related("user").filter(role="FOOD_PARTNER").first().user
        if listing.organization.members.filter(role="FOOD_PARTNER").exists() else request.user,
        "New reservation request",
        f"{request.user.get_full_name() or request.user.username} requested {reservation.quantity} from {listing.name}.",
        "reservation",
        reservation.pk,
    )
    messages.success(request, f"Reservation {reservation.reference} created and sent to the food partner.")
    return redirect("dashboard")


@login_required
def reservation_action(request, pk, action):
    denied = require_role(request, "FOOD_PARTNER", "ADMIN")
    if denied:
        return denied
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    with transaction.atomic():
        reservation = get_object_or_404(
            Reservation.objects.select_for_update().select_related(
                "listing", "organization", "requested_by"
            ),
            pk=pk,
        )

        if not request.user.is_superuser:
            org = user_org(request.user, "FOOD_PARTNER")
            if not org or reservation.listing.organization_id != org.id:
                return HttpResponseForbidden("You cannot manage this reservation.")

        if action not in {"accept", "reject"}:
            return HttpResponseBadRequest("Unknown action")

        if reservation.status != "REQUESTED":
            messages.error(
                request,
                f"This reservation is already {reservation.get_status_display().lower()} and cannot be changed.",
            )
            return redirect("dashboard")

        listing = FoodListing.objects.select_for_update().get(pk=reservation.listing_id)

        if action == "accept":
            if timezone.now() >= listing.available_until:
                listing.quantity_reserved = max(0, listing.quantity_reserved - reservation.quantity)
                if listing.status in {"PARTIAL", "FULL"}:
                    listing.status = (
                        "PUBLISHED" if listing.quantity_reserved == 0 else "PARTIAL"
                    )
                listing.save(update_fields=["quantity_reserved", "status", "updated_at"])
                reservation.status = "REJECTED"
                reservation.save(update_fields=["status", "updated_at"])
                notify(
                    reservation.requested_by,
                    "Reservation expired",
                    f"Your reservation {reservation.reference} could not be accepted because {reservation.listing.name} is no longer available.",
                    "reservation",
                    reservation.pk,
                )
                messages.error(request, f"{reservation.reference} expired and its inventory was released.")
                return redirect("dashboard")

            reservation.status = "ACCEPTED"
            reservation.save(update_fields=["status", "updated_at"])

            pickup, created = Pickup.objects.get_or_create(
                reservation=reservation,
                defaults={
                    "source": reservation.listing.organization,
                    "destination": reservation.organization,
                    "status": "ASSIGNED",
                    "window_start": reservation.collection_window_start,
                    "window_end": reservation.collection_window_end,
                    "expected_quantity": reservation.quantity,
                },
            )
            if created:
                PickupStatusHistory.objects.create(
                    pickup=pickup,
                    from_status="",
                    to_status="ASSIGNED",
                    changed_by=request.user,
                    note="Pickup created after reservation approval.",
                )
            notify(
                reservation.requested_by,
                "Reservation accepted",
                f"Your reservation {reservation.reference} for {reservation.listing.name} was accepted.",
                "reservation",
                reservation.pk,
            )
            messages.success(
                request,
                f"{reservation.reference} accepted and pickup {pickup.reference} is ready for assignment.",
            )
        else:
            listing.quantity_reserved = max(0, listing.quantity_reserved - reservation.quantity)
            if listing.status in {"PARTIAL", "FULL"} and listing.available_until > timezone.now():
                listing.status = (
                    "PUBLISHED" if listing.quantity_reserved == 0 else "PARTIAL"
                )
            listing.save(update_fields=["quantity_reserved", "status", "updated_at"])
            reservation.status = "REJECTED"
            reservation.save(update_fields=["status", "updated_at"])
            notify(
                reservation.requested_by,
                "Reservation declined",
                f"Your reservation {reservation.reference} for {reservation.listing.name} was declined.",
                "reservation",
                reservation.pk,
            )
            messages.success(request, f"{reservation.reference} rejected and inventory released.")
    return redirect("dashboard")


@login_required
def cancel_reservation_view(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    try:
        cancel_reservation(reservation_id=pk, user=request.user)
    except (ValueError, PermissionError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Reservation cancelled and inventory released.")
    return redirect("dashboard")


@login_required
def confirm_delivery(request, pk):
    denied = require_role(request, "RECIPIENT", "ADMIN")
    if denied:
        return denied
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    pickup = get_object_or_404(
        Pickup.objects.select_related(
            "reservation__listing", "destination", "source", "courier__user"
        ),
        pk=pk,
    )
    org = user_org(request.user, "RECIPIENT")
    if not request.user.is_superuser and (not org or pickup.destination_id != org.id):
        return HttpResponseForbidden("You cannot confirm this delivery.")

    if pickup.status != "DELIVERED":
        messages.error(request, "The courier must mark the pickup as delivered first.")
        return redirect("dashboard")

    with transaction.atomic():
        delivered = pickup.delivered_quantity or pickup.collected_quantity or pickup.expected_quantity
        pickup.status = "COMPLETED"
        pickup.updated_at = timezone.now()
        pickup.save(update_fields=["status", "updated_at"])

        reservation = pickup.reservation
        reservation.status = "COMPLETED"
        reservation.save(update_fields=["status", "updated_at"])

        listing = reservation.listing
        other_active_pickups = (
            Pickup.objects.filter(reservation__listing_id=listing.pk)
            .exclude(pk=pickup.pk)
            .exclude(status__in=["COMPLETED", "CANCELLED"])
            .exists()
        )
        if not other_active_pickups:
            listing.status = "COMPLETED"
            listing.save(update_fields=["status", "updated_at"])

        DeliveryConfirmation.objects.update_or_create(
            pickup=pickup,
            defaults={
                "received_by": request.user.get_full_name() or request.user.username,
                "received_quantity": delivered,
                "confirmed_at": timezone.now(),
            },
        )

        ImpactRecord.objects.update_or_create(
            pickup=pickup,
            defaults={
                "organization": pickup.source,
                "portions": delivered,
            },
        )
        PickupStatusHistory.objects.create(
            pickup=pickup,
            from_status="DELIVERED",
            to_status="COMPLETED",
            changed_by=request.user,
            note="Recipient confirmed delivery.",
        )
        if pickup.courier:
            notify(
                pickup.courier.user,
                "Delivery confirmed",
                f"Pickup {pickup.reference} was confirmed by the recipient.",
                "pickup",
                pickup.pk,
            )

    messages.success(
        request,
        f"Delivery {pickup.reference} confirmed. Thank you for completing the redistribution.",
    )
    return redirect("dashboard")


@login_required
def courier_dashboard(request):
    denied = require_role(request, "COURIER")
    if denied:
        return denied
    try:
        courier = request.user.courier_profile
    except Courier.DoesNotExist:
        return HttpResponseForbidden("Courier profile required.")
    pickups = Pickup.objects.select_related(
        "reservation__listing", "source", "destination"
    ).filter(
        courier=courier
    ).exclude(status__in=["COMPLETED", "CANCELLED"]).order_by("window_start")
    return render(request, "courier.html", {"pickups": pickups, "courier": courier})


@login_required
def pickup_action(request, pk, action):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    pickup = get_object_or_404(Pickup, pk=pk)
    try:
        courier = request.user.courier_profile
    except Courier.DoesNotExist:
        return HttpResponseForbidden("Courier profile required.")
    if pickup.courier_id != courier.id and not request.user.is_superuser:
        return HttpResponseForbidden("Not assigned to this pickup.")

    try:
        collected_quantity = None
        delivered_quantity = None
        note = request.POST.get("notes", "").strip()[:2000]
        if action == "collect":
            collected_quantity = int(request.POST.get("quantity", "0"))
            to_status = "COLLECTED"
        elif action == "deliver":
            delivered_quantity = int(request.POST.get("quantity", "0"))
            to_status = "DELIVERED"
        else:
            to_status = action.upper()

        transition_pickup(
            pickup_id=pk,
            to_status=to_status,
            user=request.user,
            collected_quantity=collected_quantity,
            delivered_quantity=delivered_quantity,
            note=note,
        )
    except (ValueError, TypeError, PermissionError) as exc:
        messages.error(request, str(exc))
        return redirect("courier")
    messages.success(request, f"Pickup updated to {to_status.replace('_', ' ').title()}.")
    return redirect("courier")


@login_required
def admin_organization_action(request, pk, action):
    denied = require_role(request, "ADMIN")
    if denied:
        return denied
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    org = get_object_or_404(Organization, pk=pk)
    if action == "approve":
        org.verification_status = "APPROVED"
        org.active = True
        message = "Organization approved."
    elif action == "reject":
        org.verification_status = "REJECTED"
        org.active = False
        message = "Organization rejected."
    else:
        return HttpResponseBadRequest("Unknown action")
    org.save(update_fields=["verification_status", "active", "updated_at"])
    for membership in org.members.select_related("user"):
        notify(membership.user, f"Organization {org.verification_status.lower()}", f"{org.name} is now {org.verification_status.lower()}.")
    messages.success(request, message)
    return redirect("dashboard")


@login_required
def admin_assign_pickup(request, pk):
    denied = require_role(request, "ADMIN")
    if denied:
        return denied
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    pickup = get_object_or_404(
        Pickup.objects.select_related("reservation"),
        pk=pk,
    )
    if pickup.status not in {"ASSIGNED", "RESCHEDULED"}:
        messages.error(request, "Only unstarted pickups can be assigned or reassigned.")
        return redirect("dashboard")

    courier = get_object_or_404(
        Courier.objects.select_related("user"),
        pk=request.POST.get("courier"),
        active=True,
    )
    if not courier.user.memberships.filter(role="COURIER").exists():
        messages.error(request, "The selected account is not an active SharePlate courier.")
        return redirect("dashboard")

    old_status = pickup.status
    pickup.courier = courier
    pickup.status = "ASSIGNED"
    pickup.save(update_fields=["courier", "status", "updated_at"])

    reservation = pickup.reservation
    reservation.status = "PICKUP"
    reservation.save(update_fields=["status", "updated_at"])

    PickupStatusHistory.objects.create(
        pickup=pickup,
        from_status=old_status,
        to_status="ASSIGNED",
        changed_by=request.user,
        note="Assigned by admin.",
    )
    notify(
        courier.user,
        "Pickup assigned",
        f"Pickup {pickup.reference} has been assigned to you.",
        "pickup",
        pickup.pk,
    )
    messages.success(
        request,
        f"{pickup.reference} assigned to {courier.user.get_full_name() or courier.user.username}.",
    )
    return redirect("dashboard")


@login_required
def complaint_create(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    role = user_role(request.user)
    if role not in {"FOOD_PARTNER", "RECIPIENT", "COURIER", "ADMIN"}:
        return HttpResponseForbidden("Your role cannot submit complaints.")

    category = request.POST.get("category", "").strip()
    description = request.POST.get("description", "").strip()
    if not category or not description:
        messages.error(request, "Category and description are required.")
        return redirect("dashboard")

    org = user_org(request.user, role if role != "ADMIN" else None)
    Complaint.objects.create(
        reporter=request.user,
        organization=org,
        category=category[:80],
        description=description,
    )
    messages.success(request, "Your issue was submitted to the SharePlate operations team.")
    return redirect("dashboard")


@login_required
def complaint_action(request, pk, action):
    denied = require_role(request, "ADMIN")
    if denied:
        return denied
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    complaint = get_object_or_404(Complaint, pk=pk)
    if action not in {"IN_REVIEW", "ACTION_REQUIRED", "RESOLVED"}:
        return HttpResponseBadRequest("Unknown action")
    response = request.POST.get("response", "").strip()
    complaint.status = action
    complaint.admin_response = response
    if action == "RESOLVED":
        complaint.resolution = response
        complaint.save(update_fields=["status", "admin_response", "resolution", "updated_at"])
    else:
        complaint.save(update_fields=["status", "admin_response", "updated_at"])
    notify(complaint.reporter, f"Complaint {action.replace('_', ' ').title()}", complaint.admin_response or "Your complaint status was updated.", "complaint", complaint.pk)
    messages.success(request, "Complaint updated.")
    return redirect("dashboard")


@login_required
def notifications(request):
    qs = request.user.notifications.order_by("-created_at")[:100]
    request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    return render(request, "notifications.html", {"notifications": qs})


@login_required
def impact(request):
    summary = ImpactRecord.objects.aggregate(weight=Sum("weight_kg"), portions=Sum("portions"))
    monthly = ImpactRecord.objects.values("recorded_at__year", "recorded_at__month").annotate(
        weight=Sum("weight_kg"), portions=Sum("portions")
    ).order_by("recorded_at__year", "recorded_at__month")
    return render(request, "impact.html", {"summary": summary, "monthly": monthly})


@login_required
def impact_api(request):
    summary = ImpactRecord.objects.aggregate(
        weight=Sum("weight_kg"), portions=Sum("portions"), pickups=Count("pickup", distinct=True)
    )
    return JsonResponse(summary)
