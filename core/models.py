from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from uuid import uuid4

class Organization(models.Model):
    TYPES = [('RESTAURANT','Restaurant'),('BAKERY','Bakery'),('HOTEL','Hotel'),('SUPERMARKET','Supermarket'),('CATERER','Caterer'),('EVENT_ORGANIZER','Event Organizer'),('NGO','NGO'),('SHELTER','Shelter'),('COMMUNITY_KITCHEN','Community Kitchen'),('OTHER','Other')]
    VERIFICATION = [('PENDING','Pending'),('APPROVED','Approved'),('REJECTED','Rejected'),('SUSPENDED','Suspended')]
    name = models.CharField(max_length=180)
    organization_type = models.CharField(max_length=30, choices=TYPES)
    description = models.TextField(blank=True)
    contact_person = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    operating_hours = models.CharField(max_length=255, blank=True)
    maximum_daily_capacity = models.PositiveIntegerField(null=True, blank=True)
    verification_status = models.CharField(max_length=15, choices=VERIFICATION, default='PENDING')
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.name

class Membership(models.Model):
    ROLES = [('FOOD_PARTNER','Food Partner'),('RECIPIENT','Recipient Organization'),('COURIER','Courier'),('ADMIN','Admin')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='members')
    role = models.CharField(max_length=30, choices=ROLES)
    class Meta: constraints = [models.UniqueConstraint(fields=['user','organization'], name='unique_membership')]

class Address(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=80, default='Primary')
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_primary = models.BooleanField(default=False)

class FoodCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)
    active = models.BooleanField(default=True)
    def __str__(self): return self.name

class FoodListing(models.Model):
    STATUS = [('DRAFT','Draft'),('PUBLISHED','Published'),('PARTIAL','Partially Reserved'),('FULL','Fully Reserved'),('PICKUP','Pickup Scheduled'),('COLLECTED','Collected'),('DELIVERED','Delivered'),('COMPLETED','Completed'),('CANCELLED','Cancelled'),('EXPIRED','Expired'),('REJECTED','Rejected'),('DISPUTED','Disputed')]
    UNITS = [('PORTIONS','Portions'),('KILOGRAMS','Kilograms'),('BOXES','Boxes'),('TRAYS','Trays'),('PACKS','Packs')]
    STORAGE = [('AMBIENT','Ambient'),('REFRIGERATED','Refrigerated'),('FROZEN','Frozen'),('HOT_HOLD','Hot hold'),('OTHER','Other')]
    reference = models.CharField(max_length=30, unique=True, default=lambda: f'SP-L-{uuid4().hex[:8].upper()}')
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='listings')
    category = models.ForeignKey(FoodCategory, on_delete=models.PROTECT, related_name='listings')
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    quantity_listed = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    quantity_reserved = models.PositiveIntegerField(default=0)
    quantity_collected = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=15, choices=UNITS)
    servings = models.PositiveIntegerField(default=1)
    preparation_at = models.DateTimeField()
    available_from = models.DateTimeField()
    available_until = models.DateTimeField()
    storage_condition = models.CharField(max_length=20, choices=STORAGE)
    ingredients = models.TextField(blank=True)
    allergens = models.TextField(blank=True)
    handling_instructions = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='DRAFT')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    @property
    def remaining(self): return max(0, self.quantity_listed - self.quantity_reserved - self.quantity_collected)
    def __str__(self): return f'{self.name} ({self.reference})'
    class Meta:
        indexes = [models.Index(fields=['status','available_until']), models.Index(fields=['organization','status']), models.Index(fields=['category','status'])]

class FoodSafetyRecord(models.Model):
    listing = models.OneToOneField(FoodListing, on_delete=models.CASCADE, related_name='safety')
    preparation_timestamp = models.DateTimeField()
    best_before_timestamp = models.DateTimeField(null=True, blank=True)
    storage_method = models.CharField(max_length=120)
    temperature_c = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    allergen_information = models.TextField(blank=True)
    handling_notes = models.TextField(blank=True)

class ListingStatusHistory(models.Model):
    listing = models.ForeignKey(FoodListing, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class SavedFood(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='saved_foods')
    category = models.ForeignKey(FoodCategory, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=15, choices=FoodListing.UNITS)
    servings = models.PositiveIntegerField(default=1)
    ingredients = models.TextField(blank=True)
    allergens = models.TextField(blank=True)
    storage_condition = models.CharField(max_length=20, choices=FoodListing.STORAGE, blank=True)
    class Meta: constraints = [models.UniqueConstraint(fields=['organization','name'], name='unique_saved_food')]

class Reservation(models.Model):
    STATUS = [('REQUESTED','Requested'),('ACCEPTED','Accepted'),('PICKUP','Pickup Scheduled'),('COLLECTED','Collected'),('RECEIVED','Received'),('COMPLETED','Completed'),('CANCELLED','Cancelled'),('REJECTED','Rejected')]
    reference = models.CharField(max_length=30, unique=True, default=lambda: f'SP-R-{uuid4().hex[:8].upper()}')
    listing = models.ForeignKey(FoodListing, on_delete=models.PROTECT, related_name='reservations')
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='reservations')
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=20, choices=STATUS, default='REQUESTED')
    collection_window_start = models.DateTimeField()
    collection_window_end = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: indexes = [models.Index(fields=['listing','status']), models.Index(fields=['organization','status'])]

class Courier(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='courier_profile')
    vehicle_details = models.CharField(max_length=160, blank=True)
    active = models.BooleanField(default=True)

class Pickup(models.Model):
    STATUS = [('ASSIGNED','Assigned'),('ACCEPTED','Accepted'),('EN_ROUTE','En Route'),('ARRIVED','Arrived'),('COLLECTED','Collected'),('DELIVERED','Delivered'),('COMPLETED','Completed'),('CANCELLED','Cancelled'),('ISSUE','Issue Reported'),('RESCHEDULED','Rescheduled')]
    reference = models.CharField(max_length=30, unique=True, default=lambda: f'PU-{uuid4().hex[:8].upper()}')
    reservation = models.OneToOneField(Reservation, on_delete=models.PROTECT, related_name='pickup')
    courier = models.ForeignKey(Courier, null=True, blank=True, on_delete=models.PROTECT, related_name='pickups')
    source = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='outgoing_pickups')
    destination = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name='incoming_pickups')
    status = models.CharField(max_length=20, choices=STATUS, default='ASSIGNED')
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    expected_quantity = models.PositiveIntegerField()
    collected_quantity = models.PositiveIntegerField(null=True, blank=True)
    delivered_quantity = models.PositiveIntegerField(null=True, blank=True)
    collection_at = models.DateTimeField(null=True, blank=True)
    delivery_at = models.DateTimeField(null=True, blank=True)
    collection_notes = models.TextField(blank=True)
    delivery_notes = models.TextField(blank=True)
    issue_notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: indexes = [models.Index(fields=['status','window_start']), models.Index(fields=['courier','status'])]

class PickupStatusHistory(models.Model):
    pickup = models.ForeignKey(Pickup, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class DeliveryConfirmation(models.Model):
    pickup = models.OneToOneField(Pickup, on_delete=models.CASCADE, related_name='delivery_confirmation')
    received_by = models.CharField(max_length=120, blank=True)
    received_quantity = models.PositiveIntegerField()
    condition = models.CharField(max_length=30, default='GOOD')
    notes = models.TextField(blank=True)
    confirmed_at = models.DateTimeField(default=timezone.now)

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=180)
    message = models.TextField()
    related_type = models.CharField(max_length=50, blank=True)
    related_id = models.CharField(max_length=64, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: indexes = [models.Index(fields=['user','read_at','created_at'])]

class Complaint(models.Model):
    STATUS = [('OPEN','Open'),('IN_REVIEW','Under Review'),('ACTION_REQUIRED','Action Required'),('RESOLVED','Resolved')]
    reporter = models.ForeignKey(User, on_delete=models.PROTECT)
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.PROTECT)
    reservation = models.ForeignKey(Reservation, null=True, blank=True, on_delete=models.PROTECT)
    pickup = models.ForeignKey(Pickup, null=True, blank=True, on_delete=models.PROTECT)
    category = models.CharField(max_length=80)
    description = models.TextField()
    evidence = models.FileField(upload_to='complaints/', blank=True)
    admin_response = models.TextField(blank=True)
    resolution = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='OPEN')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ImpactRecord(models.Model):
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.PROTECT)
    pickup = models.OneToOneField(Pickup, on_delete=models.PROTECT)
    portions = models.PositiveIntegerField()
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

class AuditLog(models.Model):
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=120)
    entity_type = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=64)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: indexes = [models.Index(fields=['entity_type','entity_id']), models.Index(fields=['created_at'])]
