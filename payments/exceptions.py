class PaymentError(Exception):
    def __init__(self, message, code=None, params=None):
        super().__init__(message)
        self.code = code
        self.params = params or {}

class PaymentValidationError(PaymentError):
    pass

class PaymentProcessError(PaymentError):
    pass

class RefundError(PaymentError):
    pass