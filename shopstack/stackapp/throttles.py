from rest_framework.throttling import ScopedRateThrottle


class ForgotPasswordThrottle(ScopedRateThrottle):
    scope = 'forgot_password'
