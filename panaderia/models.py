from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password, check_password


class Marca(models.Model):
    TIPO_CHOICES = [
        ('panaderia', 'Panadería'),
        ('bebida', 'Bebidas'),
        ('chucheria', 'Chucherías'),
        ('recurso', 'Recursos'),
    ]
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='panaderia')

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"


class Producto(models.Model):
    nombre = models.CharField(max_length=150)
    stock = models.PositiveIntegerField(default=0, verbose_name="Stock disponible")
    marca = models.ForeignKey(Marca, null=True, blank=True, on_delete=models.SET_NULL, related_name='productos')
    CATEGORIA_CHOICES = [
        ('pan_salado', 'Pan Salado'),
        ('pan_dulce', 'Pan Dulce'),
        ('pasteleria', 'Pastelería'),
        ('bebida', 'Bebida'),
        ('chucheria', 'Chuchería'),
        ('recurso', 'Recurso'),
    ]
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='pan_salado')
    sabor = models.BooleanField(verbose_name="sabor",default=False)

    def __str__(self):
        return self.nombre

    @property
    def stock_level(self):
        if self.stock == 0:
            return 'Agotado'
        if self.stock < 5:
            return 'Bajo'
        if self.stock < 20:
            return 'Medio'
        return 'Alto'

    @property
    def stock_badge_class(self):
        if self.stock == 0:
            return 'badge-out'
        if self.stock < 5:
            return 'badge-low'
        if self.stock < 20:
            return 'badge-medium'
        return 'badge-high'


class Bebida(Producto):
    volumen_ml = models.PositiveIntegerField(null=True, blank=True)




class Chucheria(Producto):
    descripcion = models.CharField(max_length=200, blank=True)


class Venta(models.Model):
    MONEDA_CHOICES = [
        ('COP', 'Pesos colombianos'),
        ('VES', 'Bolívares venezolanos'),
        ('USD', 'Dólares'),
    ]

    fecha = models.DateField(default=timezone.now)
    moneda = models.CharField(max_length=10, choices=MONEDA_CHOICES, default='COP')
    ESTADO_CHOICES = [
        ('abierta', 'Abierta'),
        ('cerrada', 'Cerrada'),
    ]
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='abierta')
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    observacion = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Venta {self.id} - {self.get_moneda_display()}"


class VentaItem(models.Model):
    venta = models.ForeignKey(Venta, related_name='items', on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, related_name='ventas', on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    moneda = models.CharField(max_length=10, choices=Venta.MONEDA_CHOICES, default='COP')

    def __str__(self):
        return f"{self.producto.nombre} x {self.cantidad}"

    def apply_stock_change(self):
        if self.producto.stock >= self.cantidad:
            self.producto.stock -= self.cantidad
            self.producto.save(update_fields=['stock'])
            return True
        return False


class Panaderia_items(models.Model):
    UNIDAD_CHOICES = [
        ('kg', 'Kilogramos'),
        ('g', 'Gramos'),
        ('l', 'Litros'),
        ('ml', 'Mililitros'),
        ('ud', 'Unidades'),
    ]

    tipo_item = models.CharField(
        max_length=100,
        verbose_name="Insumo de materia prima",
        help_text='Describa el insumo de materia prima que se guardará en el inventario.',
    )
    marca = models.ForeignKey(
        Marca,
        on_delete=models.CASCADE,
        verbose_name="Marca",
        help_text='Marca del insumo de materia prima.',
    )
    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Cantidad disponible",
        help_text='Cantidad disponible del insumo en la unidad seleccionada.',
    )
    unidad = models.CharField(
        max_length=10,
        choices=UNIDAD_CHOICES,
        default='kg',
        verbose_name='Unidad de medida',
        help_text='Unidad en la que se registra la cantidad del insumo.',
    )

    class Meta:
        verbose_name = "Insumo de materia prima"
        verbose_name_plural = "Insumos de materia prima"

    def __str__(self):
        return f"{self.tipo_item} - {self.cantidad} {self.get_unidad_display()}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.tipo_item or not self.tipo_item.strip():
            raise ValidationError({'tipo_item': 'Debes ingresar el nombre del insumo de materia prima.'})

        if self.cantidad is None or self.cantidad <= 0:
            raise ValidationError({'cantidad': 'La cantidad debe ser mayor que cero.'})

        if self.marca and self.marca.tipo != 'recurso':
            raise ValidationError({'marca': 'La marca debe corresponder a materia prima (tipo recurso).'})

        if not self.unidad:
            raise ValidationError({'unidad': 'Debes seleccionar la unidad de medida.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def stock_level(self):
        if self.cantidad == 0:
            return 'Agotado'
        if self.cantidad < 5:
            return 'Bajo'
        if self.cantidad < 20:
            return 'Medio'
        return 'Alto'

    @property
    def stock_badge_class(self):
        if self.cantidad == 0:
            return 'badge-out'
        if self.cantidad < 5:
            return 'badge-low'
        if self.cantidad < 20:
            return 'badge-medium'
        return 'badge-high'


class EmployeeInsumo(models.Model):
    empleado = models.CharField(max_length=150, verbose_name='Empleado')
    descripcion = models.TextField(blank=True, verbose_name='Descripción')
    cantidad = models.PositiveIntegerField(default=1, verbose_name='Cantidad')
    costo = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Costo')
    fecha = models.DateField(default=timezone.now, verbose_name='Fecha')
    pagado = models.BooleanField(default=False, verbose_name='Pagado')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Insumo de empleado'
        verbose_name_plural = 'Insumos de empleados'

    def __str__(self):
        return f"{self.empleado} - {self.descripcion or 'Sin detalle'}"

    def marcar_pagado(self):
        self.pagado = True
        self.save(update_fields=['pagado'])


class Gasto(models.Model):
    proveedor = models.CharField(max_length=150, verbose_name='Proveedor')
    descripcion = models.TextField(blank=True, verbose_name='Descripción')
    monto = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Monto')
    fecha = models.DateField(default=timezone.now, verbose_name='Fecha')
    pagado = models.BooleanField(default=False, verbose_name='Pagado')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Gasto'
        verbose_name_plural = 'Gastos'

    def __str__(self):
        return f"{self.proveedor} - {self.descripcion or 'Sin detalle'}"

    def marcar_pagado(self):
        self.pagado = True
        self.save(update_fields=['pagado'])


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    security_word_hash = models.CharField(max_length=128, blank=True, null=True)

    def set_security_word(self, raw_word):
        self.security_word_hash = make_password(raw_word)
        self.save()

    def check_security_word(self, raw_word):
        if not self.security_word_hash:
            return False
        return check_password(raw_word, self.security_word_hash)

    def __str__(self):
        return f"Perfil de {self.user.username}"


    config = models.JSONField(default=dict, blank=True, null=True, help_text='Configuración personalizada del usuario')
class Backup(models.Model):
    """Registro de respaldos de la base de datos o archivos subidos por el usuario."""
    file = models.FileField(upload_to='backups/')
    target_date = models.DateField(null=True, blank=True, help_text='Fecha a la que corresponde el snapshot de inventario, si aplica')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='backups')

    def __str__(self):
        return f"Backup {self.id} - {self.file.name} ({self.created_at.date()})"
