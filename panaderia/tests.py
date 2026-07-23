import os
import sqlite3
import tempfile
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from datetime import timedelta
from django.utils import timezone
from .models import Backup, Bebida, Chucheria, Marca, Producto, Venta, VentaItem, EmployeeInsumo, Gasto, Panaderia_items


class VentaItemStockTests(TestCase):
    def setUp(self):
        self.marca = Marca.objects.create(nombre='Test', tipo='bebida')
        self.bebida = Bebida.objects.create(
            nombre='Coca Cola',
            marca=self.marca,
            stock=10,
            existencia_manana=10,
            volumen_ml=500,
            categoria='bebida',
        )
        self.producto = Producto.objects.create(
            nombre='Pan de prueba',
            marca=self.marca,
            existencia_manana=6,
            entrada_manana=3,
            entrada_tarde=1,
            stock=10,
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
        self.assertEqual(self.bebida.existencia_manana, 7)

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
        self.assertEqual(self.producto.stock, 8)
        self.assertEqual(self.producto.existencia_manana, 4)


class VentaManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='adminventa',
            password='secret123',
            is_staff=True,
            is_superuser=True,
        )
        self.marca = Marca.objects.create(nombre='Marca venta', tipo='panaderia')
        self.producto = Producto.objects.create(
            nombre='Pan de venta',
            marca=self.marca,
            stock=5,
            existencia_manana=5,
            categoria='pan_salado',
        )
        self.venta = Venta.objects.create(
            moneda='VES',
            estado='abierta',
            fecha=timezone.localdate(),
            total=Decimal('1200.00'),
            observacion='Venta inicial',
        )
        self.item = VentaItem.objects.create(
            venta=self.venta,
            producto=self.producto,
            cantidad=2,
            precio_unitario=Decimal('600.00'),
            moneda='VES',
        )

    def test_sale_form_rejects_future_dates_and_negative_totals(self):
        self.client.force_login(self.user)
        future_date = (timezone.localdate() + timezone.timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.post(
            reverse('panaderia:venta_create'),
            {
                'fecha': future_date,
                'moneda': 'VES',
                'metodo_pago': 'efectivo',
                'producto': self.producto.pk,
                'cantidad': '-1',
                'precio_unitario': '-100',
            },
            follow=True,
        )

        self.assertContains(response, 'La fecha no puede ser futura.')
        self.assertContains(response, 'La cantidad debe ser al menos 1.')
        self.assertContains(response, 'El precio unitario no puede ser negativo.')

    def test_sale_can_be_updated_and_deleted(self):
        self.client.force_login(self.user)

        update_response = self.client.post(
            reverse('panaderia:venta_update', args=[self.venta.pk]),
            {
                'fecha': self.venta.fecha.strftime('%Y-%m-%d'),
                'moneda': 'VES',
                'metodo_pago': 'pago_movil',
                'producto': self.producto.pk,
                'cantidad': '3',
                'precio_unitario': '650.00',
            },
            follow=True,
        )
        self.assertRedirects(update_response, reverse('panaderia:venta_list'))
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.total, Decimal('1950.00'))

        delete_response = self.client.post(
            reverse('panaderia:venta_delete', args=[self.venta.pk]),
            follow=True,
        )
        self.assertRedirects(delete_response, reverse('panaderia:venta_list'))
        self.assertFalse(Venta.objects.filter(pk=self.venta.pk).exists())

    def test_ves_sales_accept_tarjeta_point_of_sale_method(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('panaderia:venta_create'),
            {
                'fecha': self.venta.fecha.strftime('%Y-%m-%d'),
                'moneda': 'VES',
                'metodo_pago': 'tarjeta',
                'producto': self.producto.pk,
                'cantidad': '1',
                'precio_unitario': '100.00',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('panaderia:venta_list'))
        self.assertTrue(Venta.objects.filter(metodo_pago='tarjeta').exists())


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

    def test_inventory_values_can_be_updated_directly_from_list(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('panaderia:update_inventory'),
            {
                'model_type': 'producto',
                'pk': self.producto.pk,
                'existencia_manana': '10',
                'entrada_manana': '4',
                'entrada_tarde': '2',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.existencia_manana, 10)
        self.assertEqual(self.producto.entrada_manana, 4)
        self.assertEqual(self.producto.entrada_tarde, 2)
        self.assertEqual(self.producto.stock, 16)


class BackupsSalesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='adminbackups',
            password='secret123',
            is_staff=True,
            is_superuser=True,
        )
        self.marca = Marca.objects.create(nombre='Marca backup', tipo='panaderia')
        self.producto = Producto.objects.create(
            nombre='Pan backup',
            marca=self.marca,
            existencia_manana=5,
            entrada_manana=2,
            entrada_tarde=1,
            stock=8,
            categoria='pan_salado',
        )
        self.venta = Venta.objects.create(moneda='COP', fecha=timezone.now(), observacion='Venta de backup')
        VentaItem.objects.create(
            venta=self.venta,
            producto=self.producto,
            cantidad=2,
            precio_unitario=Decimal('3000'),
            moneda='COP',
        )
        self.backup_today = Backup.objects.create(file='backups/backup-today.sqlite3', created_by=self.user, target_date=timezone.localdate())
        self.backup_other = Backup.objects.create(file='backups/backup-other.sqlite3', created_by=self.user, target_date=timezone.localdate() - timedelta(days=1))
        Backup.objects.filter(pk=self.backup_today.pk).update(created_at=timezone.now())
        Backup.objects.filter(pk=self.backup_other.pk).update(created_at=timezone.now() - timedelta(days=1))

    def test_backups_page_includes_sales_history(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('panaderia:backups'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('ventas', response.context)
        self.assertEqual(response.context['ventas'].count(), 1)
        self.assertEqual(response.context['ventas_totales']['items'], 1)

    def test_backups_page_filters_backup_list_by_selected_date(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('panaderia:backups'), {'date': timezone.localdate().strftime('%Y-%m-%d')})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['backups'].values_list('id', flat=True)), [self.backup_today.id])
        self.assertEqual(response.context['selected_date'], timezone.localdate())


class BackupImportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='adminbackupimport',
            password='secret123',
            is_staff=True,
            is_superuser=True,
        )

    def test_upload_backup_imports_brands_products_and_sales(self):
        with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as temp_file:
            backup_path = temp_file.name

        try:
            conn = sqlite3.connect(backup_path)
            cur = conn.cursor()
            cur.execute('CREATE TABLE panaderia_marca (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT)')
            cur.execute('CREATE TABLE panaderia_producto (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, existencia_manana INTEGER, entrada_manana INTEGER, entrada_tarde INTEGER, stock INTEGER, categoria TEXT, marca_id INTEGER, sabor BOOLEAN)')
            cur.execute('CREATE TABLE panaderia_bebida (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_ptr_id INTEGER, volumen_ml INTEGER)')
            cur.execute('CREATE TABLE panaderia_chucheria (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_ptr_id INTEGER, descripcion TEXT)')
            cur.execute('CREATE TABLE panaderia_venta (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, moneda TEXT, estado TEXT, total TEXT, observacion TEXT, creado_en TEXT)')
            cur.execute('CREATE TABLE panaderia_ventaitem (id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER, producto_id INTEGER, cantidad INTEGER, precio_unitario TEXT, moneda TEXT)')
            cur.execute('INSERT INTO panaderia_marca (id, nombre, tipo) VALUES (1, "Marca importada", "panaderia")')
            cur.execute('INSERT INTO panaderia_producto (id, nombre, existencia_manana, entrada_manana, entrada_tarde, stock, categoria, marca_id, sabor) VALUES (10, "Pan importado", 4, 1, 1, 6, "pan_salado", 1, 0)')
            cur.execute('INSERT INTO panaderia_venta (id, fecha, moneda, estado, total, observacion, creado_en) VALUES (100, "2026-07-07", "COP", "cerrada", "15000.00", "Venta importada", "2026-07-07 10:00:00")')
            cur.execute('INSERT INTO panaderia_ventaitem (id, venta_id, producto_id, cantidad, precio_unitario, moneda) VALUES (200, 100, 10, 2, "7500.00", "COP")')
            conn.commit()
            conn.close()

            with open(backup_path, 'rb') as fh:
                uploaded = SimpleUploadedFile('backup.sqlite3', fh.read(), content_type='application/octet-stream')

            self.client.force_login(self.user)
            response = self.client.post(reverse('panaderia:upload_backup'), {'backup_file': uploaded, 'import': '1'}, follow=True)

            self.assertRedirects(response, reverse('panaderia:backups'))
            self.assertTrue(Marca.objects.filter(nombre='Marca importada', tipo='panaderia').exists())
            producto = Producto.objects.get(nombre='Pan importado')
            self.assertEqual(producto.stock, 6)
            self.assertEqual(producto.existencia_manana, 4)
            self.assertEqual(Venta.objects.filter(observacion='Venta importada').exists(), True)
            self.assertTrue(VentaItem.objects.filter(venta__observacion='Venta importada').exists())
        finally:
            if os.path.exists(backup_path):
                os.remove(backup_path)

    def test_selecting_existing_backup_restores_its_data_into_system(self):
        restore_file = None
        with tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False) as temp_file:
            backup_path = temp_file.name

        try:
            conn = sqlite3.connect(backup_path)
            cur = conn.cursor()
            cur.execute('CREATE TABLE panaderia_marca (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT)')
            cur.execute('CREATE TABLE panaderia_producto (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, existencia_manana INTEGER, entrada_manana INTEGER, entrada_tarde INTEGER, stock INTEGER, categoria TEXT, marca_id INTEGER, sabor BOOLEAN)')
            cur.execute('CREATE TABLE panaderia_bebida (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_ptr_id INTEGER, volumen_ml INTEGER)')
            cur.execute('CREATE TABLE panaderia_chucheria (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_ptr_id INTEGER, descripcion TEXT)')
            cur.execute('CREATE TABLE panaderia_venta (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, moneda TEXT, estado TEXT, total TEXT, observacion TEXT, creado_en TEXT)')
            cur.execute('CREATE TABLE panaderia_ventaitem (id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER, producto_id INTEGER, cantidad INTEGER, precio_unitario TEXT, moneda TEXT)')
            cur.execute('INSERT INTO panaderia_marca (id, nombre, tipo) VALUES (1, "Marca restaurada", "panaderia")')
            cur.execute('INSERT INTO panaderia_producto (id, nombre, existencia_manana, entrada_manana, entrada_tarde, stock, categoria, marca_id, sabor) VALUES (11, "Pan restaurado", 7, 2, 1, 10, "pan_salado", 1, 0)')
            cur.execute('INSERT INTO panaderia_venta (id, fecha, moneda, estado, total, observacion, creado_en) VALUES (101, "2026-07-08", "COP", "cerrada", "18000.00", "Venta restaurada", "2026-07-08 10:00:00")')
            cur.execute('INSERT INTO panaderia_ventaitem (id, venta_id, producto_id, cantidad, precio_unitario, moneda) VALUES (201, 101, 11, 3, "6000.00", "COP")')
            conn.commit()
            conn.close()

            dest_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
            os.makedirs(dest_dir, exist_ok=True)
            restore_file = os.path.join(dest_dir, 'restore.sqlite3')
            with open(backup_path, 'rb') as src, open(restore_file, 'wb') as dst:
                dst.write(src.read())

            backup = Backup.objects.create(file='backups/restore.sqlite3', created_by=self.user)
            self.client.force_login(self.user)
            response = self.client.get(reverse('panaderia:restore_backup', args=[backup.pk]), follow=True)

            self.assertRedirects(response, reverse('panaderia:backups'))
            self.assertTrue(Marca.objects.filter(nombre='Marca restaurada', tipo='panaderia').exists())
            producto = Producto.objects.get(nombre='Pan restaurado')
            self.assertEqual(producto.stock, 10)
            self.assertEqual(Venta.objects.filter(observacion='Venta restaurada').exists(), True)
        finally:
            if os.path.exists(backup_path):
                os.remove(backup_path)
            if os.path.exists(restore_file):
                os.remove(restore_file)


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
