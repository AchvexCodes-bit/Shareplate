from django.contrib import admin
from .models import *

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name','organization_type','verification_status','active','created_at')
    list_filter = ('organization_type','verification_status','active')
    search_fields = ('name','email','contact_person')
    list_per_page = 25

@admin.register(FoodListing)
class FoodListingAdmin(admin.ModelAdmin):
    list_display = ('reference','name','organization','status','quantity_listed','quantity_reserved','quantity_collected','available_until')
    list_filter = ('status','category','storage_condition')
    search_fields = ('reference','name','organization__name')
    list_per_page = 25

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('reference','listing','organization','quantity','status','created_at')
    list_filter = ('status',)
    search_fields = ('reference','listing__name','organization__name')
    list_per_page = 25

@admin.register(Pickup)
class PickupAdmin(admin.ModelAdmin):
    list_display = ('reference','source','destination','courier','status','expected_quantity','collected_quantity','delivered_quantity','window_start')
    list_filter = ('status',)
    search_fields = ('reference','source__name','destination__name')
    list_per_page = 25

@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('id','category','status','created_at','updated_at')
    list_filter = ('status','category')
    search_fields = ('description','category')

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('actor','action','entity_type','entity_id','created_at')
    list_filter = ('action','entity_type')
    search_fields = ('entity_id','action')
    readonly_fields = ('actor','action','entity_type','entity_id','details','created_at')

admin.site.register(Membership)
admin.site.register(Address)
admin.site.register(FoodCategory)
admin.site.register(FoodSafetyRecord)
admin.site.register(SavedFood)
admin.site.register(Courier)
admin.site.register(PickupStatusHistory)
admin.site.register(DeliveryConfirmation)
admin.site.register(Notification)
admin.site.register(ImpactRecord)
