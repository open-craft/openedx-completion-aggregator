# -*- coding: utf-8 -*-
"""
URLs for completion_aggregator.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from django.urls import include, re_path

urlpatterns = [
    re_path(r'^o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    re_path(r'', include('completion_aggregator.urls')),
]
