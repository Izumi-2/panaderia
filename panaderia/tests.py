from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Bebida, Marca, Venta, VentaItem, EmployeeInsumo, Gasto, Panaderia_items


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


class ReportesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='adminreportes',
            password='secret123',
            is_staff=True,
            is_superuser=True,
        )
        self.marca_recurso = Marca.objects.create(nombre='Marca recurso', tipo='recurso')
        self.recurso = Panaderia_items.objects.create(
            tipo_item='Harina',
            marca=self.marca_recurso,
            cantidad=20,
            stock=10,
            unidad='kg',
        )
        self.insumo = EmployeeInsumo.objects.create(
            empleado='Carlos',
            descripcion='Refresco',
            cantidad=2,
            costo=Decimal('7000'),
            fecha=timezone.now().date(),
        )
        self.gasto = Gasto.objects.create(
            proveedor='Proveedor X',
            descripcion='Luz',
            monto=Decimal('50000'),
            fecha=timezone.now().date(),
        )

    def test_report_page_context_includes_new_sections(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('panaderia:reportes'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('recursos', response.context)
        self.assertIn('employee_insumos', response.context)
        self.assertIn('gastos', response.context)
        self.assertTrue(response.context['employee_insumos'].filter(pk=self.insumo.pk).exists())
        self.assertTrue(response.context['gastos'].filter(pk=self.gasto.pk).exists())
        self.assertTrue(response.context['recursos'].filter(pk=self.recurso.pk).exists())
