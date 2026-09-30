from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .models import FoodListing, Reservation, Pickup, Notification, ImpactRecord
from .services import reserve_listing, transition_pickup

@login_required
def dashboard(request):
    memberships = request.user.memberships.select_related('organization')
    org_ids = memberships.values_list('organization_id', flat=True)
    context = {
        'active_listings': FoodListing.objects.filter(organization_id__in=org_ids, status__in=['PUBLISHED','PARTIAL','FULL']).count(),
        'reservations': Reservation.objects.filter(organization_id__in=org_ids).count(),
        'pickups': Pickup.objects.filter(source_id__in=org_ids, window_start__date=timezone.localdate()).count(),
        'impact': ImpactRecord.objects.filter(organization_id__in=org_ids).aggregate(weight=Sum('weight_kg'), portions=Sum('portions')),
    }
    return render(request, 'dashboard.html', context)

@login_required
def listings(request):
    qs = FoodListing.objects.select_related('organization','category').filter(status__in=['PUBLISHED','PARTIAL','FULL'], available_until__gt=timezone.now()).order_by('available_until')
    q = request.GET.get('q','').strip()
    if q: qs = qs.filter(name__icontains=q)
    return render(request, 'listings.html', {'listings': qs[:100]})

@login_required
def reserve(request, pk):
    if request.method != 'POST': return HttpResponseBadRequest('POST required')
    membership = request.user.memberships.filter(role='RECIPIENT').select_related('organization').first()
    if not membership: return HttpResponseBadRequest('A recipient organization is required.')
    listing = get_object_or_404(FoodListing, pk=pk)
    try:
        quantity = int(request.POST.get('quantity','0'))
        reservation = reserve_listing(listing_id=pk, organization=membership.organization, user=request.user, quantity=quantity, start=listing.available_from, end=listing.available_until)
    except (ValueError, TypeError, FoodListing.DoesNotExist) as exc:
        messages.error(request, str(exc)); return redirect('listings')
    messages.success(request, f'Reservation {reservation.reference} created.')
    return redirect('dashboard')

@login_required
def courier_dashboard(request):
    try: courier = request.user.courier_profile
    except Exception: return HttpResponseBadRequest('Courier profile required.')
    pickups = Pickup.objects.select_related('reservation__listing','source','destination').filter(courier=courier).exclude(status='COMPLETED').order_by('window_start')
    return render(request, 'courier.html', {'pickups': pickups})

@login_required
def pickup_action(request, pk, action):
    if request.method != 'POST': return HttpResponseBadRequest('POST required')
    pickup = get_object_or_404(Pickup, pk=pk)
    if not hasattr(request.user, 'courier_profile') or pickup.courier_id != request.user.courier_profile.id:
        return HttpResponseBadRequest('Not assigned to this pickup.')
    try:
        if action == 'collect':
            pickup.collected_quantity = int(request.POST.get('quantity','0'))
            pickup.collection_notes = request.POST.get('notes','')[:2000]
            pickup.save(update_fields=['collected_quantity','collection_notes','updated_at'])
            to_status = 'COLLECTED'
        elif action == 'deliver':
            pickup.delivered_quantity = int(request.POST.get('quantity','0'))
            pickup.delivery_notes = request.POST.get('notes','')[:2000]
            pickup.save(update_fields=['delivered_quantity','delivery_notes','updated_at'])
            to_status = 'DELIVERED'
        else: to_status = action.upper()
        transition_pickup(pickup_id=pk, to_status=to_status, user=request.user)
    except (ValueError, TypeError) as exc:
        messages.error(request, str(exc)); return redirect('courier')
    messages.success(request, f'Pickup updated to {to_status.replace("_", " ").title()}.')
    return redirect('courier')

@login_required
def notifications(request):
    qs = request.user.notifications.order_by('-created_at')[:100]
    request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    return render(request, 'notifications.html', {'notifications': qs})

@login_required
def impact(request):
    summary = ImpactRecord.objects.aggregate(weight=Sum('weight_kg'), portions=Sum('portions'))
    monthly = ImpactRecord.objects.values('recorded_at__year','recorded_at__month').annotate(weight=Sum('weight_kg'), portions=Sum('portions')).order_by('recorded_at__year','recorded_at__month')
    return render(request, 'impact.html', {'summary': summary, 'monthly': monthly})

@login_required
def impact_api(request):
    summary = ImpactRecord.objects.aggregate(weight=Sum('weight_kg'), portions=Sum('portions'), pickups=Count('pickup', distinct=True))
    return JsonResponse(summary)
