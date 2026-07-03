from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from .models import Bebida, Marca, Venta, VentaItem


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
            producto_model='bebida',
            producto_id=self.bebida.pk,
            cantidad=3,
            precio_unitario=Decimal('5000'),
            moneda='COP',
        )
        item.apply_stock_change()
        self.bebida.refresh_from_db()
        self.assertEqual(self.bebida.stock, 7)
