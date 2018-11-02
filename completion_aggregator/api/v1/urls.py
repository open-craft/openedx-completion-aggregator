"""
URLs for the completion API
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf.urls import url

from . import views

app_name = 'completion_aggregator'

urlpatterns = [
    url(r'^course/$', views.CompletionListView.as_view()),
    url(r'^course/(?P<course_key>.+)/$', views.CompletionDetailView.as_view()),
    url(r'^stats/(?P<course_key>.+)/$', views.CourseLevelCompletionStatsView.as_view()),
]
