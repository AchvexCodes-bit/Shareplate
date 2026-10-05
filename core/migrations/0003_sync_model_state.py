import django.core.validators
import django.utils.timezone
from django.db import migrations, models
import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_listing_status_history"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="auditlog",
            old_name="core_auditl_entity__4b2c31_idx",
            new_name="core_auditl_entity__244637_idx",
        ),
        migrations.RenameIndex(
            model_name="auditlog",
            old_name="core_auditl_created_8f1a11_idx",
            new_name="core_auditl_created_dc23ea_idx",
        ),
        migrations.RenameIndex(
            model_name="foodlisting",
            old_name="core_foodli_status_9f1e2a_idx",
            new_name="core_foodli_status_c14e6a_idx",
        ),
        migrations.RenameIndex(
            model_name="foodlisting",
            old_name="core_foodli_organiz_efc0b6_idx",
            new_name="core_foodli_organiz_679d1f_idx",
        ),
        migrations.RenameIndex(
            model_name="foodlisting",
            old_name="core_foodli_categor_6e9d6d_idx",
            new_name="core_foodli_categor_e3f8ed_idx",
        ),
        migrations.RenameIndex(
            model_name="notification",
            old_name="core_notifi_user_re_6d5a22_idx",
            new_name="core_notifi_user_id_a55642_idx",
        ),
        migrations.RenameIndex(
            model_name="pickup",
            old_name="core_pickup_status_7e3d91_idx",
            new_name="core_pickup_status_4a20c4_idx",
        ),
        migrations.RenameIndex(
            model_name="pickup",
            old_name="core_pickup_courie_9a6d12_idx",
            new_name="core_pickup_courier_be4b0d_idx",
        ),
        migrations.RenameIndex(
            model_name="reservation",
            old_name="core_reserva_listin_8c4d7a_idx",
            new_name="core_reserv_listing_face01_idx",
        ),
        migrations.RenameIndex(
            model_name="reservation",
            old_name="core_reserva_organi_6f2b8c_idx",
            new_name="core_reserv_organiz_d8ce50_idx",
        ),
        migrations.AlterField(
            model_name="deliveryconfirmation",
            name="confirmed_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name="foodlisting",
            name="quantity_listed",
            field=models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AlterField(
            model_name="foodlisting",
            name="reference",
            field=models.CharField(default=core.models.listing_reference, max_length=30, unique=True),
        ),
        migrations.AlterField(
            model_name="pickup",
            name="reference",
            field=models.CharField(default=core.models.pickup_reference, max_length=30, unique=True),
        ),
        migrations.AlterField(
            model_name="reservation",
            name="quantity",
            field=models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AlterField(
            model_name="reservation",
            name="reference",
            field=models.CharField(default=core.models.reservation_reference, max_length=30, unique=True),
        ),
    ]
