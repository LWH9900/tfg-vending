import os
import uuid
from datetime import datetime, timezone

from locust import HttpUser, between, task

MACHINE_IDENTIFIER = os.getenv("LOCUST_MACHINE_IDENTIFIER", "VM-003")
SELECTION = os.getenv("LOCUST_SELECTION", "A1")


class ProductListUser(HttpUser):
    """
    Escenario de carga sobre el listado de productos.
    """

    wait_time = between(1, 3)

    @task
    def view_products(self):
        with self.client.get(
            "/inventory/products/",
            name="/inventory/products/",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Respuesta inesperada: {response.status_code}")


class SaleReceiveUser(HttpUser):
    """
    Escenario de carga sobre la recepción de ventas.

    Requiere una máquina, selección y stock válidos en la base de datos.
    """

    wait_time = between(1, 3)

    @task
    def receive_sale(self):
        event_id = f"locust-{uuid.uuid4()}"

        payload = {
            "event_id": event_id,
            "machine_identifier": MACHINE_IDENTIFIER,
            "selection": SELECTION,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "quantity": 1,
            "dispense_type": "paid",
            "unit_price": "1.50",
            "amount_received": "1.50",
            "payment_method": "cash",
        }

        with self.client.post(
            "/sales/receive/",
            json=payload,
            name="/sales/receive/",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(
                    f"Respuesta inesperada: {response.status_code} "
                    f"{response.text[:200]}"
                )
