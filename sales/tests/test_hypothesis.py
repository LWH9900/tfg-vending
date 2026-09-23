"""
Pruebas basadas en propiedades y robustez con Hypothesis.

Los casos HYP-xxx marcados como expectedFailure documentan defectos
descubiertos durante las pruebas y se conservan como pruebas
de regresión.

Todas las clases están etiquetadas con "hypothesis" para poder ejecutar
estas pruebas de forma independiente de la suite habitual.
"""

import json
import sys
import unittest
from datetime import date, datetime, timedelta
from datetime import timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import Client, SimpleTestCase, tag
from django.urls import reverse
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from inventory.models import Category, Product
from inventory.services import get_machine_stock, get_total_stock, get_warehouse_stock
from machines.models import (
    Machine,
    MachineLayout,
    MachineLayoutActivation,
    MachinePosition,
    MachinePriceOverride,
    PricingProfile,
)
from machines.services.layouts import (
    activate_machine_layout,
    get_current_machine_layout_activation,
)
from purchases.models import Purchase, PurchaseLine
from replenishments.models import Replenishment, ReplenishmentLine
from sales.models import Sale
from sales.services import (
    _get_payload_hash,
    _parse_occurred_at,
    _parse_optional_decimal,
    _parse_positive_integer,
    create_manual_sale,
    get_sales_projection,
    void_sale,
)

SAFE_TEXT = st.text(
    alphabet=st.characters(exclude_categories=("Cs",)),
    max_size=80,
)
JSON_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**30), max_value=10**30),
    st.floats(allow_nan=False, allow_infinity=False, width=64),
    SAFE_TEXT,
)
JSON_VALUES = st.recursive(
    JSON_SCALARS,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(SAFE_TEXT, children, max_size=5),
    ),
    max_leaves=15,
)


@tag("hypothesis")
class SaleParsingHypothesisTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_hyp_001_superscript_digit_causes_value_error(self):
        """
        HYP-001
        str.isdigit() acepta '²' pero int('²') lanza ValueError.
        """

        try:
            _parse_positive_integer(
                "²",
                "quantity",
            )

        except ValidationError:
            return

        self.fail(
            "La entrada '²' debería rechazarse mediante "
            "ValidationError, pero actualmente provoca "
            "una excepción interna."
        )

    @unittest.expectedFailure
    def test_hyp_002_very_long_integer_causes_value_error(self):
        """
        HYP-002

        Una cadena formada únicamente por dígitos supera
        la validación con isdigit(), pero int() lanza ValueError
        cuando se supera el límite de conversión de Python.
        """

        limit = sys.get_int_max_str_digits()

        if limit == 0:
            self.skipTest("El límite de conversión de enteros está desactivado.")

        value = "9" * (limit + 1)

        try:
            _parse_positive_integer(
                value,
                "quantity",
            )

        except ValidationError:
            return

        self.fail(
            "Una cadena numérica excesivamente larga debería "
            "rechazarse mediante ValidationError, pero actualmente "
            "provoca una excepción interna."
        )

    @unittest.expectedFailure
    def test_hyp_008_impossible_iso_date_causes_value_error(self):
        """
        HYP-008

        Comprueba que una fecha con formato ISO válido, pero que no es válida
        en el calendario, por ejemplo por pertenecer a un año no bisiesto,
        se rechace de forma controlada.

        parse_datetime() lanza ValueError y actualmente
        _parse_occurred_at() no lo transforma en ValidationError.
        """

        value = "2026-02-29T10:00:00Z"

        try:
            _parse_occurred_at(value)

        except ValidationError:
            return

        except ValueError:
            self.fail(
                "Una fecha ISO imposible ha provocado ValueError "
                "en lugar de ValidationError."
            )

        self.fail("Una fecha imposible ha sido aceptada.")


@tag("hypothesis")
class SaleServicePropertyTests(SimpleTestCase):
    @settings(max_examples=150)
    @given(value=st.integers(min_value=1, max_value=10**100))
    def test_positive_integer_parser_round_trips_ascii_digits(self, value):
        padded_value = f"  {value}  "

        self.assertEqual(
            _parse_positive_integer(padded_value, "quantity"),
            value,
        )

    @settings(max_examples=200)
    @given(
        value=st.one_of(
            st.none(),
            st.booleans(),
            st.integers(min_value=-(10**100), max_value=10**100),
            st.floats(allow_nan=True, allow_infinity=True),
            st.text(
                alphabet=st.characters(
                    min_codepoint=0,
                    max_codepoint=127,
                ),
                max_size=100,
            ),
        )
    )
    def test_integer_parser_returns_positive_int_or_validation_error(self, value):
        try:
            parsed_value = _parse_positive_integer(value, "quantity")
        except ValidationError:
            return

        self.assertIs(type(parsed_value), int)
        self.assertGreaterEqual(parsed_value, 1)

    @settings(max_examples=150)
    @given(
        value=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("99999999.999999"),
            allow_nan=False,
            allow_infinity=False,
            places=6,
        )
    )
    def test_optional_decimal_parser_preserves_non_negative_values(self, value):
        self.assertEqual(
            _parse_optional_decimal(str(value), "unit_price"),
            value,
        )

    @settings(max_examples=200)
    @given(
        value=st.one_of(
            st.none(),
            st.booleans(),
            st.integers(min_value=-(10**30), max_value=10**30),
            st.floats(allow_nan=True, allow_infinity=True),
            st.decimals(allow_nan=True, allow_infinity=True),
            SAFE_TEXT,
        )
    )
    def test_decimal_parser_returns_valid_decimal_or_validation_error(self, value):
        try:
            parsed_value = _parse_optional_decimal(value, "unit_price")
        except ValidationError:
            return

        if value in (None, ""):
            self.assertIsNone(parsed_value)
        else:
            self.assertIsInstance(parsed_value, Decimal)
            self.assertTrue(parsed_value.is_finite())
            self.assertGreaterEqual(parsed_value, 0)

    @settings(max_examples=100)
    @given(
        value=st.datetimes(
            min_value=datetime(2000, 1, 1),
            max_value=datetime(2099, 12, 31, 23, 59, 59),
            timezones=st.just(datetime_timezone.utc),
        )
    )
    def test_occurred_at_parser_round_trips_utc_iso_datetimes(self, value):
        serialized = value.isoformat().replace("+00:00", "Z")

        self.assertEqual(_parse_occurred_at(serialized), value)

    @settings(max_examples=150)
    @given(
        value=st.one_of(
            SAFE_TEXT,
            st.integers(),
            st.none(),
            st.datetimes(timezones=st.none()),
        )
    )
    def test_occurred_at_parser_returns_aware_datetime_or_validation_error(
        self,
        value,
    ):
        try:
            parsed_value = _parse_occurred_at(value)
        except ValidationError:
            return

        self.assertIsNotNone(parsed_value.tzinfo)
        self.assertIsNotNone(parsed_value.utcoffset())

    @settings(max_examples=150)
    @given(payload=st.dictionaries(SAFE_TEXT, JSON_VALUES, max_size=10))
    def test_payload_hash_is_independent_of_dictionary_insertion_order(
        self,
        payload,
    ):
        reversed_payload = dict(reversed(list(payload.items())))

        self.assertEqual(
            _get_payload_hash(payload),
            _get_payload_hash(reversed_payload),
        )

    @settings(max_examples=150)
    @given(payload=JSON_VALUES)
    def test_payload_hash_is_deterministic_sha256(self, payload):
        first_hash = _get_payload_hash(payload)
        second_hash = _get_payload_hash(payload)

        self.assertEqual(first_hash, second_hash)
        self.assertRegex(first_hash, r"^[0-9a-f]{64}$")


@tag("hypothesis")
class SaleReceiveHttpHypothesisTests(HypothesisTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(
            identifier="VM-HYP-001",
            name="Máquina Hypothesis",
            serial_number="SN-HYP-001",
            rows=2,
            columns=2,
        )

        cls.category = Category.objects.create(
            name="Bebidas Hypothesis",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product = Product.objects.create(
            name="VimaCola Hypothesis",
            category=cls.category,
            format_unit="330 ml",
            default_sale_price=Decimal("1.50"),
            vat_rate=Decimal("21.00"),
        )

        cls.layout = MachineLayout.objects.create(
            machine=cls.machine,
            name="Layout Hypothesis",
        )

        MachinePosition.objects.create(
            layout=cls.layout,
            identifier="A1",
            row=1,
            column=1,
            product=cls.product,
        )

        cls.layout.status = MachineLayout.Status.REGISTERED
        cls.layout.save()

    def setUp(self):
        self.client = Client(
            raise_request_exception=False,
        )

        self.url = reverse(
            "sales:sale_receive",
        )

    def make_payload(self):
        return {
            "event_id": "evt-hyp-001",
            "machine_identifier": "VM-HYP-001",
            "selection": "A1",
            "occurred_at": ("2026-09-21T10:00:00+02:00"),
            "quantity": 1,
            "dispense_type": "paid",
            "unit_price": "1.50",
            "amount_received": "1.50",
            "payment_method": "cash",
        }

    @settings(max_examples=50)
    @given(
        quantity=st.integers(
            min_value=(2**31) - 2,
            max_value=(2**31) + 2,
        )
    )
    def test_quantity_around_postgresql_int4_boundary_never_causes_500(
        self,
        quantity,
    ):

        payload = self.make_payload()
        payload["machine_identifier"] = "VM-NO-EXISTE"

        payload["event_id"] = f"evt-int4-{quantity}"

        payload["quantity"] = quantity

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "Una cantidad cercana al límite int4 "
                "ha provocado un error interno.\n"
                f"quantity={quantity}\n"
                f"status={response.status_code}"
            ),
        )

    @unittest.expectedFailure
    def test_hyp_003_null_character_in_machine_identifier_causes_500(self):
        """
        HYP-003

        El carácter '\\x00' recibido en machine_identifier
        llega hasta PostgreSQL y provoca DataError, generando
        una respuesta HTTP 500.

        """

        payload = self.make_payload()

        payload["machine_identifier"] = "\x00"

        response = self.client.post(
            self.url,
            data=payload,
            content_type="application/json",
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "El carácter nulo en machine_identifier "
                "ha provocado un error interno.\n"
                f"status={response.status_code}"
            ),
        )

    @settings(max_examples=100)
    @given(
        payload=st.one_of(
            st.none(),
            st.booleans(),
            st.integers(),
            SAFE_TEXT,
            st.lists(JSON_VALUES, max_size=5),
        )
    )
    def test_non_object_json_payload_is_rejected_without_500(self, payload):
        response = self.client.post(
            self.url,
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.json())

    @settings(max_examples=50)
    @given(
        missing_field=st.sampled_from(
            [
                "event_id",
                "machine_identifier",
                "selection",
                "occurred_at",
                "quantity",
                "dispense_type",
            ]
        )
    )
    def test_missing_required_payload_field_returns_field_error(self, missing_field):
        payload = self.make_payload()
        payload.pop(missing_field)

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(missing_field, response.json()["errors"])

    @settings(max_examples=150)
    @given(
        quantity=st.one_of(
            st.none(),
            st.booleans(),
            st.integers(min_value=-(10**30), max_value=10**30),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(
                alphabet=st.characters(min_codepoint=0, max_codepoint=127),
                max_size=100,
            ),
        )
    )
    def test_arbitrary_quantity_never_causes_http_500(self, quantity):
        payload = self.make_payload()
        payload["quantity"] = quantity

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertLess(
            response.status_code,
            500,
            f"quantity={quantity!r} provocó status={response.status_code}",
        )

    @settings(max_examples=100)
    @given(dispense_type=SAFE_TEXT)
    def test_arbitrary_dispense_type_never_causes_http_500(self, dispense_type):
        payload = self.make_payload()
        payload["dispense_type"] = dispense_type

        response = self.client.post(
            self.url,
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertLess(
            response.status_code,
            500,
            (f"dispense_type={dispense_type!r} provocó status={response.status_code}"),
        )

    def test_deeply_nested_json_never_causes_http_500(self):

        depth = sys.getrecursionlimit() + 100

        body = "[" * depth + "0" + "]" * depth

        response = self.client.post(
            self.url,
            data=body,
            content_type="application/json",
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "Un JSON excesivamente anidado ha provocado "
                "un error interno.\n"
                f"depth={depth}\n"
                f"status={response.status_code}"
            ),
        )

    @settings(max_examples=100)
    @given(
        field_info=st.sampled_from(
            [
                ("event_id", 100, "e"),
                ("machine_identifier", 100, "m"),
                ("selection", 20, "s"),
                ("payment_method", 50, "p"),
            ]
        ),
        extra=st.integers(
            min_value=1,
            max_value=50,
        ),
    )
    def test_sale_text_fields_above_max_length_never_cause_500(
        self,
        field_info,
        extra,
    ):

        field, max_length, character = field_info

        payload = self.make_payload()

        payload["machine_identifier"] = "VM-NO-EXISTE"

        payload["event_id"] = f"evt-length-{field}-{extra}"

        value = character * (max_length + extra)

        payload[field] = value

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "Un campo por encima de su max_length "
                "ha provocado un error interno.\n"
                f"field={field}\n"
                f"max_length={max_length}\n"
                f"actual_length={len(value)}\n"
                f"status={response.status_code}"
            ),
        )


@tag("hypothesis")
class CategoryHypothesisTests(HypothesisTestCase):
    @settings(max_examples=200)
    @given(
        name=st.text(
            min_size=0,
            max_size=150,
        )
    )
    def test_category_name_arbitrary_text_never_causes_500(
        self,
        name,
    ):

        client = Client(
            raise_request_exception=False,
        )

        response = client.post(
            reverse("inventory:category_create"),
            {
                "name": name,
                "default_vat_rate": "21.00",
            },
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "El nombre de categoría ha provocado "
                "un error interno.\n"
                f"name={name!r}\n"
                f"length={len(name)}\n"
                f"status={response.status_code}"
            ),
        )

    @settings(max_examples=200)
    @given(
        vat_rate=st.one_of(
            st.decimals(
                allow_nan=True,
                allow_infinity=True,
                places=None,
            ),
            st.sampled_from(
                [
                    "0",
                    "0.00",
                    "-0.01",
                    "100",
                    "100.00",
                    "100.01",
                    "999999999999999999999999",
                    "0.000000000000000000001",
                    "99.999999999999999999",
                    "NaN",
                    "Infinity",
                    "-Infinity",
                    "1e999999",
                    "1e-999999",
                ]
            ),
        )
    )
    def test_category_vat_rate_arbitrary_value_never_causes_500(
        self,
        vat_rate,
    ):

        client = Client(
            raise_request_exception=False,
        )

        response = client.post(
            reverse("inventory:category_create"),
            {
                "name": "Categoria Hypothesis",
                "default_vat_rate": str(vat_rate),
            },
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "El valor del IVA ha provocado un error interno.\n"
                f"default_vat_rate={vat_rate!r}\n"
                f"status={response.status_code}"
            ),
        )


@tag("hypothesis")
class ProductHypothesisTests(HypothesisTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Categoria Hypothesis",
            default_vat_rate=Decimal("21.00"),
        )

    @settings(max_examples=200)
    @given(
        price=st.one_of(
            st.decimals(
                allow_nan=True,
                allow_infinity=True,
                places=None,
            ),
            st.sampled_from(
                [
                    "0",
                    "0.00",
                    "-0.01",
                    "99999999.99",
                    "100000000.00",
                    "999999999999999999999999",
                    "0.001",
                    "1.999999999999",
                    "NaN",
                    "Infinity",
                    "-Infinity",
                    "1e999999",
                    "1e-999999",
                ]
            ),
        )
    )
    def test_product_sale_price_arbitrary_value_never_causes_500(
        self,
        price,
    ):

        client = Client(
            raise_request_exception=False,
        )

        response = client.post(
            reverse("inventory:product_create"),
            {
                "name": "Producto Hypothesis",
                "category": self.category.pk,
                "format_unit": "1 ud.",
                "vat_rate": "21.00",
                "default_sale_price": str(price),
            },
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "El precio de venta ha provocado "
                "un error interno.\n"
                f"default_sale_price={price!r}\n"
                f"status={response.status_code}"
            ),
        )

    @settings(max_examples=200)
    @given(
        format_unit=st.text(
            min_size=0,
            max_size=150,
        )
    )
    def test_product_format_unit_arbitrary_text_never_causes_500(
        self,
        format_unit,
    ):

        client = Client(
            raise_request_exception=False,
        )

        response = client.post(
            reverse("inventory:product_create"),
            {
                "name": "Producto Hypothesis",
                "category": self.category.pk,
                "format_unit": format_unit,
                "vat_rate": "21.00",
                "default_sale_price": "1.50",
            },
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "El formato/unidad del producto ha provocado "
                "un error interno.\n"
                f"format_unit={format_unit!r}\n"
                f"length={len(format_unit)}\n"
                f"status={response.status_code}"
            ),
        )

    @settings(max_examples=200)
    @given(
        vat_rate=st.one_of(
            st.decimals(
                allow_nan=True,
                allow_infinity=True,
                places=None,
            ),
            st.sampled_from(
                [
                    "0",
                    "0.00",
                    "-0.01",
                    "100",
                    "100.00",
                    "100.01",
                    "999999999999999999999",
                    "0.000000000000001",
                    "99.999999999999",
                    "NaN",
                    "Infinity",
                    "-Infinity",
                    "1e999999",
                    "1e-999999",
                ]
            ),
        )
    )
    def test_product_vat_rate_arbitrary_value_never_causes_500(
        self,
        vat_rate,
    ):

        client = Client(
            raise_request_exception=False,
        )

        response = client.post(
            reverse("inventory:product_create"),
            {
                "name": "Producto Hypothesis",
                "category": self.category.pk,
                "format_unit": "1 ud.",
                "default_sale_price": "1.50",
                "vat_rate": str(vat_rate),
            },
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "El IVA del producto ha provocado "
                "un error interno.\n"
                f"vat_rate={vat_rate!r}\n"
                f"status={response.status_code}"
            ),
        )

    @settings(max_examples=100)
    @given(
        use_valid_category=st.booleans(),
        arbitrary_category=st.one_of(
            st.integers(
                min_value=-10_000,
                max_value=10_000,
            ),
            st.text(max_size=30),
        ),
    )
    def test_product_blank_vat_never_causes_500(
        self,
        use_valid_category,
        arbitrary_category,
    ):
        if use_valid_category:
            category_id = self.category.pk
        else:
            category_id = arbitrary_category

        client = Client(
            raise_request_exception=False,
        )

        response = client.post(
            reverse("inventory:product_create"),
            {
                "name": "Producto Hypothesis",
                "category": category_id,
                "format_unit": "1 ud.",
                "vat_rate": "",
                "default_sale_price": "1.50",
            },
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "IVA vacío combinado con una categoría "
                "ha provocado un error interno.\n"
                f"category={category_id!r}\n"
                f"status={response.status_code}"
            ),
        )

    @settings(max_examples=200)
    @given(
        name=st.text(
            min_size=0,
            max_size=150,
        )
    )
    def test_product_name_arbitrary_text_never_causes_500(
        self,
        name,
    ):

        client = Client(
            raise_request_exception=False,
        )

        response = client.post(
            reverse("inventory:product_create"),
            {
                "name": name,
                "category": self.category.pk,
                "format_unit": "1 ud.",
                "default_sale_price": "1.50",
                "vat_rate": "21.00",
            },
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "El nombre del producto ha provocado "
                "un error interno.\n"
                f"name={name!r}\n"
                f"length={len(name)}\n"
                f"status={response.status_code}"
            ),
        )


@tag("hypothesis")
class MachineHypothesisTests(HypothesisTestCase):
    @settings(max_examples=200)
    @given(
        rows=st.one_of(
            st.text(
                min_size=0,
                max_size=100,
            ),
            st.sampled_from(
                [
                    "-1",
                    "0",
                    "1",
                    "20",
                    "21",
                    "999999999999999999999999",
                    "1.5",
                    "-1.5",
                    "NaN",
                    "Infinity",
                    "-Infinity",
                    "1e10",
                    " ",
                    "+1",
                    "01",
                ]
            ),
        )
    )
    def test_machine_rows_arbitrary_value_never_causes_500(
        self,
        rows,
    ):

        client = Client(
            raise_request_exception=False,
        )

        response = client.post(
            reverse("machines:machine_create"),
            {
                "identifier": "VM-HYP-001",
                "name": "Máquina Hypothesis",
                "serial_number": "SN-HYP-001",
                "location": "Ubicación de prueba",
                "rows": rows,
                "columns": "5",
            },
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "El número de filas ha provocado "
                "un error interno.\n"
                f"rows={rows!r}\n"
                f"status={response.status_code}"
            ),
        )


@tag("hypothesis")
class PricingProfileHypothesisTests(HypothesisTestCase):
    @settings(max_examples=200)
    @given(
        adjustment=st.one_of(
            st.decimals(
                allow_nan=True,
                allow_infinity=True,
                places=None,
            ),
            st.sampled_from(
                [
                    "0",
                    "0.00",
                    "0.01",
                    "-0.01",
                    "9999.99",
                    "-9999.99",
                    "10000.00",
                    "-10000.00",
                    "999999999999999999",
                    "0.000000000001",
                    "1.999999999999",
                    "NaN",
                    "Infinity",
                    "-Infinity",
                    "1e999999",
                    "1e-999999",
                ]
            ),
        )
    )
    def test_pricing_profile_adjustment_arbitrary_value_never_causes_500(
        self,
        adjustment,
    ):

        client = Client(
            raise_request_exception=False,
        )

        response = client.post(
            reverse("machines:pricing_profile_create"),
            {
                "name": "Tarifa Hypothesis",
                "percentage_adjustment": str(adjustment),
            },
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "La variación de la política de precios "
                "ha provocado un error interno.\n"
                f"percentage_adjustment={adjustment!r}\n"
                f"status={response.status_code}"
            ),
        )


@tag("hypothesis")
class MachinePriceOverrideHypothesisTests(HypothesisTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Categoria Override Hypothesis",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product = Product.objects.create(
            name="Producto Override Hypothesis",
            format_unit="1 ud.",
            default_sale_price=Decimal("2.00"),
            vat_rate=Decimal("21.00"),
            category=cls.category,
        )

        cls.pricing_profile = PricingProfile.objects.create(
            name="Tarifa Hypothesis",
            percentage_adjustment=Decimal("10.00"),
        )

        cls.machine = Machine.objects.create(
            identifier="VM-OVERRIDE-HYP",
            name="Máquina Override Hypothesis",
            serial_number="SN-OVERRIDE-HYP",
            rows=5,
            columns=5,
            pricing_profile=cls.pricing_profile,
        )

    @settings(max_examples=200)
    @given(
        adjustment=st.decimals(
            allow_nan=True,
            allow_infinity=True,
            places=None,
        )
    )
    def test_machine_price_override_arbitrary_adjustment_never_causes_500(
        self,
        adjustment,
    ):

        client = Client(
            raise_request_exception=False,
        )

        response = client.post(
            reverse(
                "machines:machine_price_override_create",
                kwargs={"pk": self.machine.pk},
            ),
            {
                "product": self.product.pk,
                "percentage_adjustment": str(adjustment),
            },
        )

        self.assertLess(
            response.status_code,
            500,
            (
                "La excepción de precio ha provocado "
                "un error interno.\n"
                f"percentage_adjustment={adjustment!r}\n"
                f"status={response.status_code}"
            ),
        )


@tag("hypothesis")
class MachinePositionHypothesisTests(HypothesisTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(
            identifier="VM-POS-HYP",
            name="Máquina Posiciones Hypothesis",
            serial_number="SN-POS-HYP",
            rows=5,
            columns=5,
        )

        cls.layout = MachineLayout.objects.create(
            machine=cls.machine,
            name="Layout Posiciones Hypothesis",
        )

    @settings(max_examples=300)
    @given(
        row=st.integers(min_value=-20, max_value=20),
        column=st.integers(min_value=-20, max_value=20),
        width=st.integers(min_value=-20, max_value=20),
        height=st.integers(min_value=-20, max_value=20),
    )
    def test_position_must_fit_inside_machine_grid(
        self,
        row,
        column,
        width,
        height,
    ):
        position = MachinePosition(
            layout=self.layout,
            identifier="HYP",
            row=row,
            column=column,
            width=width,
            height=height,
        )

        should_be_valid = (
            row >= 1
            and column >= 1
            and width >= 1
            and height >= 1
            and row + height - 1 <= self.machine.rows
            and column + width - 1 <= self.machine.columns
        )

        try:
            position.full_clean()

        except ValidationError:
            if should_be_valid:
                self.fail(
                    "Una posición que cabe dentro de la cuadrícula "
                    "ha sido rechazada.\n"
                    f"row={row}, column={column}, "
                    f"width={width}, height={height}"
                )
            return

        except Exception as exc:
            self.fail(
                "La validación de una posición ha provocado "
                "una excepción interna inesperada.\n"
                f"row={row}, column={column}, "
                f"width={width}, height={height}\n"
                f"tipo={type(exc).__name__}\n"
                f"error={exc}"
            )

        if not should_be_valid:
            self.fail(
                "Se ha aceptado una posición fuera de los límites "
                "de la cuadrícula.\n"
                f"row={row}, column={column}, "
                f"width={width}, height={height}"
            )


@st.composite
def valid_machine_rectangle(
    draw,
    max_rows=5,
    max_columns=5,
):

    row = draw(
        st.integers(
            min_value=1,
            max_value=max_rows,
        )
    )

    column = draw(
        st.integers(
            min_value=1,
            max_value=max_columns,
        )
    )

    height = draw(
        st.integers(
            min_value=1,
            max_value=max_rows - row + 1,
        )
    )

    width = draw(
        st.integers(
            min_value=1,
            max_value=max_columns - column + 1,
        )
    )

    return row, column, width, height


@tag("hypothesis")
class MachinePositionOverlapHypothesisTests(HypothesisTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(
            identifier="VM-OVERLAP-HYP",
            name="Máquina Overlap Hypothesis",
            serial_number="SN-OVERLAP-HYP",
            rows=5,
            columns=5,
        )

        cls.layout = MachineLayout.objects.create(
            machine=cls.machine,
            name="Layout Overlap Hypothesis",
        )

    @settings(max_examples=500)
    @given(
        first=valid_machine_rectangle(),
        second=valid_machine_rectangle(),
    )
    def test_position_overlap_detection_matches_geometry(
        self,
        first,
        second,
    ):

        MachinePosition.objects.filter(
            layout=self.layout,
        ).delete()

        row1, column1, width1, height1 = first
        row2, column2, width2, height2 = second

        MachinePosition.objects.create(
            layout=self.layout,
            identifier="A1",
            row=row1,
            column=column1,
            width=width1,
            height=height1,
        )

        candidate = MachinePosition(
            layout=self.layout,
            identifier="A2",
            row=row2,
            column=column2,
            width=width2,
            height=height2,
        )

        first_last_row = row1 + height1 - 1
        first_last_column = column1 + width1 - 1

        second_last_row = row2 + height2 - 1
        second_last_column = column2 + width2 - 1

        rows_overlap = row2 <= first_last_row and second_last_row >= row1

        columns_overlap = column2 <= first_last_column and second_last_column >= column1

        expected_overlap = rows_overlap and columns_overlap

        try:
            candidate.full_clean()

        except ValidationError:
            if not expected_overlap:
                self.fail(
                    "La aplicación detectó un solapamiento "
                    "que geométricamente no existe.\n"
                    f"first={first!r}\n"
                    f"second={second!r}"
                )

            return

        if expected_overlap:
            self.fail(
                "La aplicación permitió dos posiciones "
                "que geométricamente se solapan.\n"
                f"first={first!r}\n"
                f"second={second!r}"
            )


@tag("hypothesis")
class MachineLayoutActivationHypothesisTests(HypothesisTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(
            identifier="VM-ACT-HYP",
            name="Máquina Activaciones Hypothesis",
            serial_number="SN-ACT-HYP",
            rows=5,
            columns=5,
        )

        cls.layout_a = MachineLayout.objects.create(
            machine=cls.machine,
            name="Layout A Hypothesis",
        )

        cls.layout_a.status = MachineLayout.Status.REGISTERED
        cls.layout_a.save()

        cls.layout_b = MachineLayout.objects.create(
            machine=cls.machine,
            name="Layout B Hypothesis",
        )

        cls.layout_b.status = MachineLayout.Status.REGISTERED
        cls.layout_b.save()

    @settings(max_examples=300)
    @given(
        sequence=st.lists(
            st.sampled_from(["A", "B"]),
            min_size=1,
            max_size=15,
        )
    )
    def test_activation_sequence_never_corrupts_history(
        self,
        sequence,
    ):
        MachineLayoutActivation.objects.filter(
            layout__machine=self.machine,
        ).delete()

        base_time = datetime(
            2026,
            1,
            1,
            10,
            0,
            tzinfo=datetime_timezone.utc,
        )

        current_layout = None
        successful_activations = 0

        for index, choice in enumerate(sequence):
            layout = self.layout_a if choice == "A" else self.layout_b

            moment = base_time + timedelta(
                minutes=index + 1,
            )

            if current_layout == layout:
                with patch(
                    "django.utils.timezone.now",
                    return_value=moment,
                ):
                    with self.assertRaises(ValidationError):
                        activate_machine_layout(layout)

            else:
                with patch(
                    "django.utils.timezone.now",
                    return_value=moment,
                ):
                    activate_machine_layout(layout)

                current_layout = layout
                successful_activations += 1

            open_activations = MachineLayoutActivation.objects.filter(
                layout__machine=self.machine,
                effective_to__isnull=True,
            )

            self.assertEqual(
                open_activations.count(),
                1,
                (
                    "El histórico contiene un número incorrecto "
                    "de disposiciones activas.\n"
                    f"sequence={sequence!r}\n"
                    f"step={index}\n"
                    f"open={open_activations.count()}"
                ),
            )

            current_activation = get_current_machine_layout_activation(self.machine)

            self.assertEqual(
                current_activation.layout_id,
                current_layout.pk,
            )

        activations = list(
            MachineLayoutActivation.objects.filter(
                layout__machine=self.machine,
            ).order_by(
                "effective_from",
                "pk",
            )
        )

        self.assertEqual(
            len(activations),
            successful_activations,
            (
                "Se han creado activaciones adicionales "
                "durante intentos inválidos.\n"
                f"sequence={sequence!r}"
            ),
        )

        for previous, following in zip(
            activations,
            activations[1:],
        ):
            self.assertIsNotNone(
                previous.effective_to,
                (f"Una activación antigua continúa abierta.\nsequence={sequence!r}"),
            )

            self.assertEqual(
                previous.effective_to,
                following.effective_from,
                (
                    "Existe un hueco o solapamiento inesperado "
                    "entre activaciones consecutivas.\n"
                    f"sequence={sequence!r}\n"
                    f"previous={previous.pk}\n"
                    f"following={following.pk}"
                ),
            )

            self.assertLess(
                previous.effective_from,
                previous.effective_to,
            )

        self.assertIsNone(
            activations[-1].effective_to,
        )

    @unittest.expectedFailure
    def test_hyp_004_model_allows_multiple_open_layout_activations(self):
        """
        HYP-004

        Comprueba que una misma máquina no pueda tener más de una
        disposición activa al mismo tiempo.

        El servicio de activación controla correctamente esta regla,
        pero al crear las activaciones directamente mediante el ORM
        el modelo permite que existan varias activaciones abiertas.
        """

        MachineLayoutActivation.objects.create(
            layout=self.layout_a,
        )

        MachineLayoutActivation.objects.create(
            layout=self.layout_b,
        )

        open_activations = MachineLayoutActivation.objects.filter(
            layout__machine=self.machine,
            effective_to__isnull=True,
        )

        self.assertLessEqual(
            open_activations.count(),
            1,
            (
                "La misma máquina tiene varias disposiciones "
                "activas simultáneamente.\n"
                f"open_activations={open_activations.count()}"
            ),
        )


@tag("hypothesis")
class MachineLayoutIntegrityHypothesisTests(HypothesisTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.machine = Machine.objects.create(
            identifier="VM-LAYOUT-INT-HYP",
            name="Máquina Layout Integrity",
            serial_number="SN-LAYOUT-INT-HYP",
            rows=5,
            columns=5,
        )

        cls.layout = MachineLayout.objects.create(
            machine=cls.machine,
            name="Layout Original",
        )

        cls.position = MachinePosition.objects.create(
            layout=cls.layout,
            identifier="A1",
            row=1,
            column=1,
            width=1,
            height=1,
        )

        cls.layout.status = MachineLayout.Status.REGISTERED
        cls.layout.save()

    @unittest.expectedFailure
    def test_hyp_005_registered_layout_can_be_modified_with_queryset_update(
        self,
    ):
        """
        HYP-005

        Las disposiciones registradas son inmutables mediante
        los flujos normales del modelo, pero QuerySet.update()
        permite modificar directamente sus datos porque no
        ejecuta MachineLayout.save().
        """

        MachineLayout.objects.filter(
            pk=self.layout.pk,
        ).update(
            name="Nombre modificado",
        )

        self.layout.refresh_from_db()

        self.assertEqual(
            self.layout.name,
            "Layout Original",
            (
                "Una disposición registrada ha podido "
                "modificarse mediante QuerySet.update()."
            ),
        )

    @unittest.expectedFailure
    def test_hyp_005_registered_layout_position_can_be_modified_with_queryset_update(
        self,
    ):
        """
        HYP-005

        Las posiciones pertenecientes a una disposición registrada
        pueden modificarse directamente mediante QuerySet.update(),
        evitando las protecciones del modelo.
        """

        MachinePosition.objects.filter(
            pk=self.position.pk,
        ).update(
            column=2,
        )

        self.position.refresh_from_db()

        self.assertEqual(
            (self.position.row, self.position.column),
            (1, 1),
            (
                "Una posición de una disposición registrada "
                "ha podido modificarse mediante QuerySet.update()."
            ),
        )

    @unittest.expectedFailure
    def test_hyp_005_registered_layout_position_can_be_deleted_with_queryset_delete(
        self,
    ):
        """
        HYP-005

        Las posiciones de una disposición registrada pueden
        eliminarse mediante QuerySet.delete(), evitando las
        protecciones de inmutabilidad del modelo.
        """

        position_pk = self.position.pk

        MachinePosition.objects.filter(
            pk=position_pk,
        ).delete()

        self.assertTrue(
            MachinePosition.objects.filter(
                pk=position_pk,
            ).exists(),
            (
                "Una posición de una disposición registrada "
                "ha podido eliminarse mediante QuerySet.delete()."
            ),
        )

    @unittest.expectedFailure
    def test_hyp_005_registered_layout_can_be_deleted_with_queryset_delete(
        self,
    ):
        """
        HYP-005

        Una disposición registrada puede eliminarse mediante
        QuerySet.delete(), evitando MachineLayout.delete().
        """

        layout_pk = self.layout.pk

        MachineLayout.objects.filter(
            pk=layout_pk,
        ).delete()

        self.assertTrue(
            MachineLayout.objects.filter(
                pk=layout_pk,
            ).exists(),
            (
                "Una disposición registrada ha podido "
                "eliminarse mediante QuerySet.delete()."
            ),
        )


@tag("hypothesis")
class PricingIntegrityHypothesisTests(HypothesisTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Categoria Pricing Integrity",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product = Product.objects.create(
            name="Producto Pricing Integrity",
            category=cls.category,
            format_unit="1 ud.",
            default_sale_price=Decimal("1.00"),
            vat_rate=Decimal("21.00"),
        )

        cls.machine = Machine.objects.create(
            identifier="VM-PRICE-INT-HYP",
            name="Máquina Pricing Integrity",
            serial_number="SN-PRICE-INT-HYP",
            rows=1,
            columns=1,
        )

    @settings(max_examples=200)
    @given(
        adjustment=st.decimals(
            max_value=Decimal("-100.01"),
            min_value=Decimal("-9999.99"),
            places=2,
        )
    )
    def test_pricing_adjustments_below_minus_100_are_rejected(self, adjustment):
        profile = PricingProfile(
            name="Tarifa Hypothesis",
            percentage_adjustment=adjustment,
        )

        with self.assertRaises(ValidationError):
            profile.full_clean()

    @unittest.expectedFailure
    def test_hyp_007_override_equal_to_profile_can_be_created_directly(
        self,
    ):
        """
        HYP-007

        MachinePriceOverride.clean() prohíbe que el ajuste específico
        sea igual al de la tarifa general, pero objects.create()
        no ejecuta full_clean() y permite guardar ese estado.
        """

        profile = PricingProfile.objects.create(
            name="Tarifa HYP-007",
            percentage_adjustment=Decimal("10.00"),
        )

        self.machine.pricing_profile = profile
        self.machine.save()

        with self.assertRaises(ValidationError):
            MachinePriceOverride.objects.create(
                machine=self.machine,
                product=self.product,
                percentage_adjustment=Decimal("10.00"),
            )


@tag("hypothesis")
class SaleStockIntegrityHypothesisTests(HypothesisTestCase):
    INITIAL_STOCK = 20

    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Categoria Stock Hypothesis",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product = Product.objects.create(
            name="Producto Stock Hypothesis",
            category=cls.category,
            format_unit="1 ud.",
            default_sale_price=Decimal("1.00"),
            vat_rate=Decimal("21.00"),
        )

        cls.machine = Machine.objects.create(
            identifier="VM-STOCK-HYP",
            name="Máquina Stock Hypothesis",
            serial_number="SN-STOCK-HYP",
            rows=5,
            columns=5,
        )

        purchase = Purchase.objects.create(
            supplier="Proveedor Hypothesis",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=cls.product,
            quantity=cls.INITIAL_STOCK,
            unit_price_excl_vat=Decimal("1.00"),
        )

        replenishment = Replenishment.objects.create(
            machine=cls.machine,
            status=Replenishment.Status.REGISTERED,
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=cls.product,
            quantity=cls.INITIAL_STOCK,
        )

    @settings(max_examples=300)
    @given(
        quantities=st.lists(
            st.integers(
                min_value=1,
                max_value=30,
            ),
            min_size=1,
            max_size=20,
        )
    )
    def test_arbitrary_sale_sequence_never_makes_stock_negative(
        self,
        quantities,
    ):

        expected_stock = self.INITIAL_STOCK
        accepted_quantity = 0

        occurred_at = datetime(
            2026,
            9,
            21,
            12,
            0,
            tzinfo=datetime_timezone.utc,
        )

        for quantity in quantities:
            stock_before = get_machine_stock(
                self.product,
                self.machine,
            )

            self.assertEqual(
                stock_before,
                expected_stock,
                (
                    "El stock calculado ya no coincide con "
                    "el estado esperado antes de la venta.\n"
                    f"sequence={quantities!r}\n"
                    f"quantity={quantity}\n"
                    f"expected_stock={expected_stock}\n"
                    f"actual_stock={stock_before}"
                ),
            )

            if quantity <= expected_stock:
                sale = create_manual_sale(
                    machine=self.machine,
                    product=self.product,
                    occurred_at=occurred_at,
                    quantity=quantity,
                    dispense_type=Sale.DispenseType.FREE,
                )

                self.assertEqual(
                    sale.status,
                    Sale.Status.RESOLVED,
                )

                expected_stock -= quantity
                accepted_quantity += quantity

            else:
                with self.assertRaises(ValidationError):
                    create_manual_sale(
                        machine=self.machine,
                        product=self.product,
                        occurred_at=occurred_at,
                        quantity=quantity,
                        dispense_type=Sale.DispenseType.FREE,
                    )

            stock_after = get_machine_stock(
                self.product,
                self.machine,
            )

            self.assertEqual(
                stock_after,
                expected_stock,
                (
                    "Una venta ha dejado un stock incorrecto.\n"
                    f"sequence={quantities!r}\n"
                    f"quantity={quantity}\n"
                    f"expected_stock={expected_stock}\n"
                    f"actual_stock={stock_after}"
                ),
            )

            self.assertGreaterEqual(
                stock_after,
                0,
                (
                    "La secuencia de ventas ha producido "
                    "stock negativo.\n"
                    f"sequence={quantities!r}\n"
                    f"stock={stock_after}"
                ),
            )

        self.assertEqual(
            accepted_quantity + expected_stock,
            self.INITIAL_STOCK,
        )

    @settings(max_examples=300)
    @given(
        operations=st.lists(
            st.tuples(
                st.integers(
                    min_value=1,
                    max_value=30,
                ),
                st.booleans(),
            ),
            min_size=1,
            max_size=20,
        )
    )
    def test_sale_and_void_sequences_preserve_stock(
        self,
        operations,
    ):

        expected_stock = self.INITIAL_STOCK

        occurred_at = datetime(
            2026,
            9,
            21,
            12,
            0,
            tzinfo=datetime_timezone.utc,
        )

        for quantity, should_void in operations:
            if quantity <= expected_stock:
                sale = create_manual_sale(
                    machine=self.machine,
                    product=self.product,
                    occurred_at=occurred_at,
                    quantity=quantity,
                    dispense_type=Sale.DispenseType.FREE,
                )

                expected_stock -= quantity

                self.assertEqual(
                    get_machine_stock(
                        self.product,
                        self.machine,
                    ),
                    expected_stock,
                )

                if should_void:
                    sale = void_sale(
                        sale,
                        "Anulación Hypothesis",
                    )

                    expected_stock += quantity

                    self.assertEqual(
                        sale.status,
                        Sale.Status.VOIDED,
                    )

            else:
                with self.assertRaises(ValidationError):
                    create_manual_sale(
                        machine=self.machine,
                        product=self.product,
                        occurred_at=occurred_at,
                        quantity=quantity,
                        dispense_type=Sale.DispenseType.FREE,
                    )

            actual_stock = get_machine_stock(
                self.product,
                self.machine,
            )

            self.assertEqual(
                actual_stock,
                expected_stock,
                (
                    "La secuencia de ventas/anulaciones ha "
                    "desincronizado el inventario.\n"
                    f"operations={operations!r}\n"
                    f"quantity={quantity}\n"
                    f"should_void={should_void}\n"
                    f"expected_stock={expected_stock}\n"
                    f"actual_stock={actual_stock}"
                ),
            )

            self.assertGreaterEqual(
                actual_stock,
                0,
            )

            self.assertLessEqual(
                actual_stock,
                self.INITIAL_STOCK,
                (
                    "Una anulación ha creado más stock "
                    "del que existía inicialmente.\n"
                    f"operations={operations!r}\n"
                    f"stock={actual_stock}"
                ),
            )

    @settings(max_examples=200)
    @given(
        quantity=st.integers(
            min_value=1,
            max_value=20,
        )
    )
    def test_voiding_same_sale_twice_never_creates_extra_stock(
        self,
        quantity,
    ):

        occurred_at = datetime(
            2026,
            9,
            21,
            12,
            0,
            tzinfo=datetime_timezone.utc,
        )

        sale = create_manual_sale(
            machine=self.machine,
            product=self.product,
            occurred_at=occurred_at,
            quantity=quantity,
            dispense_type=Sale.DispenseType.FREE,
        )

        stock_after_sale = get_machine_stock(
            self.product,
            self.machine,
        )

        self.assertEqual(
            stock_after_sale,
            self.INITIAL_STOCK - quantity,
        )

        void_sale(
            sale,
            "Primera anulación Hypothesis",
        )

        stock_after_first_void = get_machine_stock(
            self.product,
            self.machine,
        )

        self.assertEqual(
            stock_after_first_void,
            self.INITIAL_STOCK,
        )

        try:
            void_sale(
                sale,
                "Segunda anulación Hypothesis",
            )

        except ValidationError:
            pass

        stock_after_second_void = get_machine_stock(
            self.product,
            self.machine,
        )

        self.assertEqual(
            stock_after_second_void,
            self.INITIAL_STOCK,
            (
                "Anular dos veces la misma venta ha alterado "
                "incorrectamente el inventario.\n"
                f"quantity={quantity}\n"
                f"stock_after_first_void={stock_after_first_void}\n"
                f"stock_after_second_void={stock_after_second_void}"
            ),
        )

        self.assertLessEqual(
            stock_after_second_void,
            self.INITIAL_STOCK,
            (
                "La doble anulación ha generado stock inexistente.\n"
                f"quantity={quantity}\n"
                f"stock={stock_after_second_void}"
            ),
        )

    @settings(
        max_examples=250,
        deadline=None,
    )
    @given(
        operations=st.lists(
            st.tuples(
                st.integers(
                    min_value=1,
                    max_value=10,
                ),
                st.booleans(),
            ),
            min_size=1,
            max_size=15,
        )
    )
    def test_voided_sales_never_contribute_to_sales_projection(
        self,
        operations,
    ):

        expected_historical_sales = 0
        available_stock = self.INITIAL_STOCK

        occurred_at = datetime(
            2026,
            9,
            21,
            12,
            0,
            tzinfo=datetime_timezone.utc,
        )

        for quantity, should_void in operations:
            if quantity > available_stock:
                continue

            sale = create_manual_sale(
                machine=self.machine,
                product=self.product,
                occurred_at=occurred_at,
                quantity=quantity,
                dispense_type=Sale.DispenseType.FREE,
            )

            available_stock -= quantity
            expected_historical_sales += quantity

            if should_void:
                void_sale(
                    sale,
                    "Anulación Hypothesis para proyección",
                )

                available_stock += quantity
                expected_historical_sales -= quantity

            projections = get_sales_projection(
                date(2026, 9, 21),
                date(2026, 9, 21),
                date(2026, 9, 22),
                date(2026, 9, 22),
            )

            product_projection = next(
                item for item in projections if item["product"].pk == self.product.pk
            )

            self.assertEqual(
                product_projection["historical_sales"],
                expected_historical_sales,
                (
                    "La proyección incluye o excluye ventas "
                    "incorrectamente después de una anulación.\n"
                    f"operations={operations!r}\n"
                    f"quantity={quantity}\n"
                    f"should_void={should_void}\n"
                    f"expected={expected_historical_sales}\n"
                    f"actual={product_projection['historical_sales']}"
                ),
            )

            resolved_quantity = (
                Sale.objects.filter(
                    machine=self.machine,
                    product=self.product,
                    status=Sale.Status.RESOLVED,
                ).aggregate(
                    total=Sum("quantity"),
                )["total"]
                or 0
            )

            self.assertEqual(
                product_projection["historical_sales"],
                resolved_quantity,
            )


@tag("hypothesis")
class InventoryFlowHypothesisTests(HypothesisTestCase):
    INITIAL_STOCK = 40

    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Categoria Inventory Flow",
            default_vat_rate=Decimal("21.00"),
        )

        cls.product = Product.objects.create(
            name="Producto Inventory Flow",
            category=cls.category,
            format_unit="1 ud.",
            default_sale_price=Decimal("1.00"),
            vat_rate=Decimal("21.00"),
        )

        cls.machine = Machine.objects.create(
            identifier="VM-INV-FLOW-HYP",
            name="Máquina Inventory Flow",
            serial_number="SN-INV-FLOW-HYP",
            rows=5,
            columns=5,
        )
        cls.layout = MachineLayout.objects.create(
            machine=cls.machine,
            name="Layout Inventory Flow",
        )

        MachinePosition.objects.create(
            layout=cls.layout,
            identifier="A1",
            row=1,
            column=1,
            product=cls.product,
        )

        cls.layout.status = MachineLayout.Status.REGISTERED
        cls.layout.save()

        MachineLayoutActivation.objects.create(
            layout=cls.layout,
        )

        purchase = Purchase.objects.create(
            supplier="Proveedor Hypothesis",
            status=Purchase.Status.REGISTERED,
        )

        PurchaseLine.objects.create(
            purchase=purchase,
            product=cls.product,
            quantity=cls.INITIAL_STOCK,
            unit_price_excl_vat=Decimal("1.00"),
        )

    @settings(max_examples=250)
    @given(
        operations=st.lists(
            st.tuples(
                st.booleans(),
                st.integers(
                    min_value=1,
                    max_value=30,
                ),
            ),
            min_size=1,
            max_size=20,
        )
    )
    def test_replenishment_and_sale_sequences_preserve_inventory(
        self,
        operations,
    ):
        expected_warehouse = self.INITIAL_STOCK
        expected_machine = 0

        occurred_at = datetime(
            2026,
            9,
            21,
            12,
            0,
            tzinfo=datetime_timezone.utc,
        )

        for is_replenishment, quantity in operations:
            if is_replenishment:
                if quantity <= expected_warehouse:
                    replenishment = Replenishment.objects.create(
                        machine=self.machine,
                        replenished_at=occurred_at,
                        status=Replenishment.Status.REGISTERED,
                    )

                    ReplenishmentLine.objects.create(
                        replenishment=replenishment,
                        product=self.product,
                        quantity=quantity,
                    )

                    expected_warehouse -= quantity
                    expected_machine += quantity

            else:
                if quantity <= expected_machine:
                    create_manual_sale(
                        machine=self.machine,
                        product=self.product,
                        occurred_at=occurred_at,
                        quantity=quantity,
                        dispense_type=Sale.DispenseType.FREE,
                    )

                    expected_machine -= quantity

                else:
                    with self.assertRaises(ValidationError):
                        create_manual_sale(
                            machine=self.machine,
                            product=self.product,
                            occurred_at=occurred_at,
                            quantity=quantity,
                            dispense_type=Sale.DispenseType.FREE,
                        )

            warehouse_stock = get_warehouse_stock(
                self.product,
            )

            machine_stock = get_machine_stock(
                self.product,
                self.machine,
            )

            total_stock = get_total_stock(
                self.product,
            )

            self.assertEqual(
                warehouse_stock,
                expected_warehouse,
            )

            self.assertEqual(
                machine_stock,
                expected_machine,
            )

            self.assertEqual(
                warehouse_stock + machine_stock,
                total_stock,
                (
                    "El inventario global se ha desincronizado.\n"
                    f"operations={operations!r}\n"
                    f"warehouse={warehouse_stock}\n"
                    f"machine={machine_stock}\n"
                    f"total={total_stock}"
                ),
            )

            self.assertGreaterEqual(
                warehouse_stock,
                0,
            )

            self.assertGreaterEqual(
                machine_stock,
                0,
            )

    @settings(max_examples=250)
    @given(
        quantity=st.integers(
            min_value=INITIAL_STOCK + 1,
            max_value=1000,
        )
    )
    def test_replenishment_cannot_exceed_warehouse_stock(
        self,
        quantity,
    ):

        replenishment = Replenishment.objects.create(
            machine=self.machine,
            replenished_at=datetime.now(
                datetime_timezone.utc,
            ),
        )

        ReplenishmentLine.objects.create(
            replenishment=replenishment,
            product=self.product,
            quantity=quantity,
        )

        warehouse_before = get_warehouse_stock(
            self.product,
        )

        machine_before = get_machine_stock(
            self.product,
            self.machine,
        )

        client = Client(
            raise_request_exception=False,
        )

        response = client.post(
            reverse(
                "replenishments:replenishment_register",
                kwargs={"pk": replenishment.pk},
            ),
        )

        replenishment.refresh_from_db()

        self.assertEqual(
            replenishment.status,
            Replenishment.Status.DRAFT,
            (
                "Una reposición superior al stock disponible "
                "ha podido registrarse.\n"
                f"warehouse_stock={warehouse_before}\n"
                f"requested={quantity}"
            ),
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertIn(
            "stock_error=1",
            response["Location"],
        )

        warehouse_after = get_warehouse_stock(
            self.product,
        )

        machine_after = get_machine_stock(
            self.product,
            self.machine,
        )

        self.assertEqual(
            warehouse_after,
            warehouse_before,
        )

        self.assertEqual(
            machine_after,
            machine_before,
        )

        self.assertGreaterEqual(
            warehouse_after,
            0,
        )
