from django.conf import settings

from docs_agent.types import ClaudeResponse


_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def _as_system_blocks(system):
    if isinstance(system, str):
        return [{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}]
    return system


def call_claude(*, model, system, messages, max_tokens, temperature=0):
    client = _get_client()
    resp = client.messages.create(
        model=model,
        system=_as_system_blocks(system),
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = ''
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            text += block.text
    usage = getattr(resp, 'usage', None)
    return ClaudeResponse(
        text=text,
        input_tokens=getattr(usage, 'input_tokens', 0) if usage else 0,
        output_tokens=getattr(usage, 'output_tokens', 0) if usage else 0,
        stop_reason=getattr(resp, 'stop_reason', '') or '',
    )
