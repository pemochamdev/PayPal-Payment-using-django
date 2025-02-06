from rest_framework import serializers
from payments.models import Payment, PaymentRefund

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('payment_id', 'status', 'payer_email', 'payer_id')

class PaymentRefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentRefund
        fields = '__all__'
        read_only_fields = ('refund_id', 'status')