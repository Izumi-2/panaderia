from django import forms
from .models import Producto, Marca, Bebida, Panaderia_items, Venta, VentaItem
from django.contrib.auth.models import User
from django.contrib.auth.forms import SetPasswordForm


class SecurityWordForm(forms.Form):
    security_word = forms.CharField(label='Palabra de seguridad', widget=forms.PasswordInput(attrs={'class':'form-control'}), max_length=128)


class PasswordResetByWordForm(SetPasswordForm):
    # inherits new_password1 and new_password2 fields
    pass


class MarcaForm(forms.ModelForm):
    class Meta:
        model = Marca
        fields = ['nombre', 'tipo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la marca'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
        }


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        # Removed 'precio' — inventory will be governed only by 'stock'
        fields = ['nombre', 'marca', 'categoria', 'stock']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del producto'}),
            'marca': forms.Select(attrs={'class': 'form-select'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Cantidad disponible'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ensure marca queryset is available
        self.fields['marca'].queryset = Marca.objects.all()


class BebidaForm(forms.ModelForm):
    class Meta:
        model = Bebida
        fields = ['nombre', 'marca', 'stock', 'volumen_ml']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del producto de nevera'}),
            'marca': forms.Select(attrs={'class': 'form-select'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Cantidad disponible'}),
            'volumen_ml': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Volumen en ml'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['marca'].queryset = Marca.objects.all()

    def save(self, commit=True):
        bebida = super().save(commit=False)
        bebida.categoria = 'bebida'
        if commit:
            bebida.save()
        return bebida


class RecursoForm(forms.ModelForm):
    class Meta:
        model = Panaderia_items
        fields = ['tipo_item', 'marca', 'cantidad']
        widgets = {
            'tipo_item': forms.Select(attrs={'class': 'form-select'}),
            'marca': forms.Select(attrs={'class': 'form-select'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Cantidad disponible'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['marca'].queryset = Marca.objects.all()


class VentaForm(forms.ModelForm):
    class Meta:
        model = Venta
        fields = ['fecha', 'moneda']
        widgets = {
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'moneda': forms.Select(attrs={'class': 'form-select'}),
        }


class VentaItemForm(forms.ModelForm):
    class Meta:
        model = VentaItem
        fields = ['producto', 'cantidad', 'precio_unitario']
        widgets = {
            'producto': forms.Select(attrs={'class': 'form-select'}),
            'cantidad': forms.NumberInput(attrs={'class': 'form-control'}),
            'precio_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['producto'].queryset = Producto.objects.all()
        self.fields['producto'].label_from_instance = lambda obj: obj.nombre

    def clean(self):
        cleaned_data = super().clean()
        producto = cleaned_data.get('producto')
        cantidad = cleaned_data.get('cantidad')
        if producto and cantidad is not None and cantidad > producto.stock:
            raise forms.ValidationError(
                f"Stock insuficiente para {producto.nombre}. Disponible: {producto.stock}."
            )
        return cleaned_data


class ProfileConfigForm(forms.Form):
    display_name = forms.CharField(label='Nombre para mostrar', required=False, max_length=150, widget=forms.TextInput(attrs={'class':'form-control'}))
    phone = forms.CharField(label='Teléfono', required=False, max_length=30, widget=forms.TextInput(attrs={'class':'form-control'}))
    location = forms.CharField(label='Ubicación', required=False, max_length=200, widget=forms.TextInput(attrs={'class':'form-control'}))
    receive_notifications = forms.BooleanField(label='Recibir notificaciones', required=False, widget=forms.CheckboxInput())

    def save(self, user):
        profile = getattr(user, 'profile', None)
        if profile is None:
            # crear perfil si no existe
            from .models import Profile
            profile = Profile.objects.create(user=user)
        config = profile.config or {}
        config.update({
            'display_name': self.cleaned_data.get('display_name', ''),
            'phone': self.cleaned_data.get('phone', ''),
            'location': self.cleaned_data.get('location', ''),
            'receive_notifications': bool(self.cleaned_data.get('receive_notifications', False)),
        })
        profile.config = config
        profile.save()
        return profile
