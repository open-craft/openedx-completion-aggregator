# -*- coding: utf-8 -*-
"""
URLs for completion_aggregator.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from django.urls import include, re_path

from . import views

urlpatterns = [
    re_path(r'^v1/', include('completion_aggregator.api.v1.urls', namespace='completion_api_v1')),
    re_path(r'^v0/', include('completion_aggregator.api.v0.urls', namespace='completion_api_v0')),
    re_path(
        r'^progress_bar/(?P<course_key>[\w.@+:-]+)/$',
        views.CompletionProgressBarView.as_view(),
        name="completion-progress-bar",
    ),
    re_path(
        r'^progress_bar/(?P<course_key>[\w.@+:-]+)/(?P<chapter_id>.+)/$',
        views.CompletionProgressBarView.as_view(),
        name="completion-progress-bar",
    ),
]
