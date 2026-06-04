import logging
from dataclasses import asdict

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from doc_agent.models import Conversation, DocumentChunk
from doc_agent.orchestrator import Orchestrator
from doc_agent.serializers import (
    AskResponseSerializer,
    AskSerializer,
    ConversationDetailSerializer,
    ConversationListSerializer,
)


logger = logging.getLogger(__name__)
LLM_ERROR_MESSAGE = (
    "I couldn't process that question — the documentation agent is "
    'temporarily unavailable. Please try again.'
)


class AskAPIView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            response = Orchestrator().run(
                user=request.user,
                question=serializer.validated_data['question'],
                conversation_id=serializer.validated_data.get('conversation_id'),
            )
        except ValueError:
            logger.exception('LLM returned malformed response')
            return Response(
                {'detail': LLM_ERROR_MESSAGE},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        payload = {
            'message_id': response.message_id,
            'conversation_id': response.conversation_id,
            'answer': response.answer,
            'citations': [asdict(c) for c in response.citations],
            'not_fully_verified': response.not_fully_verified,
        }
        return Response(
            AskResponseSerializer(payload).data,
            status=status.HTTP_200_OK,
        )


class ConversationListView(generics.ListAPIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationListSerializer

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user)


class ConversationDetailView(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationDetailSerializer

    def get_queryset(self):
        return Conversation.objects.filter(
            user=self.request.user,
        ).prefetch_related(
            Prefetch(
                'messages__cited_chunks',
                queryset=DocumentChunk.objects.select_related('document'),
            ),
        )


@method_decorator(login_required, name='dispatch')
@method_decorator(ensure_csrf_cookie, name='dispatch')
class ChatPageView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        conversations = Conversation.objects.filter(user=request.user)
        return render(request, 'doc_agent/chat.html', {
            'conversations': conversations,
        })
