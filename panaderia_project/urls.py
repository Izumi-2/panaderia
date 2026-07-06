"""
URL configuration for panaderia_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic.base import RedirectView
from django.views.generic import RedirectView
from panaderia import views as pan_views

pan_urls = [
    path('productos/', pan_views.ProductListView.as_view(), name='product_list'),
    path('productos/nuevo/', pan_views.ProductCreateView.as_view(), name='product_create'),
    path('productos/<int:pk>/editar/', pan_views.ProductUpdateView.as_view(), name='product_update'),
    path('productos/<int:pk>/eliminar/', pan_views.ProductDeleteView.as_view(), name='product_delete'),
    path('productos/cierre-jornada/', pan_views.close_day_products, name='close_day_products'),
    path('productos/<int:pk>/sobrante/', pan_views.apply_surplus_product, name='apply_surplus_product'),
    path('productos/<int:pk>/', pan_views.ProductDetailView.as_view(), name='product_detail'),
    path('inventario/', pan_views.RecursoListView.as_view(), name='recurso_list'),
    path('inventario/nuevo/', pan_views.RecursoCreateView.as_view(), name='recurso_create'),
    path('inventario/<int:pk>/editar/', pan_views.RecursoUpdateView.as_view(), name='recurso_update'),
    path('inventario/<int:pk>/eliminar/', pan_views.RecursoDeleteView.as_view(), name='recurso_delete'),
    path('marcas/', pan_views.MarcaListView.as_view(), name='marca_list'),
    path('marcas/nueva/', pan_views.MarcaCreateView.as_view(), name='marca_create'),
    path('nevera/', pan_views.BebidaListView.as_view(), name='nevera_list'),
    path('nevera/nueva/', pan_views.BebidaCreateView.as_view(), name='nevera_create'),
    path('nevera/<int:pk>/editar/', pan_views.BebidaUpdateView.as_view(), name='nevera_update'),
    path('nevera/<int:pk>/eliminar/', pan_views.BebidaDeleteView.as_view(), name='nevera_delete'),
    path('nevera/<int:pk>/sobrante/', pan_views.apply_surplus_nevera, name='apply_surplus_nevera'),
    path('chucherias/', pan_views.ChucheriaListView.as_view(), name='chucheria_list'),
    path('chucherias/nueva/', pan_views.ChucheriaCreateView.as_view(), name='chucheria_create'),
    path('chucherias/<int:pk>/editar/', pan_views.ChucheriaUpdateView.as_view(), name='chucheria_update'),
    path('chucherias/<int:pk>/eliminar/', pan_views.ChucheriaDeleteView.as_view(), name='chucheria_delete'),
    path('chucherias/<int:pk>/sobrante/', pan_views.apply_surplus_chucheria, name='apply_surplus_chucheria'),
    path('ventas/', pan_views.VentaListView.as_view(), name='venta_list'),
    path('ventas/nueva/', pan_views.VentaCreateView.as_view(), name='venta_create'),
    path('insumos-gastos/', pan_views.insumos_gastos_dashboard, name='insumos_gastos'),
    path('reportes/', pan_views.VentaReportView.as_view(), name='reportes'),
    path('reportes/exportar-pdf/', pan_views.export_report_pdf, name='export_report_pdf'),
    path('ventas/cerrar/', pan_views.cerrar_ventas, name='cerrar_ventas'),
    path('backups/', pan_views.backups_list, name='backups'),
    path('backups/create/', pan_views.create_backup, name='create_backup'),
    path('backups/upload/', pan_views.upload_backup, name='upload_backup'),
    path('backups/download/<int:pk>/', pan_views.download_backup, name='download_backup'),
    path('backups/exportar-pdf/', pan_views.export_backup_pdf, name='export_backup_pdf'),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url='/static/panaderia/img/logo.png')),
    path('accounts/security-word/', pan_views.set_security_word, name='set_security_word'),
    path('accounts/login/', pan_views.AdminLoginView.as_view(), name='login'),
    path('accounts/logout/', pan_views.logout_view, name='logout'),
    path('accounts/logged-out/', pan_views.logged_out_view, name='logged_out'),
    path('accounts/password-reset-by-word/', pan_views.password_reset_request_by_word, name='password_reset_by_word'),
    path('accounts/password-reset-by-word/<str:username>/', pan_views.password_reset_confirm_by_word, name='password_reset_confirm_by_word'),
    path('panaderia/', include((pan_urls, 'panaderia'), namespace='panaderia')),
    path('', RedirectView.as_view(pattern_name='login', permanent=True), name='home'),
]
