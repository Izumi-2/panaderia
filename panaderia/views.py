import io
import os
import re
import sqlite3
from datetime import datetime
from decimal import Decimal
from django.conf import settings
from django.http import HttpResponse, FileResponse, JsonResponse
from django.urls import reverse_lazy, reverse
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth import get_user_model, login, logout, views as auth_views
from django.core.exceptions import PermissionDenied
from functools import wraps
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import get_user_model, login, logout
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from .forms import SecurityWordForm, PasswordResetByWordForm, ProfileConfigForm
from .models import Producto, Marca, Panaderia_items, Bebida, Chucheria, Venta, VentaItem, EmployeeInsumo, Gasto
from .models import Backup
from .forms import ProductoForm, BebidaForm, MarcaForm, RecursoForm, VentaForm, VentaItemForm, EmployeeInsumoForm, GastoForm


def parse_target_date(date_str):
    if not date_str:
        return None

    from django.utils.dateparse import parse_date
    parsed = parse_date(date_str)
    if parsed:
        return parsed

    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    m = re.search(r"(?:el\s+)?(\d{1,2})\s+(?:de|del)\s+([a-zA-ZñÑ]+)\s+(?:de|del)\s+(\d{4})", date_str, re.IGNORECASE)
    if m:
        day, month_name, year = m.groups()
        month_name = month_name.lower()
        months_es = {
            'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
            'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
            'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
        }
        month_num = months_es.get(month_name)
        if month_num:
            try:
                return datetime(int(year), month_num, int(day)).date()
            except ValueError:
                return None
    return None


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, 'Acceso restringido solo a usuarios administrativos.')
            logout(request)
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'login'

    def test_func(self):
        return self.request.user.is_active and (self.request.user.is_staff or self.request.user.is_superuser)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, 'Acceso restringido solo a usuarios administrativos.')
        logout(self.request)
        return redirect('login')


class AdminLoginView(auth_views.LoginView):
    template_name = 'registration/login.html'

    def form_valid(self, form):
        user = form.get_user()
        if not (user.is_active and (user.is_staff or user.is_superuser)):
            form.add_error(None, 'Acceso restringido solo a usuarios administrativos.')
            return self.form_invalid(form)
        return super().form_valid(form)


@admin_required
def update_inventory(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    model_type = (request.POST.get('model_type') or '').strip().lower()
    pk = request.POST.get('pk')
    if not model_type or not pk:
        return JsonResponse({'ok': False, 'error': 'Datos incompletos'}, status=400)

    model_map = {
        'producto': Producto,
        'bebida': Bebida,
        'chucheria': Chucheria,
    }
    model_class = model_map.get(model_type)
    if model_class is None:
        return JsonResponse({'ok': False, 'error': 'Tipo de modelo no soportado'}, status=400)

    instance = get_object_or_404(model_class, pk=pk)
    try:
        existencia = int(request.POST.get('existencia_manana', instance.existencia_manana))
    except (TypeError, ValueError):
        existencia = instance.existencia_manana
    try:
        entrada_manana = int(request.POST.get('entrada_manana', instance.entrada_manana))
    except (TypeError, ValueError):
        entrada_manana = instance.entrada_manana
    try:
        entrada_tarde = int(request.POST.get('entrada_tarde', instance.entrada_tarde))
    except (TypeError, ValueError):
        entrada_tarde = instance.entrada_tarde

    if existencia < 0:
        existencia = 0
    if entrada_manana < 0:
        entrada_manana = 0
    if entrada_tarde < 0:
        entrada_tarde = 0

    instance.existencia_manana = existencia
    instance.entrada_manana = entrada_manana
    instance.entrada_tarde = entrada_tarde
    instance.stock = max(0, existencia + entrada_manana + entrada_tarde)
    instance.save(update_fields=['existencia_manana', 'entrada_manana', 'entrada_tarde', 'stock'])
    return JsonResponse({'ok': True, 'stock': instance.stock, 'existencia_manana': instance.existencia_manana, 'entrada_manana': instance.entrada_manana, 'entrada_tarde': instance.entrada_tarde})


class ProductListView(AdminRequiredMixin, generic.ListView):
    model = Producto
    template_name = 'panaderia/product_list.html'
    context_object_name = 'productos'

    def get_queryset(self):
        queryset = super().get_queryset()
        categoria = self.request.GET.get('categoria')
        if categoria:
            queryset = queryset.filter(categoria=categoria)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categorias'] = Producto.CATEGORIA_CHOICES
        return context


class ProductCreateView(AdminRequiredMixin, generic.CreateView):
    model = Producto
    form_class = ProductoForm
    template_name = 'panaderia/product_form.html'
    success_url = reverse_lazy('panaderia:product_list')

    def form_valid(self, form):
        request = self.request
        try:
            existencia = int(request.POST.get('existencia_manana', 0))
        except (TypeError, ValueError):
            existencia = 0
        try:
            entrada_manana = int(request.POST.get('entrada_manana', 0))
        except (TypeError, ValueError):
            entrada_manana = 0
        try:
            entrada_tarde = int(request.POST.get('entrada_tarde', 0))
        except (TypeError, ValueError):
            entrada_tarde = 0
        form.instance.existencia_manana = existencia
        form.instance.entrada_manana = entrada_manana
        form.instance.entrada_tarde = entrada_tarde
        form.instance.stock = max(0, existencia + entrada_manana + entrada_tarde)
        return super().form_valid(form)


class ProductUpdateView(AdminRequiredMixin, generic.UpdateView):
    model = Producto
    form_class = ProductoForm
    template_name = 'panaderia/product_form.html'
    success_url = reverse_lazy('panaderia:product_list')

    def form_valid(self, form):
        request = self.request
        try:
            existencia = int(request.POST.get('existencia_manana', form.instance.existencia_manana))
        except (TypeError, ValueError):
            existencia = form.instance.existencia_manana
        try:
            entrada_manana = int(request.POST.get('entrada_manana', form.instance.entrada_manana))
        except (TypeError, ValueError):
            entrada_manana = form.instance.entrada_manana
        try:
            entrada_tarde = int(request.POST.get('entrada_tarde', form.instance.entrada_tarde))
        except (TypeError, ValueError):
            entrada_tarde = form.instance.entrada_tarde
        form.instance.existencia_manana = existencia
        form.instance.entrada_manana = entrada_manana
        form.instance.entrada_tarde = entrada_tarde
        form.instance.stock = max(0, existencia + entrada_manana + entrada_tarde)
        return super().form_valid(form)


class SignUpView(generic.CreateView):
    form_class = UserCreationForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('panaderia:recurso_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, 'Usuario creado y autenticado correctamente.')
        return response


class BebidaCreateView(AdminRequiredMixin, generic.CreateView):
    model = Bebida
    form_class = BebidaForm
    template_name = 'panaderia/bebida_form.html'
    success_url = reverse_lazy('panaderia:nevera_list')

    def form_valid(self, form):
        form.instance.categoria = 'bebida'
        form.instance.existencia_manana = int(self.request.POST.get('existencia_manana', 0) or 0)
        form.instance.entrada_manana = int(self.request.POST.get('entrada_manana', 0) or 0)
        form.instance.entrada_tarde = int(self.request.POST.get('entrada_tarde', 0) or 0)
        form.instance.stock = max(0, form.instance.existencia_manana + form.instance.entrada_manana + form.instance.entrada_tarde)
        return super().form_valid(form)


class BebidaUpdateView(AdminRequiredMixin, generic.UpdateView):
    model = Bebida
    form_class = BebidaForm
    template_name = 'panaderia/bebida_form.html'
    success_url = reverse_lazy('panaderia:nevera_list')

    def form_valid(self, form):
        form.instance.existencia_manana = int(self.request.POST.get('existencia_manana', form.instance.existencia_manana) or form.instance.existencia_manana)
        form.instance.entrada_manana = int(self.request.POST.get('entrada_manana', form.instance.entrada_manana) or form.instance.entrada_manana)
        form.instance.entrada_tarde = int(self.request.POST.get('entrada_tarde', form.instance.entrada_tarde) or form.instance.entrada_tarde)
        form.instance.stock = max(0, form.instance.existencia_manana + form.instance.entrada_manana + form.instance.entrada_tarde)
        return super().form_valid(form)


class BebidaDeleteView(AdminRequiredMixin, generic.DeleteView):
    model = Bebida
    template_name = 'panaderia/product_confirm_delete.html'
    success_url = reverse_lazy('panaderia:nevera_list')


class ProductDeleteView(AdminRequiredMixin, generic.DeleteView):
    model = Producto
    template_name = 'panaderia/product_confirm_delete.html'
    success_url = reverse_lazy('panaderia:product_list')


@admin_required
def apply_surplus_product(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        try:
            sobrante = int(request.POST.get('sobrante', 0))
        except (TypeError, ValueError):
            sobrante = 0
        if sobrante < 0:
            sobrante = 0
        producto.existencia_manana = sobrante
        producto.entrada_manana = 0
        producto.entrada_tarde = 0
        producto.stock = sobrante
        producto.save(update_fields=['existencia_manana', 'entrada_manana', 'entrada_tarde', 'stock'])
        messages.success(request, f'Sobrante de la noche aplicado a {producto.nombre}.')
    return redirect('panaderia:product_list')


@admin_required
def close_day_products(request):
    if request.method != 'POST':
        return redirect('panaderia:product_list')

    updated = 0
    for key, value in request.POST.items():
        if not key.startswith('sobrante_'):
            continue
        try:
            producto_pk = int(key.split('_', 1)[1])
            sobrante = int(value)
        except (ValueError, TypeError):
            continue
        if sobrante < 0:
            sobrante = 0
        producto = Producto.objects.filter(pk=producto_pk).first()
        if producto:
            producto.existencia_manana = sobrante
            producto.entrada_manana = 0
            producto.entrada_tarde = 0
            producto.stock = sobrante
            producto.save(update_fields=['stock', 'existencia_manana', 'entrada_manana', 'entrada_tarde'])
            updated += 1

    messages.success(request, f'Cierre de jornada aplicado a {updated} producto(s).')
    return redirect('panaderia:product_list')


class ProductDetailView(AdminRequiredMixin, generic.DetailView):
    model = Producto
    template_name = 'panaderia/product_detail.html'


class BebidaListView(AdminRequiredMixin, generic.ListView):
    model = Bebida
    template_name = 'panaderia/bebida_list.html'
    context_object_name = 'neveras'


@admin_required
def apply_surplus_nevera(request, pk):
    bebida = get_object_or_404(Bebida, pk=pk)
    if request.method == 'POST':
        try:
            sobrante = int(request.POST.get('sobrante', 0))
        except (TypeError, ValueError):
            sobrante = 0
        if sobrante < 0:
            sobrante = 0
        bebida.existencia_manana = sobrante
        bebida.entrada_manana = 0
        bebida.entrada_tarde = 0
        bebida.stock = sobrante
        bebida.save(update_fields=['existencia_manana', 'entrada_manana', 'entrada_tarde', 'stock'])
        messages.success(request, f'Sobrante de la noche aplicado a {bebida.nombre}.')
    return redirect('panaderia:nevera_list')


class ChucheriaListView(AdminRequiredMixin, generic.ListView):
    model = Chucheria
    template_name = 'panaderia/chucheria_list.html'
    context_object_name = 'chucherias'


@admin_required
def apply_surplus_chucheria(request, pk):
    chucheria = get_object_or_404(Chucheria, pk=pk)
    if request.method == 'POST':
        try:
            sobrante = int(request.POST.get('sobrante', 0))
        except (TypeError, ValueError):
            sobrante = 0
        if sobrante < 0:
            sobrante = 0
        chucheria.existencia_manana = sobrante
        chucheria.entrada_manana = 0
        chucheria.entrada_tarde = 0
        chucheria.stock = sobrante
        chucheria.save(update_fields=['existencia_manana', 'entrada_manana', 'entrada_tarde', 'stock'])
        messages.success(request, f'Sobrante de la noche aplicado a {chucheria.nombre}.')
    return redirect('panaderia:chucheria_list')


class ChucheriaUpdateView(AdminRequiredMixin, generic.UpdateView):
    model = Chucheria
    fields = ['nombre', 'marca', 'descripcion']
    template_name = 'panaderia/chucheria_form.html'
    success_url = reverse_lazy('panaderia:chucheria_list')

    def form_valid(self, form):
        form.instance.existencia_manana = int(self.request.POST.get('existencia_manana', form.instance.existencia_manana) or form.instance.existencia_manana)
        form.instance.entrada_manana = int(self.request.POST.get('entrada_manana', form.instance.entrada_manana) or form.instance.entrada_manana)
        form.instance.entrada_tarde = int(self.request.POST.get('entrada_tarde', form.instance.entrada_tarde) or form.instance.entrada_tarde)
        form.instance.stock = max(0, form.instance.existencia_manana + form.instance.entrada_manana + form.instance.entrada_tarde)
        return super().form_valid(form)


class ChucheriaDeleteView(AdminRequiredMixin, generic.DeleteView):
    model = Chucheria
    template_name = 'panaderia/chucheria_confirm_delete.html'
    success_url = reverse_lazy('panaderia:chucheria_list')


class RecursoListView(AdminRequiredMixin, generic.ListView):
    model = Panaderia_items
    template_name = 'panaderia/recursos_list.html'
    context_object_name = 'recursos'


class MarcaListView(AdminRequiredMixin, generic.ListView):
    model = Marca
    template_name = 'panaderia/marca_list.html'
    context_object_name = 'marcas'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['marcas_panaderia'] = Marca.objects.filter(tipo='panaderia')
        context['marcas_nevera'] = Marca.objects.filter(tipo='bebida')
        context['marcas_chucheria'] = Marca.objects.filter(tipo='chucheria')
        context['marcas_recurso'] = Marca.objects.filter(tipo='recurso')
        return context


class MarcaCreateView(AdminRequiredMixin, generic.CreateView):
    model = Marca
    form_class = MarcaForm
    template_name = 'panaderia/marca_form.html'
    success_url = reverse_lazy('panaderia:marca_list')


class ChucheriaCreateView(AdminRequiredMixin, generic.CreateView):
    model = Chucheria
    fields = ['nombre', 'marca', 'descripcion']
    template_name = 'panaderia/chucheria_form.html'
    success_url = reverse_lazy('panaderia:chucheria_list')

    def form_valid(self, form):
        form.instance.categoria = 'chucheria'
        form.instance.existencia_manana = int(self.request.POST.get('existencia_manana', 0) or 0)
        form.instance.entrada_manana = int(self.request.POST.get('entrada_manana', 0) or 0)
        form.instance.entrada_tarde = int(self.request.POST.get('entrada_tarde', 0) or 0)
        form.instance.stock = max(0, form.instance.existencia_manana + form.instance.entrada_manana + form.instance.entrada_tarde)
        return super().form_valid(form)


class RecursoCreateView(AdminRequiredMixin, generic.CreateView):
    model = Panaderia_items
    form_class = RecursoForm
    template_name = 'panaderia/recurso_form.html'
    success_url = reverse_lazy('panaderia:recurso_list')


class RecursoUpdateView(AdminRequiredMixin, generic.UpdateView):
    model = Panaderia_items
    form_class = RecursoForm
    template_name = 'panaderia/recurso_form.html'
    success_url = reverse_lazy('panaderia:recurso_list')


class RecursoDeleteView(AdminRequiredMixin, generic.DeleteView):
    model = Panaderia_items
    template_name = 'panaderia/recurso_confirm_delete.html'
    success_url = reverse_lazy('panaderia:recurso_list')


@admin_required
def insumos_gastos_dashboard(request):
    if request.method == 'POST':
        if 'mark_employee_paid' in request.POST:
            insumo = get_object_or_404(EmployeeInsumo, pk=request.POST.get('record_id'))
            insumo.marcar_pagado()
            messages.success(request, 'Insumo marcado como pagado.')
        elif 'mark_expense_paid' in request.POST:
            gasto = get_object_or_404(Gasto, pk=request.POST.get('record_id'))
            gasto.marcar_pagado()
            messages.success(request, 'Gasto marcado como pagado.')
        elif request.POST.get('form_type') == 'employee':
            form = EmployeeInsumoForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Insumo de empleado registrado correctamente.')
            else:
                messages.error(request, 'Revisa los datos del insumo de empleado.')
        elif request.POST.get('form_type') == 'expense':
            form = GastoForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Gasto registrado correctamente.')
            else:
                messages.error(request, 'Revisa los datos del gasto.')
        return redirect('panaderia:insumos_gastos')

    employee_insumos = EmployeeInsumo.objects.order_by('-fecha', '-created_at')
    gastos = Gasto.objects.order_by('-fecha', '-created_at')
    context = {
        'employee_insumos': employee_insumos,
        'gastos': gastos,
        'employee_form': EmployeeInsumoForm(),
        'expense_form': GastoForm(),
        'pending_employee_count': employee_insumos.filter(pagado=False).count(),
        'pending_expense_count': gastos.filter(pagado=False).count(),
    }
    return render(request, 'panaderia/insumos_gastos.html', context)


class VentaListView(AdminRequiredMixin, generic.ListView):
    model = Venta
    template_name = 'panaderia/venta_list.html'
    context_object_name = 'ventas'

    def get_queryset(self):
        queryset = Venta.objects.prefetch_related('items__producto').filter(estado='abierta').order_by('-fecha', '-creado_en')
        fecha_inicio = self.request.GET.get('fecha_inicio')
        fecha_fin = self.request.GET.get('fecha_fin')
        moneda = self.request.GET.get('moneda')

        # Si no se pasan filtros de fecha, mostrar sólo la jornada actual
        if not fecha_inicio and not fecha_fin:
            hoy = timezone.localdate()
            queryset = queryset.filter(fecha=hoy)

        if fecha_inicio:
            queryset = queryset.filter(fecha__gte=fecha_inicio)
        if fecha_fin:
            queryset = queryset.filter(fecha__lte=fecha_fin)
        if moneda:
            queryset = queryset.filter(moneda=moneda)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ventas = context['ventas']
        totals = {'COP': 0.0, 'VES': 0.0, 'USD': 0.0}
        for venta in ventas:
            totals[venta.moneda] += float(venta.total)
        context['ventas_count'] = ventas.count()
        context['total_sales'] = sum(venta.total for venta in ventas)
        context['total_items'] = sum(venta.items.count() for venta in ventas)
        context['currency_totals'] = totals
        context['fecha_inicio'] = self.request.GET.get('fecha_inicio', '')
        context['fecha_fin'] = self.request.GET.get('fecha_fin', '')
        context['moneda'] = self.request.GET.get('moneda', '')
        context['today'] = timezone.localdate()
        return context


class VentaCreateView(AdminRequiredMixin, generic.CreateView):
    model = Venta
    form_class = VentaForm
    template_name = 'panaderia/venta_form.html'
    success_url = reverse_lazy('panaderia:venta_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('item_form', VentaItemForm())
        return context

    def form_valid(self, form):
        item_form = VentaItemForm(self.request.POST)
        if not item_form.is_valid():
            return self.form_invalid(form, item_form)

        self.object = form.save(commit=False)
        self.object.save()

        item = item_form.save(commit=False)
        item.venta = self.object
        item.moneda = self.object.moneda
        item.save()

        if not item.apply_stock_change():
            item.delete()
            form.add_error(None, f"Stock insuficiente para {item.producto.nombre}.")
            return self.form_invalid(form, item_form)

        self.object.total = item.cantidad * item.precio_unitario
        self.object.save(update_fields=['total'])
        return redirect(self.get_success_url())

    def form_invalid(self, form, item_form=None):
        if item_form is None:
            item_form = VentaItemForm(self.request.POST)
        return self.render_to_response(self.get_context_data(form=form, item_form=item_form))


class VentaReportView(AdminRequiredMixin, generic.TemplateView):
    template_name = 'panaderia/reportes.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ventas = Venta.objects.prefetch_related('items__producto').all()
        employee_insumos = EmployeeInsumo.objects.all()
        gastos = Gasto.objects.all()
        recursos = Panaderia_items.objects.all()
        fecha_inicio = self.request.GET.get('fecha_inicio')
        fecha_fin = self.request.GET.get('fecha_fin')

        if fecha_inicio:
            ventas = ventas.filter(fecha__gte=fecha_inicio)
            employee_insumos = employee_insumos.filter(fecha__gte=fecha_inicio)
            gastos = gastos.filter(fecha__gte=fecha_inicio)
        if fecha_fin:
            ventas = ventas.filter(fecha__lte=fecha_fin)
            employee_insumos = employee_insumos.filter(fecha__lte=fecha_fin)
            gastos = gastos.filter(fecha__lte=fecha_fin)

        context['ventas'] = ventas
        # Para el inventario: si se filtra por fecha, mostramos el stock correspondiente a ese periodo
        productos = Producto.objects.all()
        productos_snapshot = []
        from django.db.models import Sum
        target_date = None
        if fecha_fin:
            # usar la fecha_fin como referencia para el snapshot
            try:
                from django.utils.dateparse import parse_date
                target_date = parse_date(fecha_fin)
            except Exception:
                target_date = None
        elif fecha_inicio:
            try:
                from django.utils.dateparse import parse_date
                target_date = parse_date(fecha_inicio)
            except Exception:
                target_date = None

        if target_date:
            # reconstruir stock al final del periodo: stock_actual + ventas posteriores al periodo
            for producto in productos:
                sold_after = VentaItem.objects.filter(producto=producto, venta__fecha__gt=target_date).aggregate(total_sold=Sum('cantidad'))['total_sold'] or 0
                stock_on_date = producto.stock + int(sold_after)
                productos_snapshot.append({'nombre': producto.nombre, 'stock': stock_on_date})
        else:
            for producto in productos:
                productos_snapshot.append({'nombre': producto.nombre, 'stock': producto.stock})

        context['productos'] = productos_snapshot
        context['recursos'] = recursos.order_by('tipo_item', 'marca__nombre')
        context['employee_insumos'] = employee_insumos.order_by('-fecha', '-created_at')
        context['gastos'] = gastos.order_by('-fecha', '-created_at')
        context['fecha_inicio'] = fecha_inicio or ''
        context['fecha_fin'] = fecha_fin or ''

        totals = {'COP': 0, 'VES': 0, 'USD': 0}
        for venta in ventas:
            totals[venta.moneda] += float(venta.total)
        context['currency_totals'] = totals
        context['employee_insumos_total'] = sum(float(item.costo) for item in employee_insumos)
        context['gastos_total'] = sum(float(item.monto) for item in gastos)
        context['pending_employee_count'] = employee_insumos.filter(pagado=False).count()
        context['pending_expense_count'] = gastos.filter(pagado=False).count()
        return context


@admin_required
def export_report_pdf(request):
    ventas = Venta.objects.prefetch_related('items__producto').all()
    productos = Producto.objects.all()
    recursos = Panaderia_items.objects.all()
    employee_insumos = EmployeeInsumo.objects.all()
    gastos = Gasto.objects.all()
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')

    if fecha_inicio:
        ventas = ventas.filter(fecha__gte=fecha_inicio)
        employee_insumos = employee_insumos.filter(fecha__gte=fecha_inicio)
        gastos = gastos.filter(fecha__gte=fecha_inicio)
    if fecha_fin:
        ventas = ventas.filter(fecha__lte=fecha_fin)
        employee_insumos = employee_insumos.filter(fecha__lte=fecha_fin)
        gastos = gastos.filter(fecha__lte=fecha_fin)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.6 * inch, leftMargin=0.6 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    story = []

    logo_path = os.path.join(settings.BASE_DIR, 'panaderia', 'static', 'panaderia', 'img', 'logo.png')
    logo = Image(logo_path, width=1.0 * inch, height=1.0 * inch)
    header = [logo, Paragraph('Grupo Panadería Los Ángeles Santa Elena<br/><b>Reporte general</b>', styles['Title'])]
    story.append(Table([header], colWidths=[1.2 * inch, 5.5 * inch]))
    story.append(Spacer(1, 0.2 * inch))

    totals = {'COP': 0.0, 'VES': 0.0, 'USD': 0.0}
    for venta in ventas:
        totals[venta.moneda] += float(venta.total)

    story.append(Paragraph('Totales por moneda', styles['Heading2']))
    totals_data = [
        ['Moneda', 'Total'],
        ['Pesos colombianos', f"{totals['COP']:.2f}"],
        ['Bolívares venezolanos', f"{totals['VES']:.2f}"],
        ['Dólares', f"{totals['USD']:.2f}"],
    ]
    totals_table = Table(totals_data, repeatRows=1, colWidths=[3.0 * inch, 3.0 * inch])
    totals_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6D4C41')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 1), (0, 1), colors.HexColor('#1976d2')),
        ('BACKGROUND', (0, 2), (0, 2), colors.HexColor('#fbc02d')),
        ('BACKGROUND', (0, 3), (0, 3), colors.HexColor('#388e3c')),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.whitesmoke),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.black),
        ('TEXTCOLOR', (0, 3), (-1, 3), colors.whitesmoke),
        # Force numeric column colors for legibility: Pesos (row 1) and Dólares (row 3)
        ('TEXTCOLOR', (1, 1), (1, 1), colors.black),
        ('TEXTCOLOR', (1, 3), (1, 3), colors.black),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D7C4A7')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph('Ventas', styles['Heading2']))
    table_data = [['Fecha', 'Moneda', 'Producto', 'Categoría', 'Cantidad', 'Precio unitario', 'Total']]
    for venta in ventas:
        for item in venta.items.all():
            table_data.append([
                str(venta.fecha),
                venta.get_moneda_display(),
                item.producto.nombre,
                item.producto.get_categoria_display(),
                str(item.cantidad),
                f"{item.precio_unitario:.2f}",
                f"{venta.total:.2f}",
            ])

    if len(table_data) == 1:
        table_data.append(['Sin ventas registradas', '', '', '', '', '', ''])

    sales_table = Table(table_data, repeatRows=1)
    sales_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6D4C41')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D7C4A7')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ]))
    story.append(sales_table)
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph('Inventario general', styles['Heading2']))
    product_table_data = [['Nombre', 'Marca', 'Categoría', 'Stock']]
    for producto in productos:
        product_table_data.append([
            producto.nombre,
            producto.marca.nombre if producto.marca else '-',
            producto.get_categoria_display(),
            str(producto.stock),
        ])

    if len(product_table_data) == 1:
        product_table_data.append(['Sin productos registrados', '', '', ''])

    product_table = Table(product_table_data, repeatRows=1)
    product_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F4B400')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D7C4A7')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ]))
    story.append(product_table)
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph('Inventario del Panadero (Recursos)', styles['Heading2']))
    recurso_table_data = [['Tipo de Item', 'Marca', 'Cantidad', 'Stock']]
    for recurso in recursos:
        recurso_table_data.append([
            recurso.tipo_item,
            recurso.marca.nombre if recurso.marca else '-',
            str(recurso.cantidad),
            str(recurso.stock),
        ])

    if len(recurso_table_data) == 1:
        recurso_table_data.append(['Sin recursos registrados', '', '', ''])

    recurso_table = Table(recurso_table_data, repeatRows=1)
    recurso_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8D6E63')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D7C4A7')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ]))
    story.append(recurso_table)
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph('Insumos de empleados', styles['Heading2']))
    employee_table_data = [['Empleado', 'Descripción', 'Cantidad', 'Costo', 'Estado']]
    for insumo in employee_insumos:
        employee_table_data.append([
            insumo.empleado,
            insumo.descripcion or '-',
            str(insumo.cantidad),
            f"{insumo.costo:.2f}",
            'Pagado' if insumo.pagado else 'Pendiente',
        ])

    if len(employee_table_data) == 1:
        employee_table_data.append(['Sin insumos registrados', '', '', '', ''])

    employee_table = Table(employee_table_data, repeatRows=1)
    employee_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1976D2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D7C4A7')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(employee_table)
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph('Gastos', styles['Heading2']))
    gasto_table_data = [['Proveedor', 'Descripción', 'Monto', 'Estado']]
    for gasto in gastos:
        gasto_table_data.append([
            gasto.proveedor,
            gasto.descripcion or '-',
            f"{gasto.monto:.2f}",
            'Pagado' if gasto.pagado else 'Pendiente',
        ])

    if len(gasto_table_data) == 1:
        gasto_table_data.append(['Sin gastos registrados', '', '', ''])

    gasto_table = Table(gasto_table_data, repeatRows=1)
    gasto_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#388E3C')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D7C4A7')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(gasto_table)

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_panaderia.pdf"'
    return response





@login_required
def export_backup_pdf(request):
    """Exporta un PDF con el snapshot de inventario para una fecha dada (GET param `date`)."""
    from django.utils.dateparse import parse_date
    date_str = request.GET.get('date')
    target_date = parse_target_date(date_str)

    productos = Producto.objects.all()

    from django.db.models import Sum
    productos_data = [['Producto', 'Stock (al)']]
    for producto in productos:
        if target_date:
            sold_after = VentaItem.objects.filter(producto=producto, venta__fecha__gt=target_date).aggregate(total_sold=Sum('cantidad'))['total_sold'] or 0
            stock_on_date = producto.stock + int(sold_after)
        else:
            stock_on_date = producto.stock
        productos_data.append([producto.nombre, str(stock_on_date)])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.6 * inch, leftMargin=0.6 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    story = []
    header_text = 'Snapshot de inventario'
    if target_date:
        header_text += f' al {target_date.strftime("%Y-%m-%d")} '
    story.append(Paragraph('Grupo Panadería Los Ángeles Santa Elena', styles['Title']))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(header_text, styles['Heading2']))
    story.append(Spacer(1, 0.1 * inch))

    prod_table = Table(productos_data, repeatRows=1)
    prod_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F4B400')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D7C4A7')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ]))
    story.append(prod_table)
    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    filename = 'snapshot_inventario'
    if target_date:
        filename += f'-{target_date.strftime("%Y%m%d")}'
    filename += '.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@admin_required
def backups_list(request):
    # Permitir seleccionar fecha para ver snapshot de inventario
    date_str = request.GET.get('date')
    target_date = parse_target_date(date_str)

    # lista de backups
    backups = Backup.objects.order_by('-created_at')

    ventas = Venta.objects.prefetch_related('items__producto').order_by('-fecha', '-creado_en')
    if target_date:
        ventas = ventas.filter(fecha=target_date)

    # construir snapshot de inventario para la fecha seleccionada (si existe)
    productos = Producto.objects.all()
    productos_snapshot = []
    from django.db.models import Sum
    if target_date:
        for producto in productos:
            sold_after = VentaItem.objects.filter(producto=producto, venta__fecha__gt=target_date).aggregate(total_sold=Sum('cantidad'))['total_sold'] or 0
            stock_on_date = producto.stock + int(sold_after)
            productos_snapshot.append({'nombre': producto.nombre, 'stock': stock_on_date})
    else:
        for producto in productos:
            productos_snapshot.append({'nombre': producto.nombre, 'stock': producto.stock})

    ventas_totales = {
        'count': ventas.count(),
        'items': sum(venta.items.count() for venta in ventas),
        'total': sum(float(venta.total) for venta in ventas),
    }

    return render(request, 'panaderia/backups.html', {
        'backups': backups,
        'productos': productos_snapshot,
        'selected_date': target_date,
        'ventas': ventas,
        'ventas_totales': ventas_totales,
    })


@admin_required
def create_backup(request):
    """Copia el archivo de base de datos actual al directorio MEDIA/backups y crea registro."""
    import shutil
    db_path = settings.DATABASES['default']['NAME']
    timestamp = timezone.now().strftime('%Y%m%d-%H%M%S')
    dest_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f'backup-{timestamp}.sqlite3')
    try:
        shutil.copy2(db_path, dest_path)
        # si se pidió una fecha, incluirla en el registro y nombre del archivo
        req_date = request.GET.get('date') or request.POST.get('date')
        target = parse_target_date(req_date)
        filename = os.path.basename(dest_path)
        if target:
            # renombrar archivo para incluir la fecha objetivo
            name_with_date = f"backup-{target.strftime('%Y%m%d')}-{timestamp}.sqlite3"
            new_path = os.path.join(dest_dir, name_with_date)
            os.rename(dest_path, new_path)
            dest_path = new_path
            filename = os.path.basename(dest_path)

        backup = Backup.objects.create(file=f'backups/{filename}', created_by=request.user, target_date=target)
        messages.success(request, f'Respaldo creado: {backup.file.name}')
        f = open(dest_path, 'rb')
        response = FileResponse(f, as_attachment=True, filename=filename)
        return response
    except Exception as e:
        messages.error(request, f'No se pudo crear el respaldo: {e}')
    return redirect('panaderia:backups')


def _import_backup_database(dest_path):
    from django.db import transaction

    def _table_exists(conn, table_name):
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
        return row is not None

    def _column_names(conn, table_name):
        return [row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()]

    def _get_value(row, columns, field_name):
        if field_name in columns:
            return row[columns.index(field_name)]
        return None

    def _to_bool(value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {'1', 'true', 'si', 'sí', 'yes', 'y'}:
                return True
            if text in {'0', 'false', 'no', 'n', ''}:
                return False
        return bool(value)

    def _to_decimal(value):
        if value in (None, ''):
            return Decimal('0')
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal('0')

    def _to_date(value):
        if value in (None, ''):
            return timezone.now().date()
        if isinstance(value, datetime):
            return value.date()
        parsed = parse_date(str(value))
        return parsed or timezone.now().date()

    def _to_datetime(value):
        if value in (None, ''):
            return timezone.now()
        if isinstance(value, datetime):
            return value
        parsed = parse_datetime(str(value))
        return parsed or timezone.now()

    conn = sqlite3.connect(dest_path)
    try:
        with transaction.atomic():
            VentaItem.objects.all().delete()
            Venta.objects.all().delete()
            Bebida.objects.all().delete()
            Chucheria.objects.all().delete()
            Producto.objects.all().delete()
            Marca.objects.all().delete()

            brand_id_map = {}
            if _table_exists(conn, 'panaderia_marca'):
                columns = _column_names(conn, 'panaderia_marca')
                for row in conn.execute(f'SELECT * FROM "panaderia_marca"').fetchall():
                    source_id = _get_value(row, columns, 'id')
                    nombre = str(_get_value(row, columns, 'nombre') or '').strip()
                    if not nombre:
                        continue
                    tipo = str(_get_value(row, columns, 'tipo') or 'panaderia').strip() or 'panaderia'
                    marca = Marca.objects.create(id=source_id, nombre=nombre, tipo=tipo)
                    if source_id is not None:
                        brand_id_map[source_id] = marca.pk

            product_id_map = {}
            if _table_exists(conn, 'panaderia_producto'):
                columns = _column_names(conn, 'panaderia_producto')
                for row in conn.execute(f'SELECT * FROM "panaderia_producto"').fetchall():
                    source_id = _get_value(row, columns, 'id')
                    nombre = str(_get_value(row, columns, 'nombre') or '').strip()
                    if not nombre:
                        continue
                    marca_id = _get_value(row, columns, 'marca_id')
                    marca_obj = None
                    if marca_id is not None:
                        marca_obj = Marca.objects.filter(pk=brand_id_map.get(marca_id)).first()
                    producto = Producto.objects.create(
                        id=source_id,
                        nombre=nombre,
                        existencia_manana=int(_get_value(row, columns, 'existencia_manana') or 0),
                        entrada_manana=int(_get_value(row, columns, 'entrada_manana') or 0),
                        entrada_tarde=int(_get_value(row, columns, 'entrada_tarde') or 0),
                        stock=int(_get_value(row, columns, 'stock') or 0),
                        categoria=str(_get_value(row, columns, 'categoria') or 'pan_salado').strip() or 'pan_salado',
                        marca=marca_obj,
                        sabor=_to_bool(_get_value(row, columns, 'sabor')),
                    )
                    if source_id is not None:
                        product_id_map[source_id] = producto.pk

            if _table_exists(conn, 'panaderia_bebida'):
                columns = _column_names(conn, 'panaderia_bebida')
                for row in conn.execute('SELECT * FROM "panaderia_bebida"').fetchall():
                    source_product_id = _get_value(row, columns, 'producto_ptr_id')
                    dest_product_id = product_id_map.get(source_product_id)
                    if not dest_product_id:
                        continue
                    volumen_ml = _get_value(row, columns, 'volumen_ml')
                    Bebida.objects.create(producto_ptr_id=dest_product_id, volumen_ml=int(volumen_ml) if volumen_ml is not None else None)

            if _table_exists(conn, 'panaderia_chucheria'):
                columns = _column_names(conn, 'panaderia_chucheria')
                for row in conn.execute('SELECT * FROM "panaderia_chucheria"').fetchall():
                    source_product_id = _get_value(row, columns, 'producto_ptr_id')
                    dest_product_id = product_id_map.get(source_product_id)
                    if not dest_product_id:
                        continue
                    descripcion = str(_get_value(row, columns, 'descripcion') or '').strip()
                    Chucheria.objects.create(producto_ptr_id=dest_product_id, descripcion=descripcion)

            venta_id_map = {}
            if _table_exists(conn, 'panaderia_venta'):
                columns = _column_names(conn, 'panaderia_venta')
                for row in conn.execute('SELECT * FROM "panaderia_venta"').fetchall():
                    source_id = _get_value(row, columns, 'id')
                    venta = Venta.objects.create(
                        id=source_id,
                        fecha=_to_date(_get_value(row, columns, 'fecha')),
                        moneda=str(_get_value(row, columns, 'moneda') or 'COP').strip() or 'COP',
                        estado=str(_get_value(row, columns, 'estado') or 'abierta').strip() or 'abierta',
                        total=_to_decimal(_get_value(row, columns, 'total')),
                        observacion=str(_get_value(row, columns, 'observacion') or '').strip(),
                    )
                    if source_id is not None:
                        venta_id_map[source_id] = venta.pk

            if _table_exists(conn, 'panaderia_ventaitem'):
                columns = _column_names(conn, 'panaderia_ventaitem')
                for row in conn.execute('SELECT * FROM "panaderia_ventaitem"').fetchall():
                    source_id = _get_value(row, columns, 'id')
                    source_venta_id = _get_value(row, columns, 'venta_id')
                    source_product_id = _get_value(row, columns, 'producto_id')
                    dest_venta_id = venta_id_map.get(source_venta_id)
                    dest_product_id = product_id_map.get(source_product_id)
                    if not dest_venta_id or not dest_product_id:
                        continue
                    VentaItem.objects.create(
                        id=source_id,
                        venta_id=dest_venta_id,
                        producto_id=dest_product_id,
                        cantidad=int(_get_value(row, columns, 'cantidad') or 0),
                        precio_unitario=_to_decimal(_get_value(row, columns, 'precio_unitario')),
                        moneda=str(_get_value(row, columns, 'moneda') or 'COP').strip() or 'COP',
                    )
    finally:
        conn.close()


@admin_required
def upload_backup(request):
    if request.method == 'POST':
        f = request.FILES.get('backup_file')
        if f:
            dest_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, f.name)
            with open(dest_path, 'wb') as out:
                for chunk in f.chunks():
                    out.write(chunk)
            backup = Backup.objects.create(file=f'backups/{f.name}', created_by=request.user)
            messages.success(request, 'Respaldo subido correctamente.')
            try:
                do_import = request.POST.get('import') == '1' or request.GET.get('import') == '1'
            except Exception:
                do_import = False
            if do_import:
                try:
                    _import_backup_database(dest_path)
                    messages.success(request, 'Importación desde respaldo completada: marcas, productos, ventas e ítems restaurados.')
                except Exception as e:
                    messages.error(request, f'Error al importar datos desde el respaldo: {e}')
    return redirect('panaderia:backups')


@admin_required
def download_backup(request, pk):
    backup = get_object_or_404(Backup, pk=pk)
    file_path = os.path.join(settings.MEDIA_ROOT, backup.file.name)
    if not os.path.exists(file_path):
        messages.error(request, 'El archivo de respaldo no existe en el servidor.')
        return redirect('panaderia:backups')
    try:
        f = open(file_path, 'rb')
        return FileResponse(f, as_attachment=True, filename=os.path.basename(file_path))
    except Exception as e:
        messages.error(request, f'Error al leer el archivo: {e}')
        return redirect('panaderia:backups')


 


def set_security_word(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method == 'POST':
        form = SecurityWordForm(request.POST)
        if form.is_valid():
            word = form.cleaned_data['security_word']
            profile = getattr(request.user, 'profile', None)
            if not profile:
                from .models import Profile
                profile = Profile.objects.create(user=request.user)
            profile.set_security_word(word)
            messages.success(request, 'Palabra de seguridad guardada.')
            return redirect('panaderia:recurso_list')
    else:
        form = SecurityWordForm()
    return render(request, 'panaderia/set_security_word.html', {'form': form})


def password_reset_request_by_word(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=username)
            return redirect('password_reset_confirm_by_word', username=user.username)
        except user_model.DoesNotExist:
            messages.error(request, 'Usuario no encontrado')
    return render(request, 'panaderia/password_reset_request.html')


def password_reset_confirm_by_word(request, username):
    user_model = get_user_model()
    user = get_object_or_404(user_model, username=username)
    profile = getattr(user, 'profile', None)
    if request.method == 'POST':
        answer = request.POST.get('security_word')
        if profile and profile.check_security_word(answer):
            form = PasswordResetByWordForm(user, request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Contraseña actualizada. Puedes iniciar sesión.')
                return redirect('login')
        else:
            messages.error(request, 'Palabra de seguridad incorrecta')
            form = PasswordResetByWordForm(user)
    else:
        form = PasswordResetByWordForm(user)
    return render(request, 'panaderia/password_reset_confirm.html', {'form': form, 'username': username})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.info(request, "Has cerrado sesión exitosamente.")
    return redirect('login')


def logged_out_view(request):
    return render(request, 'registration/logged_out.html')


@login_required
def cerrar_ventas(request):
    if request.method == 'POST':
        fecha_raw = request.POST.get('fecha') or str(timezone.localdate())
        # Try parsing ISO and common numeric formats first
        from django.utils.dateparse import parse_date
        fecha_obj = parse_date(fecha_raw)
        if not fecha_obj:
            # Try common numeric formats
            from datetime import datetime
            parsed = False
            for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d'):
                try:
                    fecha_obj = datetime.strptime(fecha_raw, fmt).date()
                    parsed = True
                    break
                except Exception:
                    continue
            if not parsed:
                # Try Spanish textual month like '30 de junio de 2026'
                import re
                m = re.search(r"(\d{1,2})\s+de\s+([a-zA-ZñÑ]+)\s+de\s+(\d{4})", fecha_raw, re.IGNORECASE)
                if m:
                    day, month_name, year = m.groups()
                    month_name = month_name.lower()
                    months_es = {
                        'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
                        'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
                        'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
                    }
                    month_num = months_es.get(month_name)
                    if month_num:
                        try:
                            fecha_obj = datetime(int(year), month_num, int(day)).date()
                        except Exception:
                            fecha_obj = timezone.localdate()
                    else:
                        fecha_obj = timezone.localdate()
                else:
                    # Fallback to today
                    fecha_obj = timezone.localdate()

        ventas = Venta.objects.filter(fecha=fecha_obj, estado='abierta')
        count = ventas.update(estado='cerrada')
        messages.success(request, f'Se han cerrado {count} ventas para {fecha_obj}.')
    return redirect('panaderia:venta_list')
