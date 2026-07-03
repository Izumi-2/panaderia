import io
from django.http import HttpResponse
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

from ..models import Producto, Panaderia_items, Venta


class VentaReportView(LoginRequiredMixin, generic.TemplateView):
    template_name = 'panaderia/reportes.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ventas'] = Venta.objects.prefetch_related('items__producto').all()
        context['productos'] = Producto.objects.all()
        context['recursos'] = Panaderia_items.objects.all()
        return context


def export_report_pdf(request):
    ventas = Venta.objects.prefetch_related('items__producto').all()
    productos = Producto.objects.all()
    recursos = Panaderia_items.objects.all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.6 * inch, leftMargin=0.6 * inch, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    story = []

    logo_path = 'panaderia/static/panaderia/img/logo.png'
    logo = Image(logo_path, width=1.0 * inch, height=1.0 * inch)
    header = [logo, Paragraph('Grupo Panadería Los Ángeles Santa Elena<br/><b>Reporte general</b>', styles['Title'])]
    story.append(Table([header], colWidths=[1.2 * inch, 5.5 * inch]))
    story.append(Spacer(1, 0.2 * inch))

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
    recurso_table_data = [['Tipo de Item', 'Marca', 'Cantidad']]
    for recurso in recursos:
        recurso_table_data.append([
            recurso.get_tipo_item_display(),
            recurso.marca.nombre if recurso.marca else '-',
            str(recurso.cantidad),
        ])

    if len(recurso_table_data) == 1:
        recurso_table_data.append(['Sin recursos registrados', '', ''])

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

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_panaderia.pdf"'
    return response
