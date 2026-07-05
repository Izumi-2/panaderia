from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from . import models


class ProfileInline(admin.StackedInline):
    model = models.Profile
    can_delete = False
    verbose_name_plural = 'Perfil'
    fields = ('security_word_hash', 'config')


class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)


# Unregister original User admin and register new one with Profile inline
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(models.Marca)
class MarcaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'tipo')
    list_filter = ('tipo',)


@admin.register(models.Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'stock', 'marca', 'categoria', "sabor")
    list_filter = ('marca', 'categoria')


@admin.register(models.Bebida)
class BebidaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'marca', 'volumen_ml')


@admin.register(models.Chucheria)
class ChucheriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'marca')


@admin.register(models.Panaderia_items)
class Pitemsadmin(admin.ModelAdmin):
    list_display = ("id", "tipo_item", "cantidad", "unidad", "stock")


@admin.register(models.EmployeeInsumo)
class EmployeeInsumoAdmin(admin.ModelAdmin):
    list_display = ('id', 'empleado', 'cantidad', 'costo', 'fecha', 'pagado')
    list_filter = ('pagado', 'fecha')


@admin.register(models.Gasto)
class GastoAdmin(admin.ModelAdmin):
    list_display = ('id', 'proveedor', 'monto', 'fecha', 'pagado')
    list_filter = ('pagado', 'fecha')


@admin.register(models.Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'user')
    search_fields = ('user__username', 'user__email')