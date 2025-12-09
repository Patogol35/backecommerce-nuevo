from decimal import Decimal
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import viewsets, generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from .models import Producto, Categoria, Carrito, ItemCarrito, Pedido, ItemPedido
from .serializers import (
    ProductoSerializer,
    CategoriaSerializer,
    CarritoSerializer,
    UserSerializer,
    ItemCarritoSerializer,
    PedidoSerializer,
)
from .filters import ProductoFilter
# imports para activación de cuenta por email
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.mail import send_mail
from django.conf import settings
# ---------------------------
# ViewSets / CRUD productos
# ---------------------------
class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer
    filterset_class = ProductoFilter
class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer
# ---------------------------
# Carrito: agregar / eliminar / actualizar
# ---------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def agregar_al_carrito(request):
    producto_id = request.data.get('producto_id')
    cantidad = int(request.data.get('cantidad', 1))
    try:
        producto = Producto.objects.get(id=producto_id)
    except Producto.DoesNotExist:
        return Response({'error': 'Producto no encontrado'}, status=status.HTTP_404_NOT_FOUND)
    # Validar stock disponible
    if cantidad > producto.stock:
        return Response({'error': f'Solo hay {producto.stock} unidades disponibles'}, status=status.HTTP_400_BAD_REQUEST)
    carrito, _ = Carrito.objects.get_or_create(usuario=request.user)
    item, creado = ItemCarrito.objects.get_or_create(
        carrito=carrito,
        producto=producto,
        defaults={'cantidad': cantidad}
    )
    if not creado:
        nueva_cantidad = item.cantidad + cantidad
        # Validar stock en actualización
        if nueva_cantidad > producto.stock:
            return Response({'error': f'Solo hay {producto.stock} unidades disponibles'}, status=status.HTTP_400_BAD_REQUEST)
        if nueva_cantidad <= 0:
            item.delete()
            return Response({'message': 'Producto eliminado del carrito'}, status=status.HTTP_200_OK)
        item.cantidad = nueva_cantidad
        item.save()
    if creado and item.cantidad <= 0:
        item.delete()
        return Response({'message': 'Producto eliminado del carrito'}, status=status.HTTP_200_OK)
    return Response(ItemCarritoSerializer(item).data, status=status.HTTP_201_CREATED)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def eliminar_del_carrito(request, item_id):
    try:
        item = ItemCarrito.objects.get(id=item_id, carrito__usuario=request.user)
        item.delete()
        return Response({'message': 'Producto eliminado del carrito'}, status=status.HTTP_200_OK)
    except ItemCarrito.DoesNotExist:
        return Response({'error': 'Producto no encontrado en el carrito'}, status=status.HTTP_404_NOT_FOUND)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def actualizar_cantidad_carrito(request, item_id):
    try:
        cantidad = int(request.data.get('cantidad', 1))
    except (TypeError, ValueError):
        return Response({'error': 'Cantidad inválida'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        item = ItemCarrito.objects.get(id=item_id, carrito__usuario=request.user)
    except ItemCarrito.DoesNotExist:
        return Response({'error': 'Producto no encontrado en el carrito'}, status=status.HTTP_404_NOT_FOUND)
    # Validar stock
    if cantidad > item.producto.stock:
        return Response({'error': f'Solo hay {item.producto.stock} unidades disponibles'}, status=status.HTTP_400_BAD_REQUEST)
    if cantidad <= 0:
        item.delete()
        return Response({'message': 'Producto eliminado del carrito'}, status=status.HTTP_200_OK)
    item.cantidad = cantidad
    item.save()
    return Response(ItemCarritoSerializer(item).data, status=status.HTTP_200_OK)
# ---------------------------
# Carrito view
# ---------------------------
class CarritoView(generics.RetrieveAPIView):
    serializer_class = CarritoSerializer
    permission_classes = [permissions.IsAuthenticated]
    def get_object(self):
        carrito, _ = Carrito.objects.get_or_create(usuario=self.request.user)
        return carrito
# ---------------------------
# Registro (RegisterView) — se mantiene tu clase, solo se añade perform_create
# ---------------------------
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    def perform_create(self, serializer):
        user = serializer.save()
        # Crear uid y token
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        # Link de activación apuntando al frontend
        activation_link = f"{settings.FRONTEND_URL}/activate/{uid}/{token}"
        html_message = f"""
            <h2>Bienvenido {user.username}</h2>
            <p>Para activar tu cuenta haz clic en el siguiente enlace:</p>
            <p><a href="{activation_link}">Activar cuenta</a></p>
            <p>Si no solicitaste esto, ignora este correo.</p>
        """
        send_mail(
            'Activa tu cuenta',
            f'Activa tu cuenta aquí: {activation_link}',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False
        )
# ---------------------------
# Pedidos
# ---------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def crear_pedido(request):
    carrito, _ = Carrito.objects.get_or_create(usuario=request.user)
    items = list(carrito.items.select_related('producto'))
    if not items:
        return Response({'error': 'El carrito está vacío'}, status=status.HTTP_400_BAD_REQUEST)
    for it in items:
        if it.producto.stock < it.cantidad:
            return Response({'error': f'Stock insuficiente para {it.producto.nombre}'}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        total = sum((Decimal(it.producto.precio) * it.cantidad for it in items), Decimal('0'))
        pedido = Pedido.objects.create(usuario=request.user, total=total)
        for it in items:
            prod = it.producto
            prod.stock -= it.cantidad
            prod.save()
            ItemPedido.objects.create(
                pedido=pedido,
                producto=prod,
                cantidad=it.cantidad,
                precio_unitario=prod.precio
            )
        carrito.items.all().delete()
    return Response(PedidoSerializer(pedido).data, status=status.HTTP_201_CREATED)
class PedidoPagination(PageNumberPagination):
    page_size = 10
class ListaPedidosUsuario(generics.ListAPIView):
    serializer_class = PedidoSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PedidoPagination
    def get_queryset(self):
        return Pedido.objects.filter(usuario=self.request.user).order_by('-fecha')
# ---------------------------
# Perfil
# ---------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    user = request.user
    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email,
    })
# ---------------------------
# Activación de cuenta (vista pública)
# ---------------------------
@api_view(['GET'])
def activar_usuario(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return Response({"error": "Link inválido"}, status=400)
    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        return Response({"message": "Cuenta activada correctamente"}, status=200)
    return Response({"error": "Token inválido o expirado"}, status=400)