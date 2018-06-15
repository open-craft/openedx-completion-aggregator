# -*- coding: utf-8 -*-
"""
URLs for completion_aggregator.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf.urls import include, url
from django.views.generic import TemplateView

urlpatterns = [
    url(r'^v1/', include('completion_aggregator.api.v1.urls', namespace='completion_api_v1')),
    url(r'^v0/', include('completion_aggregator.api.v0.urls', namespace='completion_api_v0')),
    url(r'^$', TemplateView.as_view(template_name="completion_aggregator/base.html")),
]
