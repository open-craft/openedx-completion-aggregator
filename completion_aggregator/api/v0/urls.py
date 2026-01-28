"""
URLs for the completion API
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from django.urls import path

from . import views

app_name = 'completion_aggregator'

urlpatterns = [
    path(
        'course/<path:course_key>/blocks/<path:block_key>/',
        views.CompletionBlockUpdateView.as_view(),
        name='blockcompletion-update'
    ),
    path('course/', views.CompletionListView.as_view(), name='aggregator-list'),
    path('course/<path:course_key>/', views.CompletionDetailView.as_view(), name='aggregator-detail'),
]
