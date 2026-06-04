"""Thin wrapper around the Anthropic SDK.

This module is the single import site for `anthropic` so tests can stub one
attribute (`_get_client`) rather than mocking the SDK everywhere.
"""
import json

from django.conf import settings


_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def complete_json(system_prompt, user_prompt, max_tokens=1024):
    """Send a single-turn message and parse the response as JSON.

    Returns the parsed dict. Raises ValueError on parse failure.
    """
    client = _get_client()
    resp = client.messages.create(
        model=settings.DOC_AGENT_CHAT_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{'role': 'user', 'content': user_prompt}],
    )
    text = ''.join(block.text for block in resp.content if hasattr(block, 'text'))
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'LLM did not return valid JSON: {text!r}') from exc
