"""
URLs for the completion API
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from django.urls import path

from . import views

app_name = 'completion_aggregator'

urlpatterns = [
    path('course/', views.CompletionListView.as_view()),
    path('course/<path:course_key>/', views.CompletionDetailView.as_view()),
    path('stats/<path:course_key>/', views.CourseLevelCompletionStatsView.as_view()),
]
