from rest_framework import serializers
from .models import Producto, Categoria, Carrito, ItemCarrito, Pedido, ItemPedido
from django.contrib.auth.models import User
# CATEGORÍA
class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = "__all__"
# PRODUCTO
class ProductoSerializer(serializers.ModelSerializer):
    categoria = CategoriaSerializer(read_only=True)
    categoria_id = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.all(),
        source="categoria",
        write_only=True
    )
    class Meta:
        model = Producto
        fields = "__all__"
# ITEM CARRITO
class ItemCarritoSerializer(serializers.ModelSerializer):
    producto = ProductoSerializer(read_only=True)
    subtotal = serializers.SerializerMethodField()
    class Meta:
        model = ItemCarrito
        fields = ['id', 'producto', 'cantidad', 'subtotal']
    def get_subtotal(self, obj):
        return obj.subtotal()
# CARRITO
class CarritoSerializer(serializers.ModelSerializer):
    items = ItemCarritoSerializer(many=True, read_only=True)
    class Meta:
        model = Carrito
        fields = ['id', 'usuario', 'creado', 'items']
# USUARIO — ACTUALIZADO
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password']
    def validate_email(self, value):
        # Validar email único (si no viene email, permitirlo si no quieres forzarlo)
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("El email ya está registrado.")
        return value
    def create(self, validated_data):
        # Crear usuario inactivo hasta activar por email
        user = User(
            username=validated_data['username'],
            email=validated_data.get('email'),
            is_active=False
        )
        user.set_password(validated_data['password'])
        user.save()
        return user
# ITEM PEDIDO
class ItemPedidoSerializer(serializers.ModelSerializer):
    producto = ProductoSerializer(read_only=True)
    subtotal = serializers.SerializerMethodField()
    class Meta:
        model = ItemPedido
        fields = ['producto', 'cantidad', 'precio_unitario', 'subtotal']
    def get_subtotal(self, obj):
        return obj.subtotal()
# PEDIDO
class PedidoSerializer(serializers.ModelSerializer):
    items = ItemPedidoSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    class Meta:
        model = Pedido
        fields = ['id', 'usuario', 'fecha', 'total', 'items']