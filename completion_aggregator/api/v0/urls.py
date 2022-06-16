"""
URLs for the completion API
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from django.urls import re_path

from . import views

app_name = 'completion_aggregator'

urlpatterns = [
    re_path(
        r'^course/(?P<course_key>.+)/blocks/(?P<block_key>.+)/$',
        views.CompletionBlockUpdateView.as_view(),
        name='blockcompletion-update'
    ),
    re_path(r'^course/$', views.CompletionListView.as_view(), name='aggregator-list'),
    re_path(r'^course/(?P<course_key>.+)/$', views.CompletionDetailView.as_view(), name='aggregator-detail'),
]
