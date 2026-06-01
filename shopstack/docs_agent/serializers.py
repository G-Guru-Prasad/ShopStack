from rest_framework import serializers


class AskRequestSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)
