from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from inventory.models import Category, Product
from machines.models import (
    Machine,
    MachineLayout,
    MachinePosition,
    MachinePriceOverride,
    PricingProfile,
)
from machines.services.layouts import (
    activate_machine_layout,
    get_product_for_selection,
)
from machines.services.pricing import (
    get_product_price_for_machine,
)
from purchases.models import Purchase, PurchaseLine
from replenishments.models import Replenishment, ReplenishmentLine
from replenishments.services import (
    get_replenishment_layout_errors,
    get_replenishment_stock_errors,
)
from sales.models import Sale
from sales.services import (
    create_manual_sale,
    receive_sale,
    reject_sale_conflict,
    void_sale,
)


class Command(BaseCommand):
    help = "Crea datos de demostración coherentes para Vimach."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Creando datos de demostración...")

        categories = self.create_categories()
        products = self.create_products(categories)
        pricing_profiles = self.create_pricing_profiles()
        machines = self.create_machines(pricing_profiles)
        self.create_price_overrides(
            products,
            machines,
        )

        self.create_layouts(
            products,
            machines,
        )
        self.create_purchases(products)

        self.create_replenishments(
            products,
            machines,
        )

        self.create_sales(
            products,
            machines,
        )

        self.stdout.write(self.style.SUCCESS("Datos base creados correctamente."))

    def create_categories(self):
        data = [
            {
                "name": "Agua",
                "default_vat_rate": Decimal("10.00"),
            },
            {
                "name": "Refrescos",
                "default_vat_rate": Decimal("21.00"),
            },
            {
                "name": "Zumos",
                "default_vat_rate": Decimal("10.00"),
            },
            {
                "name": "Snacks",
                "default_vat_rate": Decimal("10.00"),
            },
            {
                "name": "Café y bebidas calientes",
                "default_vat_rate": Decimal("10.00"),
            },
        ]

        categories = {}

        for item in data:
            category, _ = Category.objects.update_or_create(
                name=item["name"],
                defaults={
                    "default_vat_rate": item["default_vat_rate"],
                },
            )

            categories[item["name"]] = category

        return categories

    def create_products(self, categories):
        data = [
            {
                "name": "VimaAgua",
                "category": "Agua",
                "format_unit": "500 ml",
                "default_sale_price": Decimal("1.00"),
            },
            {
                "name": "VimaAgua Grande",
                "category": "Agua",
                "format_unit": "1,5 l",
                "default_sale_price": Decimal("1.50"),
            },
            {
                "name": "VimaCola",
                "category": "Refrescos",
                "format_unit": "330 ml",
                "default_sale_price": Decimal("1.60"),
            },
            {
                "name": "VimaCola Zero",
                "category": "Refrescos",
                "format_unit": "330 ml",
                "default_sale_price": Decimal("1.60"),
            },
            {
                "name": "VimaNaranja",
                "category": "Refrescos",
                "format_unit": "330 ml",
                "default_sale_price": Decimal("1.50"),
            },
            {
                "name": "VimaTea Limón",
                "category": "Refrescos",
                "format_unit": "330 ml",
                "default_sale_price": Decimal("1.70"),
            },
            {
                "name": "VimaZumo Naranja",
                "category": "Zumos",
                "format_unit": "250 ml",
                "default_sale_price": Decimal("1.80"),
            },
            {
                "name": "VimaPatatas",
                "category": "Snacks",
                "format_unit": "45 g",
                "default_sale_price": Decimal("1.30"),
            },
            {
                "name": "VimaBarrita",
                "category": "Snacks",
                "format_unit": "40 g",
                "default_sale_price": Decimal("1.40"),
            },
            {
                "name": "VimaChocolate",
                "category": "Snacks",
                "format_unit": "50 g",
                "default_sale_price": Decimal("1.60"),
            },
            {
                "name": "VimaCafé",
                "category": "Café y bebidas calientes",
                "format_unit": "200 ml",
                "default_sale_price": Decimal("1.20"),
            },
            {
                "name": "VimaCappuccino",
                "category": "Café y bebidas calientes",
                "format_unit": "200 ml",
                "default_sale_price": Decimal("1.50"),
            },
        ]

        products = {}

        for item in data:
            category = categories[item["category"]]

            product, _ = Product.objects.update_or_create(
                name=item["name"],
                defaults={
                    "category": category,
                    "format_unit": item["format_unit"],
                    "default_sale_price": (item["default_sale_price"]),
                    "vat_rate": category.default_vat_rate,
                    "uses_category_vat": True,
                    "is_active": True,
                },
            )

            products[item["name"]] = product

        return products

    def create_pricing_profiles(self):
        data = [
            {
                "name": "Estándar",
                "percentage_adjustment": Decimal("0.00"),
            },
            {
                "name": "Ubicación premium",
                "percentage_adjustment": Decimal("10.00"),
            },
            {
                "name": "Precio reducido",
                "percentage_adjustment": Decimal("-5.00"),
            },
        ]

        profiles = {}

        for item in data:
            profile, _ = PricingProfile.objects.update_or_create(
                name=item["name"],
                defaults={
                    "percentage_adjustment": (item["percentage_adjustment"]),
                },
            )

            profiles[item["name"]] = profile

        return profiles

    def create_machines(self, pricing_profiles):
        data = [
            {
                "identifier": "VM-001",
                "name": "Facultad",
                "location": "Edificio principal · Planta baja",
                "serial_number": "VM-01-001",
                "pricing_profile": "Estándar",
                "rows": 4,
                "columns": 4,
            },
            {
                "identifier": "VM-002",
                "name": "Biblioteca",
                "location": "Biblioteca · Zona de estudio",
                "serial_number": "VM-01-002",
                "pricing_profile": "Precio reducido",
                "rows": 4,
                "columns": 4,
            },
            {
                "identifier": "VM-003",
                "name": "Pabellón deportivo",
                "location": "Pabellón · Entrada principal",
                "serial_number": "VM-01-003",
                "pricing_profile": "Ubicación premium",
                "rows": 4,
                "columns": 4,
            },
            {
                "identifier": "VM-004",
                "name": "Oficinas",
                "location": "Edificio administrativo · Planta 1",
                "serial_number": "VM-01-004",
                "pricing_profile": "Estándar",
                "rows": 4,
                "columns": 4,
            },
        ]

        machines = {}

        for item in data:
            machine, _ = Machine.objects.update_or_create(
                identifier=item["identifier"],
                defaults={
                    "name": item["name"],
                    "location": item["location"],
                    "serial_number": item["serial_number"],
                    "pricing_profile": pricing_profiles[item["pricing_profile"]],
                    "rows": item["rows"],
                    "columns": item["columns"],
                },
            )

            machines[item["identifier"]] = machine

        return machines

    def create_price_overrides(
        self,
        products,
        machines,
    ):
        data = [
            {
                "machine": "VM-001",
                "product": "VimaCafé",
                "percentage_adjustment": Decimal("5.00"),
            },
            {
                "machine": "VM-002",
                "product": "VimaAgua",
                "percentage_adjustment": Decimal("0.00"),
            },
            {
                "machine": "VM-003",
                "product": "VimaAgua",
                "percentage_adjustment": Decimal("0.00"),
            },
            {
                "machine": "VM-004",
                "product": "VimaCappuccino",
                "percentage_adjustment": Decimal("8.00"),
            },
        ]

        for item in data:
            machine = machines[item["machine"]]
            product = products[item["product"]]

            override = MachinePriceOverride.objects.filter(
                machine=machine,
                product=product,
            ).first()

            if override is None:
                override = MachinePriceOverride(
                    machine=machine,
                    product=product,
                    percentage_adjustment=(item["percentage_adjustment"]),
                )
            else:
                override.percentage_adjustment = item["percentage_adjustment"]

            override.full_clean()
            override.save()

    def create_layout(
        self,
        *,
        machine,
        name,
        assignments,
        products,
    ):
        layout, created = MachineLayout.objects.get_or_create(
            machine=machine,
            name=name,
        )

        if not created:
            return layout

        for index, product_name in enumerate(assignments):
            row = index // 4 + 1
            column = index % 4 + 1

            row_letter = chr(ord("A") + row - 1)

            MachinePosition.objects.create(
                layout=layout,
                identifier=f"{row_letter}{column}",
                row=row,
                column=column,
                product=(products[product_name] if product_name is not None else None),
            )

        layout.status = MachineLayout.Status.REGISTERED
        layout.save(update_fields=["status"])

        return layout

    def activate_layout_at(
        self,
        layout,
        moment,
    ):
        if layout.activations.exists():
            return

        with patch(
            "django.utils.timezone.now",
            return_value=moment,
        ):
            activate_machine_layout(layout)

    def demo_datetime(
        self,
        year,
        month,
        day,
        hour=8,
        minute=0,
    ):
        original_date = date(year, month, day)

        reference_date = date(2026, 9, 20)

        target_date = timezone.localdate() - timedelta(days=1)

        offset = target_date - reference_date
        shifted_date = original_date + offset

        return timezone.make_aware(
            datetime(
                shifted_date.year,
                shifted_date.month,
                shifted_date.day,
                hour,
                minute,
            )
        )

    def create_layouts(
        self,
        products,
        machines,
    ):

        layouts = {}

        vm001_old = self.create_layout(
            machine=machines["VM-001"],
            name="Disposición inicial",
            assignments=[
                "VimaCola",
                "VimaAgua",
                "VimaTea Limón",
                "VimaNaranja",
                "VimaPatatas",
                "VimaBarrita",
                "VimaChocolate",
                "VimaZumo Naranja",
                "VimaCafé",
                "VimaCappuccino",
                None,
                None,
                None,
                None,
                None,
                None,
            ],
            products=products,
        )

        vm001_current = self.create_layout(
            machine=machines["VM-001"],
            name="Disposición actual",
            assignments=[
                "VimaCola Zero",
                "VimaAgua",
                "VimaTea Limón",
                "VimaNaranja",
                "VimaPatatas",
                "VimaBarrita",
                "VimaChocolate",
                "VimaZumo Naranja",
                "VimaCafé",
                "VimaCappuccino",
                "VimaAgua Grande",
                None,
                None,
                None,
                None,
                None,
            ],
            products=products,
        )

        self.activate_layout_at(
            vm001_old,
            self.demo_datetime(
                2026,
                7,
                10,
            ),
        )

        self.activate_layout_at(
            vm001_current,
            self.demo_datetime(
                2026,
                8,
                20,
            ),
        )

        layouts["VM-001"] = {
            "old": vm001_old,
            "current": vm001_current,
        }

        vm002_current = self.create_layout(
            machine=machines["VM-002"],
            name="Disposición principal",
            assignments=[
                "VimaAgua",
                "VimaTea Limón",
                "VimaCola Zero",
                "VimaZumo Naranja",
                "VimaBarrita",
                "VimaChocolate",
                "VimaCafé",
                "VimaCappuccino",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ],
            products=products,
        )

        self.activate_layout_at(
            vm002_current,
            self.demo_datetime(
                2026,
                8,
                5,
            ),
        )

        layouts["VM-002"] = {
            "current": vm002_current,
        }

        vm003_old = self.create_layout(
            machine=machines["VM-003"],
            name="Disposición verano",
            assignments=[
                "VimaAgua",
                "VimaAgua Grande",
                "VimaNaranja",
                "VimaTea Limón",
                "VimaCola",
                "VimaCola Zero",
                "VimaPatatas",
                "VimaBarrita",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ],
            products=products,
        )

        vm003_current = self.create_layout(
            machine=machines["VM-003"],
            name="Disposición actual",
            assignments=[
                "VimaAgua",
                "VimaAgua Grande",
                "VimaCola Zero",
                "VimaTea Limón",
                "VimaChocolate",
                "VimaBarrita",
                "VimaPatatas",
                "VimaNaranja",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ],
            products=products,
        )

        self.activate_layout_at(
            vm003_old,
            self.demo_datetime(
                2026,
                7,
                1,
            ),
        )

        self.activate_layout_at(
            vm003_current,
            self.demo_datetime(
                2026,
                8,
                30,
            ),
        )

        layouts["VM-003"] = {
            "old": vm003_old,
            "current": vm003_current,
        }

        layouts["VM-004"] = {}

        return layouts

    def create_purchase(
        self,
        *,
        products,
        purchased_at,
        supplier,
        document_reference,
        status,
        lines,
    ):
        existing = Purchase.objects.filter(
            document_reference=document_reference,
        ).first()

        if existing is not None:
            return existing

        purchase = Purchase.objects.create(
            purchased_at=purchased_at,
            supplier=supplier,
            document_reference=document_reference,
            status=status,
        )

        for product_name, quantity, unit_cost in lines:
            PurchaseLine.objects.create(
                purchase=purchase,
                product=products[product_name],
                quantity=quantity,
                unit_price_excl_vat=Decimal(unit_cost),
            )

        return purchase

    def create_purchases(self, products):
        purchases = {}

        purchases["PUR-001"] = self.create_purchase(
            products=products,
            purchased_at=self.demo_datetime(
                2026,
                7,
                5,
                9,
                30,
            ),
            supplier="Distribuciones del Sur",
            document_reference="FAC-2026-0705",
            status=Purchase.Status.REGISTERED,
            lines=[
                ("VimaAgua", 120, "0.32"),
                ("VimaAgua Grande", 60, "0.48"),
                ("VimaCola", 90, "0.72"),
                ("VimaCola Zero", 5, "0.74"),
                ("VimaNaranja", 70, "0.68"),
            ],
        )

        purchases["PUR-002"] = self.create_purchase(
            products=products,
            purchased_at=self.demo_datetime(
                2026,
                7,
                18,
                11,
                0,
            ),
            supplier="Snacks Andalucía",
            document_reference="FAC-2026-0718",
            status=Purchase.Status.REGISTERED,
            lines=[
                ("VimaPatatas", 100, "0.55"),
                ("VimaBarrita", 90, "0.62"),
                ("VimaChocolate", 80, "0.78"),
            ],
        )

        purchases["PUR-003"] = self.create_purchase(
            products=products,
            purchased_at=self.demo_datetime(
                2026,
                8,
                2,
                10,
                15,
            ),
            supplier="Vending Supply Iberia",
            document_reference="FAC-2026-0802",
            status=Purchase.Status.REGISTERED,
            lines=[
                ("VimaTea Limón", 90, "0.76"),
                ("VimaZumo Naranja", 70, "0.88"),
                ("VimaCafé", 110, "0.38"),
                ("VimaCappuccino", 90, "0.52"),
            ],
        )

        purchases["PUR-004"] = self.create_purchase(
            products=products,
            purchased_at=self.demo_datetime(
                2026,
                8,
                24,
                9,
                0,
            ),
            supplier="Distribuciones del Sur",
            document_reference="FAC-2026-0824",
            status=Purchase.Status.REGISTERED,
            lines=[
                ("VimaAgua", 100, "0.35"),
                ("VimaAgua Grande", 50, "0.51"),
                ("VimaCola", 70, "0.75"),
                ("VimaCola Zero", 5, "0.71"),
                ("VimaNaranja", 60, "0.70"),
                ("VimaTea Limón", 70, "0.79"),
            ],
        )

        purchases["PUR-005"] = self.create_purchase(
            products=products,
            purchased_at=self.demo_datetime(
                2026,
                9,
                6,
                12,
                0,
            ),
            supplier="Snacks Andalucía",
            document_reference="FAC-2026-0906",
            status=Purchase.Status.REGISTERED,
            lines=[
                ("VimaPatatas", 80, "0.58"),
                ("VimaBarrita", 80, "0.60"),
                ("VimaChocolate", 70, "0.82"),
                ("VimaZumo Naranja", 60, "0.91"),
            ],
        )

        purchases["PUR-006"] = self.create_purchase(
            products=products,
            purchased_at=self.demo_datetime(
                2026,
                9,
                14,
                8,
                45,
            ),
            supplier="Vending Supply Iberia",
            document_reference="FAC-2026-0914",
            status=Purchase.Status.REGISTERED,
            lines=[
                ("VimaCafé", 90, "0.42"),
                ("VimaCappuccino", 70, "0.56"),
                ("VimaCola Zero", 1, "0.77"),
                ("VimaAgua", 80, "0.34"),
            ],
        )
        purchases["PUR-DRAFT"] = self.create_purchase(
            products=products,
            purchased_at=self.demo_datetime(
                2026,
                9,
                18,
                16,
                30,
            ),
            supplier="Distribuciones del Sur",
            document_reference="PED-2026-0918",
            status=Purchase.Status.DRAFT,
            lines=[
                ("VimaAgua", 100, "0.33"),
                ("VimaCola", 70, "0.73"),
                ("VimaTea Limón", 60, "0.78"),
            ],
        )

        purchases["PUR-CANCELLED"] = self.create_purchase(
            products=products,
            purchased_at=self.demo_datetime(
                2026,
                8,
                15,
                13,
                0,
            ),
            supplier="Proveedor Mediterráneo",
            document_reference="FAC-ANULADA-0815",
            status=Purchase.Status.CANCELLED,
            lines=[
                ("VimaChocolate", 50, "0.74"),
                ("VimaBarrita", 50, "0.57"),
            ],
        )

        return purchases

    def create_replenishment(
        self,
        *,
        products,
        machine,
        replenished_at,
        lines,
        status=Replenishment.Status.REGISTERED,
    ):
        existing = Replenishment.objects.filter(
            machine=machine,
            replenished_at=replenished_at,
        ).first()

        if existing is not None:
            return existing

        replenishment = Replenishment.objects.create(
            machine=machine,
            replenished_at=replenished_at,
            status=Replenishment.Status.DRAFT,
        )

        for product_name, quantity in lines:
            ReplenishmentLine.objects.create(
                replenishment=replenishment,
                product=products[product_name],
                quantity=quantity,
            )

        if status == Replenishment.Status.DRAFT:
            return replenishment

        stock_errors = get_replenishment_stock_errors(
            replenishment,
        )

        layout_errors = get_replenishment_layout_errors(
            replenishment,
        )

        if stock_errors or layout_errors:
            raise CommandError(
                (
                    "No se pudo registrar la reposición demo "
                    f"de {machine.identifier} "
                    f"en {replenished_at:%d/%m/%Y %H:%M}. "
                    f"Errores de stock: {stock_errors}. "
                    f"Errores de disposición: {layout_errors}."
                )
            )

        if status == Replenishment.Status.CANCELLED:
            replenishment.status = Replenishment.Status.CANCELLED
        else:
            replenishment.status = Replenishment.Status.REGISTERED

        replenishment.save(
            update_fields=["status"],
        )

        return replenishment

    def create_replenishments(
        self,
        products,
        machines,
    ):
        replenishments = {}

        replenishments["REP-001"] = self.create_replenishment(
            products=products,
            machine=machines["VM-001"],
            replenished_at=self.demo_datetime(
                2026,
                7,
                12,
                9,
                0,
            ),
            lines=[
                ("VimaAgua", 18),
                ("VimaCola", 16),
                ("VimaNaranja", 12),
            ],
        )

        replenishments["REP-002"] = self.create_replenishment(
            products=products,
            machine=machines["VM-001"],
            replenished_at=self.demo_datetime(
                2026,
                7,
                24,
                10,
                30,
            ),
            lines=[
                ("VimaCola", 10),
                ("VimaPatatas", 14),
                ("VimaBarrita", 10),
                ("VimaChocolate", 8),
            ],
        )

        replenishments["REP-003"] = self.create_replenishment(
            products=products,
            machine=machines["VM-001"],
            replenished_at=self.demo_datetime(
                2026,
                8,
                7,
                8,
                45,
            ),
            lines=[
                ("VimaAgua", 12),
                ("VimaTea Limón", 1),
                ("VimaZumo Naranja", 10),
                ("VimaCafé", 15),
                ("VimaCappuccino", 10),
            ],
        )

        replenishments["REP-004"] = self.create_replenishment(
            products=products,
            machine=machines["VM-001"],
            replenished_at=self.demo_datetime(
                2026,
                8,
                22,
                9,
                15,
            ),
            lines=[
                ("VimaCola Zero", 3),
                ("VimaAgua", 12),
                ("VimaAgua Grande", 10),
                ("VimaCafé", 12),
            ],
        )

        replenishments["REP-005"] = self.create_replenishment(
            products=products,
            machine=machines["VM-001"],
            replenished_at=self.demo_datetime(
                2026,
                9,
                12,
                10,
                0,
            ),
            lines=[
                ("VimaCola Zero", 1),
                ("VimaTea Limón", 1),
                ("VimaPatatas", 10),
                ("VimaChocolate", 8),
                ("VimaCappuccino", 8),
            ],
        )

        replenishments["REP-006"] = self.create_replenishment(
            products=products,
            machine=machines["VM-002"],
            replenished_at=self.demo_datetime(
                2026,
                8,
                8,
                11,
                0,
            ),
            lines=[
                ("VimaAgua", 15),
                ("VimaCola Zero", 1),
                ("VimaZumo Naranja", 8),
                ("VimaBarrita", 10),
                ("VimaChocolate", 10),
                ("VimaCafé", 12),
                ("VimaCappuccino", 8),
            ],
        )

        replenishments["REP-007"] = self.create_replenishment(
            products=products,
            machine=machines["VM-002"],
            replenished_at=self.demo_datetime(
                2026,
                8,
                27,
                9,
                40,
            ),
            lines=[
                ("VimaAgua", 10),
                ("VimaCola Zero", 2),
                ("VimaBarrita", 8),
                ("VimaCafé", 10),
            ],
        )

        replenishments["REP-008"] = self.create_replenishment(
            products=products,
            machine=machines["VM-002"],
            replenished_at=self.demo_datetime(
                2026,
                9,
                16,
                12,
                15,
            ),
            lines=[
                ("VimaAgua", 12),
                ("VimaTea Limón", 2),
                ("VimaChocolate", 8),
                ("VimaCappuccino", 8),
            ],
        )

        replenishments["REP-CANCELLED"] = self.create_replenishment(
            products=products,
            machine=machines["VM-002"],
            replenished_at=self.demo_datetime(
                2026,
                9,
                2,
                16,
                0,
            ),
            lines=[
                ("VimaAgua", 6),
                ("VimaBarrita", 5),
            ],
            status=Replenishment.Status.CANCELLED,
        )

        replenishments["REP-009"] = self.create_replenishment(
            products=products,
            machine=machines["VM-003"],
            replenished_at=self.demo_datetime(
                2026,
                7,
                9,
                8,
                30,
            ),
            lines=[
                ("VimaAgua", 20),
                ("VimaAgua Grande", 12),
                ("VimaNaranja", 12),
                ("VimaCola", 14),
            ],
        )

        replenishments["REP-010"] = self.create_replenishment(
            products=products,
            machine=machines["VM-003"],
            replenished_at=self.demo_datetime(
                2026,
                7,
                23,
                17,
                0,
            ),
            lines=[
                ("VimaPatatas", 12),
                ("VimaBarrita", 10),
                ("VimaCola", 8),
                ("VimaAgua", 10),
            ],
        )

        replenishments["REP-011"] = self.create_replenishment(
            products=products,
            machine=machines["VM-003"],
            replenished_at=self.demo_datetime(
                2026,
                8,
                9,
                11,
                30,
            ),
            lines=[
                ("VimaAgua", 12),
                ("VimaTea Limón", 2),
                ("VimaCola Zero", 1),
                ("VimaBarrita", 8),
            ],
        )

        replenishments["REP-012"] = self.create_replenishment(
            products=products,
            machine=machines["VM-003"],
            replenished_at=self.demo_datetime(
                2026,
                9,
                2,
                9,
                30,
            ),
            lines=[
                ("VimaAgua", 14),
                ("VimaAgua Grande", 10),
                ("VimaCola Zero", 2),
                ("VimaChocolate", 10),
                ("VimaPatatas", 10),
            ],
        )

        replenishments["REP-013"] = self.create_replenishment(
            products=products,
            machine=machines["VM-003"],
            replenished_at=self.demo_datetime(
                2026,
                9,
                17,
                10,
                45,
            ),
            lines=[
                ("VimaAgua", 10),
                ("VimaTea Limón", 1),
                ("VimaBarrita", 8),
                ("VimaNaranja", 8),
                ("VimaChocolate", 6),
            ],
        )

        replenishments["REP-DRAFT"] = self.create_replenishment(
            products=products,
            machine=machines["VM-002"],
            replenished_at=self.demo_datetime(
                2026,
                9,
                19,
                15,
                0,
            ),
            lines=[
                ("VimaAgua", 8),
                ("VimaTea Limón", 6),
            ],
            status=Replenishment.Status.DRAFT,
        )

        replenishments["REP-NO-LAYOUT"] = self.create_replenishment(
            products=products,
            machine=machines["VM-004"],
            replenished_at=self.demo_datetime(
                2026,
                9,
                19,
                16,
                30,
            ),
            lines=[
                ("VimaAgua", 10),
            ],
            status=Replenishment.Status.DRAFT,
        )

        return replenishments

    def build_sale_payload(
        self,
        *,
        machines,
        event_id,
        machine_identifier,
        selection,
        occurred_at,
        quantity=1,
        dispense_type=Sale.DispenseType.PAID,
        payment_method="card",
    ):
        machine = machines.get(machine_identifier)

        product = None

        if machine is not None:
            product = get_product_for_selection(
                machine,
                selection,
                occurred_at,
            )

        unit_price = None
        amount_received = None

        if (
            dispense_type == Sale.DispenseType.PAID
            and machine is not None
            and product is not None
        ):
            unit_price = get_product_price_for_machine(
                machine,
                product,
            )

            amount_received = unit_price * Decimal(quantity)

        if dispense_type == Sale.DispenseType.FREE:
            payment_method = ""

        return {
            "event_id": event_id,
            "machine_identifier": machine_identifier,
            "selection": selection,
            "occurred_at": occurred_at.isoformat(),
            "quantity": quantity,
            "dispense_type": dispense_type,
            "unit_price": (str(unit_price) if unit_price is not None else None),
            "amount_received": (
                str(amount_received) if amount_received is not None else None
            ),
            "payment_method": payment_method,
        }

    def create_telemetry_sale(
        self,
        *,
        machines,
        event_id,
        machine_identifier,
        selection,
        occurred_at,
        quantity=1,
        dispense_type=Sale.DispenseType.PAID,
        payment_method="card",
    ):
        existing = (
            Sale.objects.filter(
                event_id=event_id,
            )
            .order_by("pk")
            .first()
        )

        if existing is not None:
            return existing

        payload = self.build_sale_payload(
            machines=machines,
            event_id=event_id,
            machine_identifier=machine_identifier,
            selection=selection,
            occurred_at=occurred_at,
            quantity=quantity,
            dispense_type=dispense_type,
            payment_method=payment_method,
        )

        sale, _ = receive_sale(payload)

        return sale

    def create_sales(
        self,
        products,
        machines,
    ):
        sales_data = [
            (
                "SALE-001",
                "VM-001",
                "A1",
                self.demo_datetime(2026, 7, 14, 10, 15),
                2,
                "card",
            ),
            (
                "SALE-002",
                "VM-001",
                "A2",
                self.demo_datetime(2026, 7, 15, 12, 30),
                3,
                "cash",
            ),
            (
                "SALE-003",
                "VM-001",
                "B1",
                self.demo_datetime(2026, 7, 26, 17, 20),
                2,
                "card",
            ),
            (
                "SALE-004",
                "VM-001",
                "A1",
                self.demo_datetime(2026, 8, 10, 11, 10),
                1,
                "cash",
            ),
            (
                "SALE-005",
                "VM-001",
                "C1",
                self.demo_datetime(2026, 8, 12, 9, 45),
                2,
                "card",
            ),
            (
                "SALE-006",
                "VM-001",
                "A3",
                self.demo_datetime(2026, 8, 18, 16, 30),
                1,
                "card",
            ),
            (
                "SALE-007",
                "VM-001",
                "A1",
                self.demo_datetime(2026, 8, 23, 11, 20),
                2,
                "card",
            ),
            (
                "SALE-008",
                "VM-001",
                "A2",
                self.demo_datetime(2026, 8, 23, 15, 40),
                1,
                "cash",
            ),
            (
                "SALE-009",
                "VM-001",
                "C3",
                self.demo_datetime(2026, 8, 29, 13, 15),
                1,
                "card",
            ),
            (
                "SALE-010",
                "VM-001",
                "A1",
                self.demo_datetime(2026, 9, 3, 10, 30),
                1,
                "card",
            ),
            (
                "SALE-011",
                "VM-001",
                "B3",
                self.demo_datetime(2026, 9, 3, 17, 10),
                1,
                "cash",
            ),
            (
                "SALE-012",
                "VM-001",
                "C1",
                self.demo_datetime(2026, 9, 7, 9, 20),
                2,
                "card",
            ),
            (
                "SALE-013",
                "VM-001",
                "A3",
                self.demo_datetime(2026, 9, 13, 12, 10),
                1,
                "card",
            ),
            (
                "SALE-014",
                "VM-001",
                "B1",
                self.demo_datetime(2026, 9, 13, 18, 20),
                2,
                "cash",
            ),
            (
                "SALE-015",
                "VM-001",
                "A1",
                self.demo_datetime(2026, 9, 18, 11, 30),
                1,
                "card",
            ),
            (
                "SALE-016",
                "VM-001",
                "A2",
                self.demo_datetime(2026, 9, 20, 10, 10),
                2,
                "card",
            ),
            (
                "SALE-017",
                "VM-002",
                "A1",
                self.demo_datetime(2026, 8, 10, 10, 0),
                2,
                "card",
            ),
            (
                "SALE-018",
                "VM-002",
                "A3",
                self.demo_datetime(2026, 8, 18, 13, 20),
                1,
                "cash",
            ),
            (
                "SALE-019",
                "VM-002",
                "B3",
                self.demo_datetime(2026, 8, 18, 17, 35),
                2,
                "card",
            ),
            (
                "SALE-020",
                "VM-002",
                "A1",
                self.demo_datetime(2026, 8, 28, 9, 50),
                2,
                "card",
            ),
            (
                "SALE-021",
                "VM-002",
                "B1",
                self.demo_datetime(2026, 9, 1, 16, 10),
                1,
                "cash",
            ),
            (
                "SALE-022",
                "VM-002",
                "A3",
                self.demo_datetime(2026, 9, 5, 12, 40),
                2,
                "card",
            ),
            (
                "SALE-023",
                "VM-002",
                "B3",
                self.demo_datetime(2026, 9, 10, 10, 25),
                1,
                "card",
            ),
            (
                "SALE-024",
                "VM-002",
                "A2",
                self.demo_datetime(2026, 9, 17, 11, 0),
                2,
                "card",
            ),
            (
                "SALE-025",
                "VM-002",
                "B4",
                self.demo_datetime(2026, 9, 19, 16, 20),
                1,
                "cash",
            ),
            (
                "SALE-026",
                "VM-002",
                "A1",
                self.demo_datetime(2026, 9, 20, 12, 15),
                1,
                "card",
            ),
            (
                "SALE-027",
                "VM-003",
                "A1",
                self.demo_datetime(2026, 7, 11, 11, 30),
                2,
                "card",
            ),
            (
                "SALE-028",
                "VM-003",
                "B1",
                self.demo_datetime(2026, 7, 11, 18, 15),
                1,
                "cash",
            ),
            (
                "SALE-029",
                "VM-003",
                "B3",
                self.demo_datetime(2026, 7, 25, 10, 10),
                2,
                "card",
            ),
            (
                "SALE-030",
                "VM-003",
                "A2",
                self.demo_datetime(2026, 7, 25, 17, 40),
                1,
                "card",
            ),
            (
                "SALE-031",
                "VM-003",
                "A4",
                self.demo_datetime(2026, 8, 12, 16, 20),
                2,
                "cash",
            ),
            (
                "SALE-032",
                "VM-003",
                "B2",
                self.demo_datetime(2026, 8, 18, 12, 0),
                1,
                "card",
            ),
            (
                "SALE-033",
                "VM-003",
                "B1",
                self.demo_datetime(2026, 9, 3, 10, 15),
                2,
                "card",
            ),
            (
                "SALE-034",
                "VM-003",
                "A3",
                self.demo_datetime(2026, 9, 4, 18, 10),
                1,
                "cash",
            ),
            (
                "SALE-035",
                "VM-003",
                "A1",
                self.demo_datetime(2026, 9, 8, 12, 30),
                2,
                "card",
            ),
            (
                "SALE-036",
                "VM-003",
                "B3",
                self.demo_datetime(2026, 9, 11, 19, 0),
                1,
                "cash",
            ),
            (
                "SALE-037",
                "VM-003",
                "A2",
                self.demo_datetime(2026, 9, 15, 10, 40),
                2,
                "card",
            ),
            (
                "SALE-038",
                "VM-003",
                "A4",
                self.demo_datetime(2026, 9, 18, 11, 15),
                1,
                "card",
            ),
            (
                "SALE-039",
                "VM-003",
                "B4",
                self.demo_datetime(2026, 9, 18, 18, 25),
                1,
                "cash",
            ),
            (
                "SALE-040",
                "VM-003",
                "B1",
                self.demo_datetime(2026, 9, 20, 13, 30),
                1,
                "card",
            ),
        ]

        for (
            event_id,
            machine_identifier,
            selection,
            occurred_at,
            quantity,
            payment_method,
        ) in sales_data:
            self.create_telemetry_sale(
                machines=machines,
                event_id=event_id,
                machine_identifier=machine_identifier,
                selection=selection,
                occurred_at=occurred_at,
                quantity=quantity,
                payment_method=payment_method,
            )

        self.create_special_sales(
            products,
            machines,
        )

    def create_special_sales(
        self,
        products,
        machines,
    ):

        self.create_telemetry_sale(
            machines=machines,
            event_id="FREE-001",
            machine_identifier="VM-001",
            selection="C1",
            occurred_at=self.demo_datetime(
                2026,
                9,
                16,
                11,
                30,
            ),
            quantity=1,
            dispense_type=Sale.DispenseType.FREE,
            payment_method="",
        )

        if not Sale.objects.filter(
            event_id="MANUAL-001",
        ).exists():
            machine = machines["VM-001"]

            occurred_at = self.demo_datetime(
                2026,
                9,
                6,
                17,
                15,
            )

            product = get_product_for_selection(
                machine,
                "C2",
                occurred_at,
            )

            price = get_product_price_for_machine(
                machine,
                product,
            )

            create_manual_sale(
                event_id="MANUAL-001",
                machine=machine,
                product=None,
                selection="C2",
                occurred_at=occurred_at,
                quantity=1,
                dispense_type=Sale.DispenseType.PAID,
                unit_price=price,
                amount_received=price,
                payment_method="cash",
            )

        voided_sale = self.create_telemetry_sale(
            machines=machines,
            event_id="VOIDED-001",
            machine_identifier="VM-001",
            selection="B2",
            occurred_at=self.demo_datetime(
                2026,
                9,
                14,
                12,
                30,
            ),
            quantity=1,
            payment_method="card",
        )

        if voided_sale.status == Sale.Status.RESOLVED:
            with patch(
                "django.utils.timezone.now",
                return_value=self.demo_datetime(
                    2026,
                    9,
                    15,
                    9,
                    0,
                ),
            ):
                void_sale(
                    voided_sale,
                    "Operación anulada durante la revisión diaria.",
                )

        self.create_telemetry_sale(
            machines=machines,
            event_id="PENDING-001",
            machine_identifier="VM-004",
            selection="A1",
            occurred_at=self.demo_datetime(
                2026,
                9,
                19,
                14,
                20,
            ),
            quantity=1,
            payment_method="card",
        )

        self.create_demo_conflict(
            machines=machines,
            event_id="CONFLICT-001",
            machine_identifier="VM-002",
            selection="A1",
            occurred_at=self.demo_datetime(
                2026,
                9,
                18,
                12,
                30,
            ),
            reject=False,
        )

        self.create_demo_conflict(
            machines=machines,
            event_id="CONFLICT-002",
            machine_identifier="VM-003",
            selection="A3",
            occurred_at=self.demo_datetime(
                2026,
                9,
                19,
                17,
                30,
            ),
            reject=True,
        )

    def create_demo_conflict(
        self,
        *,
        machines,
        event_id,
        machine_identifier,
        selection,
        occurred_at,
        reject=False,
    ):
        existing_sales = list(
            Sale.objects.filter(
                event_id=event_id,
            ).order_by("pk")
        )

        if not existing_sales:
            original_payload = self.build_sale_payload(
                machines=machines,
                event_id=event_id,
                machine_identifier=machine_identifier,
                selection=selection,
                occurred_at=occurred_at,
                quantity=1,
                payment_method="card",
            )

            original_sale, _ = receive_sale(
                original_payload,
            )

        else:
            original_sale = existing_sales[0]

        existing_sales = list(
            Sale.objects.filter(
                event_id=event_id,
            ).order_by("pk")
        )

        if len(existing_sales) < 2:
            conflict_payload = self.build_sale_payload(
                machines=machines,
                event_id=event_id,
                machine_identifier=machine_identifier,
                selection=selection,
                occurred_at=occurred_at,
                quantity=1,
                payment_method="card",
            )

            original_price = Decimal(conflict_payload["unit_price"])

            conflict_price = (original_price - Decimal("0.10")).quantize(
                Decimal("0.01")
            )

            conflict_payload["unit_price"] = str(conflict_price)

            conflict_payload["amount_received"] = str(conflict_price)

            conflict_sale, _ = receive_sale(
                conflict_payload,
            )

        else:
            conflict_sale = existing_sales[1]

        if reject and conflict_sale.status == Sale.Status.CONFLICT:
            conflict_sale = reject_sale_conflict(
                conflict_sale,
            )

        return original_sale, conflict_sale
