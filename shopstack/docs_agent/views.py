from dataclasses import asdict

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from docs_agent import orchestrator
from docs_agent.serializers import AskRequestSerializer


class AskView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'docs_agent'

    def post(self, request):
        serializer = AskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.validated_data['question']
        result = orchestrator.answer(question)
        payload = asdict(result)
        if result.status == 'blocked':
            return Response(payload, status=status.HTTP_403_FORBIDDEN)
        return Response(payload, status=status.HTTP_200_OK)
