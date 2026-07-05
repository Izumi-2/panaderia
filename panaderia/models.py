from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class Marca(models.Model):
    TIPO_CHOICES = [
        ('panaderia', 'Panadería'),
        ('bebida', 'Bebidas'),
        ('chucheria', 'Chucherías'),
        ('recurso', 'Recursos'),
    ]

    nombre = models.CharField(max_length=100, verbose_name='Nombre')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='panaderia', verbose_name='Tipo')

    class Meta:
        verbose_name = 'Marca'
        verbose_name_plural = 'Marcas'

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"


class Producto(models.Model):
    CATEGORIA_CHOICES = [
        ('pan_salado', 'Pan Salado'),
        ('pan_dulce', 'Pan Dulce'),
        ('pasteleria', 'Pastelería'),
        ('bebida', 'Bebida'),
        ('chucheria', 'Chuchería'),
        ('recurso', 'Recurso'),
    ]

    nombre = models.CharField(max_length=150, verbose_name='Nombre')
    stock = models.PositiveIntegerField(default=0, verbose_name='Stock disponible')
    marca = models.ForeignKey(Marca, null=True, blank=True, on_delete=models.SET_NULL, related_name='productos')
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='pan_salado', verbose_name='Categoría')
    sabor = models.BooleanField(default=False, verbose_name='Sabor')

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

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
    volumen_ml = models.PositiveIntegerField(null=True, blank=True, verbose_name='Volumen (ml)')

    class Meta:
        verbose_name = 'Bebida'
        verbose_name_plural = 'Bebidas'


class Chucheria(Producto):
    descripcion = models.CharField(max_length=200, blank=True, verbose_name='Descripción')

    class Meta:
        verbose_name = 'Chuchería'
        verbose_name_plural = 'Chucherías'


class Venta(models.Model):
    MONEDA_CHOICES = [
        ('COP', 'Pesos colombianos'),
        ('VES', 'Bolívares venezolanos'),
        ('USD', 'Dólares'),
    ]
    ESTADO_CHOICES = [
        ('abierta', 'Abierta'),
        ('cerrada', 'Cerrada'),
    ]

    fecha = models.DateField(default=timezone.now, verbose_name='Fecha')
    moneda = models.CharField(max_length=10, choices=MONEDA_CHOICES, default='COP', verbose_name='Moneda')
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='abierta', verbose_name='Estado')
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Total')
    observacion = models.TextField(blank=True, verbose_name='Observación')
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')

    class Meta:
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'

    def __str__(self):
        return f"Venta {self.id} - {self.get_moneda_display()}"


class VentaItem(models.Model):
    venta = models.ForeignKey(Venta, related_name='items', on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, related_name='ventas', on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1, verbose_name='Cantidad')
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Precio unitario')
    moneda = models.CharField(max_length=10, choices=Venta.MONEDA_CHOICES, default='COP', verbose_name='Moneda')

    class Meta:
        verbose_name = 'Item de venta'
        verbose_name_plural = 'Items de venta'

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

    tipo_item = models.CharField(max_length=100, verbose_name='Insumo de materia prima', help_text='Describa el insumo de materia prima que se guardará en el inventario.')
    marca = models.ForeignKey(Marca, on_delete=models.CASCADE, verbose_name='Marca', help_text='Marca del insumo de materia prima.')
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Cantidad disponible', help_text='Cantidad disponible del insumo en la unidad seleccionada.')
    stock = models.PositiveIntegerField(default=0, verbose_name='Stock disponible', help_text='Stock separado del peso o volumen. Indica cuántas unidades hay disponibles.')
    unidad = models.CharField(max_length=10, choices=UNIDAD_CHOICES, default='kg', verbose_name='Unidad de medida', help_text='Unidad en la que se registra la cantidad del insumo.')

    class Meta:
        verbose_name = 'Insumo de materia prima'
        verbose_name_plural = 'Insumos de materia prima'

    def __str__(self):
        return f"{self.tipo_item} - {self.cantidad} {self.get_unidad_display()} (Stock {self.stock})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.tipo_item or not self.tipo_item.strip():
            raise ValidationError({'tipo_item': 'Debes ingresar el nombre del insumo de materia prima.'})

        if self.cantidad is None or self.cantidad < 0:
            raise ValidationError({'cantidad': 'La cantidad no puede ser negativa.'})

        if self.stock is None or self.stock < 0:
            raise ValidationError({'stock': 'El stock no puede ser negativo.'})

        if self.marca and self.marca.tipo != 'recurso':
            raise ValidationError({'marca': 'La marca debe corresponder a materia prima (tipo recurso).'})

        if not self.unidad:
            raise ValidationError({'unidad': 'Debes seleccionar la unidad de medida.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

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


class EmployeeInsumo(models.Model):
    empleado = models.CharField(max_length=150, verbose_name='Empleado')
    descripcion = models.TextField(blank=True, verbose_name='Descripción')
    cantidad = models.PositiveIntegerField(default=1, verbose_name='Cantidad')
    costo = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Costo')
    fecha = models.DateField(default=timezone.now, verbose_name='Fecha')
    pagado = models.BooleanField(default=False, verbose_name='Pagado')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')

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
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')

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
    config = models.JSONField(default=dict, blank=True, null=True, help_text='Configuración personalizada del usuario')

    class Meta:
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfiles'

    def set_security_word(self, raw_word):
        self.security_word_hash = make_password(raw_word)
        self.save()

    def check_security_word(self, raw_word):
        if not self.security_word_hash:
            return False
        return check_password(raw_word, self.security_word_hash)

    def __str__(self):
        return f"Perfil de {self.user.username}"


class Backup(models.Model):
    """Registro de respaldos de la base de datos o archivos subidos por el usuario."""
    file = models.FileField(upload_to='backups/')
    target_date = models.DateField(null=True, blank=True, help_text='Fecha a la que corresponde el snapshot de inventario, si aplica')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='backups')

    class Meta:
        verbose_name = 'Backup'
        verbose_name_plural = 'Backups'

    def __str__(self):
        return f"Backup {self.id} - {self.file.name} ({self.created_at.date()})"
