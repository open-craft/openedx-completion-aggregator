"""
run_aggregator_cleanup management command.

Usage:

    ./manage.py run_aggregator_cleanup

Removes StaleAggregators that have been marked resolved.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from django.core.management.base import BaseCommand

from ...batch import perform_cleanup


class Command(BaseCommand):
    """
    run_aggregator_service management command.
    """

    def handle(self, *args, **options):
        """
        Run the aggregator service.
        """
        self.set_logging(options['verbosity'])
        perform_cleanup()

    def set_logging(self, verbosity):
        """
        Set the logging level depending on the desired vebosity
        """
        handler = logging.StreamHandler()
        root_logger = logging.getLogger('')
        root_logger.addHandler(handler)
        handler.setFormatter(logging.Formatter('%(levelname)s|%(message)s'))

        if verbosity == 1:
            logging.getLogger('completion_aggregator').setLevel(logging.WARNING)
        elif verbosity == 2:
            logging.getLogger('completion_aggregator').setLevel(logging.INFO)
        elif verbosity == 3:
            logging.getLogger().setLevel(logging.DEBUG)
            handler.setFormatter(logging.Formatter('%(name)s|%(asctime)s|%(levelname)s|%(message)s'))
