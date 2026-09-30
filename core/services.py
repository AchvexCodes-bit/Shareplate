from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from .models import FoodListing, Reservation, Pickup, PickupStatusHistory, ImpactRecord, Notification

PICKUP_TRANSITIONS = {
    'ASSIGNED': {'ACCEPTED','CANCELLED','RESCHEDULED'},
    'ACCEPTED': {'EN_ROUTE','CANCELLED','RESCHEDULED'},
    'EN_ROUTE': {'ARRIVED','ISSUE'},
    'ARRIVED': {'COLLECTED','ISSUE'},
    'COLLECTED': {'DELIVERED','ISSUE'},
    'DELIVERED': {'COMPLETED','ISSUE'},
    'COMPLETED': set(), 'CANCELLED': set(), 'ISSUE': {'ASSIGNED','RESCHEDULED'}, 'RESCHEDULED': {'ASSIGNED','CANCELLED'}
}

@transaction.atomic
def reserve_listing(*, listing_id, organization, user, quantity, start, end):
    listing = FoodListing.objects.select_for_update().select_related('organization').get(pk=listing_id)
    if organization.verification_status != 'APPROVED' or not organization.active:
        raise ValueError('Your organization must be verified and active before reserving food.')
    if timezone.now() >= listing.available_until:
        raise ValueError('This listing is no longer available for reservation.')
    if listing.status not in {'PUBLISHED','PARTIAL'}:
        raise ValueError('This listing is not accepting reservations.')
    if quantity <= 0 or quantity > listing.remaining:
        raise ValueError(f'Only {listing.remaining} units remain available.')
    reservation = Reservation.objects.create(listing=listing, organization=organization, requested_by=user, quantity=quantity, collection_window_start=start, collection_window_end=end)
    listing.quantity_reserved += quantity
    listing.status = 'FULL' if listing.remaining == 0 else 'PARTIAL'
    listing.save(update_fields=['quantity_reserved','status','updated_at'])
    return reservation

@transaction.atomic
def transition_pickup(*, pickup_id, to_status, user, note=''):
    pickup = Pickup.objects.select_for_update().select_related('reservation','courier').get(pk=pickup_id)
    if to_status not in PICKUP_TRANSITIONS.get(pickup.status, set()):
        raise ValueError(f'Invalid pickup transition: {pickup.status} -> {to_status}')
    if to_status == 'COLLECTED' and not pickup.collected_quantity:
        raise ValueError('Collection quantity is required before marking food collected.')
    if to_status == 'DELIVERED':
        if pickup.status != 'COLLECTED': raise ValueError('Food must be collected before delivery.')
        if pickup.delivered_quantity is None or pickup.delivered_quantity > (pickup.collected_quantity or 0):
            raise ValueError('Delivered quantity cannot exceed collected quantity.')
    old = pickup.status
    pickup.status = to_status
    if to_status == 'COLLECTED': pickup.collection_at = timezone.now()
    if to_status == 'DELIVERED': pickup.delivery_at = timezone.now()
    if to_status == 'COMPLETED':
        pickup.reservation.status = 'COMPLETED'
        pickup.reservation.save(update_fields=['status','updated_at'])
        ImpactRecord.objects.get_or_create(pickup=pickup, defaults={'organization': pickup.source, 'portions': pickup.delivered_quantity or pickup.collected_quantity or 0})
    pickup.save()
    PickupStatusHistory.objects.create(pickup=pickup, from_status=old, to_status=to_status, changed_by=user, note=note)
    return pickup

def notify(user: User, title: str, message: str, related_type='', related_id=''):
    return Notification.objects.create(user=user, title=title, message=message, related_type=related_type, related_id=str(related_id))
