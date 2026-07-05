from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from .models import Bebida, Marca, Venta, VentaItem, EmployeeInsumo, Gasto


class VentaItemStockTests(TestCase):
    def setUp(self):
        self.marca = Marca.objects.create(nombre='Test', tipo='bebida')
        self.bebida = Bebida.objects.create(
            nombre='Coca Cola',
            marca=self.marca,
            stock=10,
            volumen_ml=500,
            categoria='bebida',
        )
        self.venta = Venta.objects.create(moneda='COP', fecha=timezone.now(), observacion='Venta de prueba')

    def test_sale_item_decreases_stock_for_bebida(self):
        item = VentaItem.objects.create(
            venta=self.venta,
            producto=self.bebida,
            cantidad=3,
            precio_unitario=Decimal('5000'),
            moneda='COP',
        )
        item.apply_stock_change()
        self.bebida.refresh_from_db()
        self.assertEqual(self.bebida.stock, 7)


class InsumoYGastoTests(TestCase):
    def test_employee_supply_and_expense_can_be_marked_paid(self):
        insumo = EmployeeInsumo.objects.create(
            empleado='Carlos',
            descripcion='Refresco para turno matutino',
            cantidad=2,
            costo=Decimal('8000'),
            fecha=timezone.now().date(),
        )
        gasto = Gasto.objects.create(
            proveedor='Distribuidora Leche',
            descripcion='Leche para producción',
            monto=Decimal('120000'),
            fecha=timezone.now().date(),
        )

        insumo.marcar_pagado()
        gasto.marcar_pagado()

        insumo.refresh_from_db()
        gasto.refresh_from_db()
        self.assertTrue(insumo.pagado)
        self.assertTrue(gasto.pagado)
