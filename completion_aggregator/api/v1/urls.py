"""
URLs for the completion API
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from django.urls import re_path

from . import views

app_name = 'completion_aggregator'

urlpatterns = [
    re_path(r'^course/$', views.CompletionListView.as_view()),
    re_path(r'^course/(?P<course_key>.+)/$', views.CompletionDetailView.as_view()),
    re_path(r'^stats/(?P<course_key>.+)/$', views.CourseLevelCompletionStatsView.as_view()),
]
