# -*- coding: utf-8 -*-
"""
completion_aggregator Django application initialization.
"""

from __future__ import absolute_import, unicode_literals

from django.apps import AppConfig


class CompletionAggregatorAppConfig(AppConfig):
    """
    Configuration for the completion_aggregator Django application.
    """

    name = 'completion_aggregator'
    plugin_app = {
        'url_config': {
            'lms.djangoapp': {
                'namespace': 'completion_aggregator',
                'regex': r'^completion-aggregator/',
                'relative_path': 'urls',
            },
        },
        'settings_config': {
            'lms.djangoapp': {
                'aws': {'relative_path': 'settings.aws'},
                'common': {'relative_path': 'settings.common'},
            },
            'cms.djangoapp': {
                'aws': {'relative_path': 'settings.aws'},
                'common': {'relative_path': 'settings.common'},
            },
        },
    }

    def ready(self):
        """
        Load signal handlers when the app is ready.
        """
        # pylint: disable=import-outside-toplevel
        from . import signals
        signals.register()

        # pylint: disable=unused-import
        from . import transformers
        from .tasks import aggregation_tasks, handler_tasks
