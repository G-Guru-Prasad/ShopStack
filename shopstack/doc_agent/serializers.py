from rest_framework import serializers

from doc_agent.models import Conversation, Message


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(min_length=1, max_length=4000)
    conversation_id = serializers.IntegerField(required=False, allow_null=True)


class CitationSerializer(serializers.Serializer):
    chunk_id = serializers.IntegerField()
    source_path = serializers.CharField()
    start_line = serializers.IntegerField()
    end_line = serializers.IntegerField()
    snippet = serializers.CharField()


class AskResponseSerializer(serializers.Serializer):
    message_id = serializers.IntegerField()
    conversation_id = serializers.IntegerField()
    answer = serializers.CharField()
    citations = CitationSerializer(many=True)
    not_fully_verified = serializers.BooleanField()


class ConversationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ['id', 'title', 'created_at', 'updated_at']


class MessageSerializer(serializers.ModelSerializer):
    cited_chunks = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'role', 'content', 'cited_chunks',
            'not_fully_verified', 'created_at',
        ]

    def get_cited_chunks(self, obj):
        return [
            {
                'chunk_id': chunk.id,
                'source_path': chunk.document.source_path,
                'snippet': chunk.text[:200],
            }
            for chunk in obj.cited_chunks.all()
        ]


class ConversationDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ['id', 'title', 'created_at', 'updated_at', 'messages']
