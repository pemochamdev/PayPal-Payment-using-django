
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
        
