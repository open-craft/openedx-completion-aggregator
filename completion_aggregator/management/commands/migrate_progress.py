"""
Migrate CourseModuleCompletion objects to BlockCompletion table.
"""

import logging

from django.core.management.base import BaseCommand

from ...tasks import aggregation_tasks

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Migrate CourseModuleCompletion objects to BlockCompletion table.
    """
    def add_arguments(self, parser):
        """
        Entry point for subclassed commands to add custom arguments.
        """
        parser.add_argument(
            '--routing-key',
            dest='routing_key',
            help='Celery routing key to use.',
        )
        parser.add_argument(
            '--batch-size',
            help='Maximum number of CourseModuleCompletions to migrate, per celery task. (default: 10000)',
            default=10000,
            type=int,
        )
        parser.add_argument(
            '--delay-between-tasks',
            help='Amount of time to wait between submitting tasks in seconds.  (default: 0.0)',
            default=0.0,
            type=float,
        )

    def handle(self, *args, **options):
        self._configure_logging(options)
        task_options = self.get_task_options(options)

        aggregation_tasks.migrate_batch.apply_async(
            kwargs={
                'batch_size': options['batch_size'],
                'delay_between_tasks': options['delay_between_tasks'],
            },
            **task_options
        )

    def get_task_options(self, options):
        """
        Return task options for generated celery tasks.

        Currently, this adds a routing key, if provided.
        """
        opts = {}
        if options.get('routing_key'):
            opts['routing_key'] = options['routing_key']
        return opts

    def _configure_logging(self, options):
        """
        Sets logging levels for this module and the block structure
        cache module, based on the given the options.
        """
        handler = logging.StreamHandler()
        root_logger = logging.getLogger('')
        root_logger.addHandler(handler)
        handler.setFormatter(logging.Formatter('%(levelname)s|%(message)s'))

        if options.get('verbosity') == 0:
            log_level = logging.WARNING
        elif options.get('verbosity') >= 1:
            log_level = logging.INFO
        log.setLevel(log_level)
