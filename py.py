#models.py

from django.db import models

from django.utils.translation import gettext_lazy as _
import uuid

class Base(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Payment(Base):
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        COMPLETED = 'completed', _('Completed')
        FAILED = 'failed', _('Failed')
        REFUNDED = 'refunded', _('Refunded')
        PARTIALLY_REFUNDED = 'partially_refunded', _('Partially Refunded')
        
    payment_id = models.CharField(max_length=255, blank=True, null=True)
    currency = models.CharField(max_length=3, default='EUR')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    
    payer_email = models.EmailField(null=True, blank=True)
    payer_id = models.UUIDField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    def __str__(self):
        return f'{self.amount} - {self.status}'
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment_id']),
            models.Index(fields=['status']),
        ]



class PaymentRefund(Base):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    refund_id = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Payment.Status.choices,
        default=Payment.Status.COMPLETED,
    )
    reason = models.TextField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    def __str__(self):
        return f'{self.amount} - {self.status}'
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['refund_id']),
            models.Index(fields=['status']),
        ]


#services.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from payments.services import PaymentService
from payments.models import Payment, PaymentRefund
from .serializers import PaymentSerializer, PaymentRefundSerializer
from payments.exceptions import PaymentError


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    paypal_service = PaymentService()
    
    def create(self,request):
        try:
            amount = float(request.data.get('amount'))
            description = request.data.get('description', '')
            base_url = request.build_absolute_uri('/')[:-1]
            return_url = f'{base_url}/api/payments/execute/'
            cancel_url = f'{base_url}/api/payments/cancel/'
            payment = self.paypal_service.create_payment(
                amount, description, return_url, cancel_url
            )
            
            return Response(
                payment, status=status.HTTP_200_OK
            )
        except PaymentError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    @action(detail=False, methods=['post'])
    def execute(self, request):
        try:
            payment_id = request.data.get('payment_id')
            payer_id = request.data.get('payer_id')
            payment = self.paypal_service.execute_payment(payment_id, payer_id)
            serializer = self.get_serializer(data=payment)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except PaymentError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        try:
            payment = get_object_or_404(Payment, pk=pk)
            amount = float(request.data.get('amount'))
            reason = request.data.get('reason', '')
            refund = self.paypal_service.refund_payment(payment, amount, reason)
            serializer = PaymentRefundSerializer(data=refund)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except PaymentError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        



#views.py


from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from payments.services import PaymentService
from payments.models import Payment, PaymentRefund
from .serializers import PaymentSerializer, PaymentRefundSerializer
from payments.exceptions import PaymentError


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    paypal_service = PaymentService()
    
    def create(self,request):
        try:
            amount = float(request.data.get('amount'))
            description = request.data.get('description', '')
            base_url = request.build_absolute_uri('/')[:-1]
            return_url = f'{base_url}/api/payments/execute/'
            cancel_url = f'{base_url}/api/payments/cancel/'
            payment = self.paypal_service.create_payment(
                amount, description, return_url, cancel_url
            )
            
            return Response(
                payment, status=status.HTTP_200_OK
            )
        except PaymentError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    @action(detail=False, methods=['post'])
    def execute(self, request):
        try:
            payment_id = request.data.get('payment_id')
            payer_id = request.data.get('payer_id')
            payment = self.paypal_service.execute_payment(payment_id, payer_id)
            serializer = self.get_serializer(data=payment)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except PaymentError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        try:
            payment = get_object_or_404(Payment, pk=pk)
            amount = float(request.data.get('amount'))
            reason = request.data.get('reason', '')
            refund = self.paypal_service.refund_payment(payment, amount, reason)
            serializer = PaymentRefundSerializer(data=refund)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except PaymentError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        