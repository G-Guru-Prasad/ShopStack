from django.urls import path

from doc_agent import views


urlpatterns = [
    path('ask/', views.AskAPIView.as_view(), name='doc-agent-ask'),
    path('conversations/', views.ConversationListView.as_view(),
         name='doc-agent-conversation-list'),
    path('conversations/<int:pk>/', views.ConversationDetailView.as_view(),
         name='doc-agent-conversation-detail'),
]
