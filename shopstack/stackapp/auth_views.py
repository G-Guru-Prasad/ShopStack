import random
import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView as BaseTokenRefreshView

from stackapp.auth_serializers import (
    ChangePasswordSerializer,
    ForgotPasswordConfirmSerializer,
    ForgotPasswordRequestSerializer,
    ForgotPasswordVerifySerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
)
from stackapp.models import PasswordResetOTP, TenantUser
from stackapp.throttles import ForgotPasswordThrottle
from stackapp.utils import ThreadVaribales


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': {'id': user.id, 'username': user.username, 'email': user.email},
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    throttle_scope = 'auth'


class CustomTokenRefreshView(BaseTokenRefreshView):
    permission_classes = [AllowAny]


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'detail': 'Refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                {'detail': 'Invalid or already blacklisted token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'detail': 'Successfully logged out.'}, status=status.HTTP_200_OK) 


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        return Response({'detail': 'Password changed successfully.'}, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        try:
            user = User.objects.get(email=email)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            # In production: send email with reset link containing uid + token.
            # Returned here for development/testing only.
            _ = f"/api/auth/password-reset/confirm/?uid={uid}&token={token}"
        except User.DoesNotExist:
            pass
        # Always return success to prevent email enumeration
        return Response(
            {'detail': 'If that email address exists, a password reset link has been sent.'},
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response({
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'first_name': u.first_name,
            'last_name': u.last_name,
        })


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            uid = force_str(urlsafe_base64_decode(
                serializer.validated_data['uid']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {'detail': 'Invalid reset link.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not default_token_generator.check_token(user, serializer.validated_data['token']):
            return Response(
                {'detail': 'Invalid or expired token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({'detail': 'Password has been reset successfully.'}, status=status.HTTP_200_OK)


class ForgotPasswordRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ForgotPasswordThrottle]

    def post(self, request):
        serializer = ForgotPasswordRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        tenant_id = ThreadVaribales().get_current_tenant_id()

        try:
            tenant_user = TenantUser.objects.select_related('user').get(
                tenant_id=tenant_id,
                user__email=email,
                is_active=True,
            )
            user = tenant_user.user

            PasswordResetOTP.objects.filter(
                user=user, tenant_id=tenant_id, is_used=False,
            ).update(is_used=True)

            otp_value = f"{random.SystemRandom().randint(0, 999999):06d}"
            expires_at = timezone.now() + timedelta(minutes=10)

            PasswordResetOTP.objects.create(
                user=user,
                tenant_id=tenant_id,
                otp=otp_value,
                expires_at=expires_at,
            )

            send_mail(
                subject='Your ShopStack password reset code',
                message=f'Your OTP is: {otp_value}\nIt expires in 10 minutes.',
                from_email='guruprasad1704@gmail.com',
                recipient_list=[email],
                fail_silently=True,
            )
        except TenantUser.DoesNotExist:
            pass

        return Response(
            {'detail': 'If that email address is registered, an OTP has been sent.'},
            status=status.HTTP_200_OK,
        )


class ForgotPasswordVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ForgotPasswordThrottle]

    def post(self, request):
        serializer = ForgotPasswordVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        otp_input = serializer.validated_data['otp']
        tenant_id = ThreadVaribales().get_current_tenant_id()

        try:
            tenant_user = TenantUser.objects.select_related('user').get(
                tenant_id=tenant_id,
                user__email=email,
                is_active=True,
            )
            user = tenant_user.user
        except TenantUser.DoesNotExist:
            return Response(
                {'detail': 'Invalid email or OTP.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            otp_record = PasswordResetOTP.objects.filter(
                user=user,
                tenant_id=tenant_id,
                is_used=False,
            ).latest('created_at')
        except PasswordResetOTP.DoesNotExist:
            return Response(
                {'detail': 'Invalid email or OTP.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp_record.attempt_count >= 3:
            return Response(
                {'detail': 'Too many incorrect attempts. Please request a new OTP.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp_record.is_expired():
            return Response(
                {'detail': 'OTP has expired. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp_record.otp != otp_input:
            otp_record.attempt_count += 1
            otp_record.save(update_fields=['attempt_count'])
            return Response(
                {'detail': 'Invalid email or OTP.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reset_token = uuid.uuid4().hex
        otp_record.is_otp_verified = True
        otp_record.reset_token = reset_token
        otp_record.save(update_fields=['is_otp_verified', 'reset_token'])

        return Response({'reset_token': reset_token}, status=status.HTTP_200_OK)


class ForgotPasswordConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ForgotPasswordThrottle]

    def post(self, request):
        serializer = ForgotPasswordConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reset_token = serializer.validated_data['reset_token']
        new_password = serializer.validated_data['new_password']

        try:
            otp_record = PasswordResetOTP.objects.select_related('user').get(
                reset_token=reset_token,
                is_otp_verified=True,
                is_used=False,
            )
        except PasswordResetOTP.DoesNotExist:
            return Response(
                {'detail': 'Invalid or expired reset token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp_record.is_expired():
            return Response(
                {'detail': 'Reset token has expired. Please start over.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = otp_record.user
        user.set_password(new_password)
        user.save()

        otp_record.is_used = True
        otp_record.save(update_fields=['is_used'])

        return Response(
            {'detail': 'Password has been reset successfully.'},
            status=status.HTTP_200_OK,
        )
