from django.urls import path

from docs_agent.views import AskView


urlpatterns = [
    path('ask', AskView.as_view(), name='docs-agent-ask'),
]
