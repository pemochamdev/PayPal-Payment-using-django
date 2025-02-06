import logging
import paypalrestsdk
from django.conf import settings
from decimal import Decimal
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
            
            payment_data = {
                'intent': 'sale',
                'payment_method': 'paypal',
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
            }
            logger.debug(f"PayPal payment data: {payment_data}")
            payment = paypalrestsdk.Payment(payment_data)
            if not payment.create():
                logger.error(f"Erreur création PayPal: {payment.error}")
                raise PaymentProcessError(
                    f"Erreur lors de la création du paiement PayPal: {payment.error}",
                    code='payment_creation_failed'
                )
            
            logger.info(f"Paiement PayPal créé: {payment.id}")
            logger.debug(f"Payment response: {payment}")
            
            db_payment = Payment.objects.create(
                payment_id=payment.id,
                amount=Decimal(str(amount)),
                currency=settings.PAYPAL_CONFIG['PAYPAL_CURRENCY'],
                description=description
            )
            
            # Trouver l'URL d'approbation
            approval_url = None
            for link in payment.links:
                logger.debug(f"Payment link: {link}")
                if link.rel == "approval_url":
                    approval_url = link.href
                    break

            if not approval_url:
                raise PaymentProcessError("URL d'approbation non trouvée")

            
            return {
                'id': str(db_payment.id),
                'payment_id': db_payment.id,
                'approval_url': next(link.href for link in payment.links if link.rel == 'approval_url')
            }
        except PaymentValidationError as e:
            logging.error(f"Erreur de validation du paiement: {str(e)}")
        
        except Exception as e:
            logging.error(f"Erreur lors de la création du paiement: {str(e)}")
            raise PaymentProcessError("Erreur lors de la création du paiement")
        
    
    
    def execute_payment(self, payment_id,payer_id):
        try:
            logger.info(f"Début exécution paiement - PayPal ID: {payment_id}, Payer ID: {payer_id}")
            
              # Vérifier les paramètres
            if not payment_id or not payer_id:
                raise PaymentValidationError("PayPal Payment ID et Payer ID sont requis")

            # Trouver le paiement dans notre base
            db_payment = Payment.objects.filter(payment_id=payment_id).first()
            if not db_payment:
                logger.error(f"Paiement non trouvé en base: {payment_id}")
                raise PaymentError("Paiement non trouvé")

            # Récupérer le paiement PayPal
            try:
                payment = paypalrestsdk.Payment.find(payment_id)
                logger.debug(f"Payment trouvé sur PayPal: {payment}")
            except Exception as e:
                logger.error(f"Erreur recherche paiement PayPal: {str(e)}")
                raise PaymentError("Paiement PayPal introuvable")

            # Exécuter le paiement
            execute_data = {"payer_id": payer_id}
            logger.debug(f"Executing payment with data: {execute_data}")
            
            if not payment.execute(execute_data):
                logger.error(f"Échec exécution: {payment.error}")
                db_payment.status = Payment.PaymentStatus.FAILED
                db_payment.error_message = str(payment.error)
                db_payment.save()
                raise PaymentProcessError(f"Échec de l'exécution: {payment.error}")

            
            
            try:
                payer_info = payment.payer.payer_info
                logger.debug(f"Payer info: {payer_info}")
                db_payment.status = Payment.Status.COMPLETED
                db_payment.payer_id = payer_id
                if hasattr(payer_info, 'email'):
                    db_payment.payer_email = payer_info.email
                db_payment.save()
                logger.info(f"Paiement exécuté avec succès: {payment_id}")
                
            except AttributeError as e:
                logger.error(f"Erreur lors de l'accès aux informations du payeur: {str(e)}")
                
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