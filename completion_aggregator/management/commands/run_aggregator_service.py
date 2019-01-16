"""
run_aggregator_service management command.

Usage:

    ./manage.py run_aggregator_service

Performs the actual aggregation.

For continuous aggregation, set a cron job to run this task periodically.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from django.core.management.base import BaseCommand

from ...batch import perform_aggregation


class Command(BaseCommand):
    """
    run_aggregator_service management command.
    """

    def add_arguments(self, parser):
        """
        Add command-line arguments
        """
        parser.add_argument(
            '--batch-size',
            help='Maximum number of StaleCompletions to process, per celery task. (default: 1000)',
            default=1000,
            type=int,
        )
        parser.add_argument(
            '--delay-between-batches',
            help='Amount of time to wait between processing batches in seconds.  (default: 0.0)',
            default=0.0,
            type=float,
        )
        parser.add_argument(
            '--limit',
            help='',
            default=500000,
            type=int,
        )
        parser.add_argument(
            '--routing-key',
            dest='routing_key',
            help='Celery routing key to use.',
        )

    def handle(self, *args, **options):
        """
        Run the aggregator service.
        """
        self.set_logging(options['verbosity'])
        perform_aggregation(
            batch_size=options['batch_size'],
            delay=options['delay_between_batches'],
            limit=options['limit'],
            routing_key=options.get('routing_key'),
        )

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
