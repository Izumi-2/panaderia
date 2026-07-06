from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Bebida, Chucheria, Marca, Producto, Venta, VentaItem, EmployeeInsumo, Gasto, Panaderia_items


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
        self.producto = Producto.objects.create(
            nombre='Pan de prueba',
            marca=self.marca,
            existencia_manana=2,
            entrada_manana=3,
            entrada_tarde=1,
            stock=6,
            categoria='pan_salado',
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

    def test_sale_item_decreases_stock_for_producto(self):
        item = VentaItem.objects.create(
            venta=self.venta,
            producto=self.producto,
            cantidad=2,
            precio_unitario=Decimal('2500'),
            moneda='COP',
        )
        item.apply_stock_change()
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 4)


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


class SurplusTransferTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='adminsurplus',
            password='secret123',
            is_staff=True,
            is_superuser=True,
        )
        self.marca = Marca.objects.create(nombre='Marca prueba', tipo='bebida')
        self.producto = Producto.objects.create(
            nombre='Pan normal',
            marca=self.marca,
            stock=5,
            categoria='pan_salado',
        )
        self.nevera = Bebida.objects.create(
            nombre='Refresco',
            marca=self.marca,
            stock=4,
            volumen_ml=500,
            categoria='bebida',
        )
        self.chucheria = Chucheria.objects.create(
            nombre='Caramelos',
            marca=self.marca,
            stock=3,
            categoria='chucheria',
        )

    def test_apply_surplus_updates_product_stock(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('panaderia:apply_surplus_product', args=[self.producto.pk]),
            {'sobrante': 11},
            follow=True,
        )

        self.assertRedirects(response, reverse('panaderia:product_list'))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 11)

    def test_close_day_products_updates_multiple_product_stocks(self):
        second = Producto.objects.create(
            nombre='Pan dulce',
            marca=self.marca,
            stock=2,
            categoria='pan_dulce',
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('panaderia:close_day_products'),
            {
                f'sobrante_{self.producto.pk}': '12',
                f'sobrante_{second.pk}': '8',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('panaderia:product_list'))
        self.producto.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.producto.stock, 12)
        self.assertEqual(second.stock, 8)

    def test_product_create_saves_computed_stock_from_quick_entry(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('panaderia:product_create'),
            {
                'nombre': 'Pan nuevo',
                'marca': self.marca.pk,
                'categoria': 'pan_salado',
                'stock': '0',
                'existencia_manana': '3',
                'entrada_manana': '2',
                'entrada_tarde': '1',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('panaderia:product_list'))
        created = Producto.objects.get(nombre='Pan nuevo')
        self.assertEqual(created.stock, 6)
        self.assertEqual(created.existencia_manana, 3)
        self.assertEqual(created.entrada_manana, 2)
        self.assertEqual(created.entrada_tarde, 1)

    def test_product_update_saves_entry_values_and_shows_them_in_list(self):
        self.client.force_login(self.user)
        producto = Producto.objects.create(
            nombre='Pan editado',
            marca=self.marca,
            existencia_manana=4,
            entrada_manana=0,
            entrada_tarde=0,
            stock=4,
            categoria='pan_salado',
        )
        response = self.client.post(
            reverse('panaderia:product_update', args=[producto.pk]),
            {
                'nombre': 'Pan editado',
                'marca': self.marca.pk,
                'categoria': 'pan_salado',
                'stock': '4',
                'existencia_manana': '4',
                'entrada_manana': '2',
                'entrada_tarde': '1',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('panaderia:product_list'))
        producto.refresh_from_db()
        self.assertEqual(producto.stock, 7)
        self.assertEqual(producto.existencia_manana, 4)
        self.assertEqual(producto.entrada_manana, 2)
        self.assertEqual(producto.entrada_tarde, 1)

        list_response = self.client.get(reverse('panaderia:product_list'))
        self.assertContains(list_response, 'Pan editado')
        self.assertContains(list_response, 'value="4"')
        self.assertContains(list_response, 'value="2"')
        self.assertContains(list_response, 'value="1"')

    def test_apply_surplus_updates_nevera_stock(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('panaderia:apply_surplus_nevera', args=[self.nevera.pk]),
            {'sobrante': 12},
            follow=True,
        )

        self.assertRedirects(response, reverse('panaderia:nevera_list'))
        self.nevera.refresh_from_db()
        self.assertEqual(self.nevera.stock, 12)

    def test_apply_surplus_updates_chucheria_stock(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('panaderia:apply_surplus_chucheria', args=[self.chucheria.pk]),
            {'sobrante': 9},
            follow=True,
        )

        self.assertRedirects(response, reverse('panaderia:chucheria_list'))
        self.chucheria.refresh_from_db()
        self.assertEqual(self.chucheria.stock, 9)


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
