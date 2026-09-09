from django.db import migrations, models


def mark_products_using_category_vat(apps, schema_editor):
    Product = apps.get_model("inventory", "Product")
    products_to_update = []

    for product in Product.objects.select_related("category").iterator():
        if product.vat_rate == product.category.default_vat_rate:
            product.uses_category_vat = True
            products_to_update.append(product)

    Product.objects.bulk_update(products_to_update, ["uses_category_vat"])


def unmark_products_using_category_vat(apps, schema_editor):
    Product = apps.get_model("inventory", "Product")
    Product.objects.update(uses_category_vat=False)


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="uses_category_vat",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            mark_products_using_category_vat,
            unmark_products_using_category_vat,
        ),
    ]
