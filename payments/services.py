import logging
import paypalrestsdk
from django.conf import settings
from payments.models import Payment, PaymentRefund
from payments.exceptions import PaymentError, PaymentValidationError, PaymentProcessError, RefundError

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        self._configure_paypal()
    
    def _configure_paypal(self):
        paypalrestsdk.configure({
            'mode': settings.PAYPAL_CONFIG['PAYPAL_MODE'],
            'client_id': settings.PAYPAL_CONFIG['PAYPAL_CLIENT_ID'],
            'client_secret': settings.PAYPAL_CONFIG['PAYPAL_CLIENT_SECRET'],
        })
    
    def _validate_payment(self, amount):
        if amount <= 0:
            raise PaymentValidationError(
                "Le montant du paiement doit être supérieur à 0",
                code='invalid_amount'
            )
    
    
    def create_payment(self,amount,description,return_url,cancel_url):
        try:
            self._validate_payment(amount)
            
            payment = paypalrestsdk.Payment({
                'intent': 'sale',
                'payer': {
                    'payment_method': 'paypal',
                },
                'transactions': [{
                    'amount': {
                        'total': str(amount),
                        'currency': settings.PAYPAL_CONFIG['PAYPAL_CURRENCY'],
                    },
                    'description': description,
                }],
                'redirect_urls': {
                    'return_url':  settings.PAYPAL_CONFIG['PAYPAL_SUCCESS_URL'],    
                    'cancel_url':  settings.PAYPAL_CONFIG['PAYPAL_CANCEL_URL'],
                },
            })
            
            if not payment.create():
                raise PaymentProcessError(
                    f"Erreur lors de la création du paiement PayPal: {payment.error}",
                    code='payment_creation_failed'
                )
            
            db_payment = Payment.objects.create(
                payment_id=payment.id,
                amount=amount,
                currency=settings.PAYPAL_CONFIG['PAYPAL_CURRENCY'],
                description=description
            )
            
            return {
                'payment_id': db_payment.payment_id,
                'approval_url': next(link.href for link in payment.links if link.rel == 'approval_url')
            }
        except PaymentValidationError as e:
            logging.error(f"Erreur de validation du paiement: {str(e)}")
        
        except Exception as e:
            logging.error(f"Erreur lors de la création du paiement: {str(e)}")
            raise PaymentProcessError("Erreur lors de la création du paiement")
        
    
    
    def execute_payment(self, payment_id,payer_id):
        try:
            payment = paypalrestsdk.Payment.find(payment_id)
            if not payment.execute({"payer_id": payer_id}):
                raise PaymentProcessError(
                    f"Erreur lors de l'exécution du paiement PayPal: {payment.error}",
                    code='payment_execution_failed'
                )
            
            db_payment = Payment.objects.get(payment_id=payment_id)
            db_payment.status = Payment.Status.COMPLETED
            db_payment.payer_id = payer_id
            db_payment.payer_email = payment.payer.payer_info.email
            db_payment.save()
            
            return db_payment
        except Payment.DoesNotExist:
            raise PaymentError("Paiement introuvable")
        
        
        except Exception as e:
            logging.error(f"Erreur lors de l'exécution du paiement: {str(e)}")
            raise PaymentProcessError("Erreur lors de l'exécution du paiement")
    
    
    def refund_payment(self,payment_id,amount=None,reason=None):
        try:
            db_payment = Payment.objects.get(payment_id=payment_id)
            if db_payment.status != Payment.Status.COMPLETED:
                raise RefundError("Impossible de rembourser un paiement non complété")
            
            paypal_payment = paypalrestsdk.Payment.find(payment_id=payment_id)
            sale_id = paypal_payment.transactions[0].related_resources[0].sale.id
            sale = paypalrestsdk.Sale.find(sale_id)
            
            refund_data = {
                'amount': {
                    'total': str(amount) if amount else str(db_payment.amount),
                    'currency': db_payment.currency
                }
            }
            
            refund = sale.refund(refund_data)
            if not refund.success():
                raise RefundError(
                    f"Erreur lors du remboursement du paiement PayPal: {refund.error}",
                    code='refund_failed'
                )
            
            refund_record = PaymentRefund.objects.create(
                payment=db_payment,
                amount=refund.amount.total,
                reason=reason
            )
            
            payment.status = Payment.Status.REFUNDED
            payment.save()
            return refund_record
        
        
        except Payment.DoesNotExist:
            raise RefundError("Paiement introuvable")
        except Exception as e:
            logging.error(f"Erreur lors du remboursement du paiement: {str(e)}")
            raise RefundError("Erreur lors du remboursement du paiement")