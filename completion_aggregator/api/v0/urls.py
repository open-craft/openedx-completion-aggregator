"""
URLs for the completion API
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf.urls import url

from . import views

app_name = 'completion_aggregator'

urlpatterns = [
    url(
        r'^course/(?P<course_key>.+)/blocks/(?P<block_key>.+)/$',
        views.CompletionBlockUpdateView.as_view(),
        name='blockcompletion-update'
    ),
    url(r'^course/$', views.CompletionListView.as_view(), name='aggregator-list'),
    url(r'^course/(?P<course_key>.+)/$', views.CompletionDetailView.as_view(), name='aggregator-detail'),
]
