"""
Migrate CourseModuleCompletion objects to BlockCompletion table.
"""

import logging
import time

from django.core.management.base import BaseCommand, CommandError

from ...tasks import aggregation_tasks

try:
    from progress.models import CourseModuleCompletion
    PROGRESS_IMPORTED = True
except ImportError:
    PROGRESS_IMPORTED = False


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
            '--start-index',
            help='Offset from which to start processing CourseModuleCompletions. (default: 0)',
            default=0,
            type=int,
        )
        parser.add_argument(
            '--stop-index',
            help='Offset at which to stop processing CourseModuleCompletions. (default: process all)',
            default=0,
            type=int,
        )
        parser.add_argument(
            '--delay-between-tasks',
            help='Amount of time to wait between submitting tasks in seconds.  (default: 0.0)',
            default=0.0,
            type=float,
        )
        parser.add_argument(
            '--ids',
            help='Migrate specific CourseModuleCompletion IDs',
        )

    def handle(self, *args, **options):
        if not PROGRESS_IMPORTED:
            raise CommandError("Unable to import progress models.  Aborting")
        self._configure_logging(options)
        task_options = self.get_task_options(options)

        if options['ids']:
            migrate_ids = [int(id_) for id_ in options['ids'].split(',')]
            migrate_ids.sort()
            for index in migrate_ids:
                aggregation_tasks.migrate_batch.apply_async(
                    kwargs={'start': index, 'stop': index + 1},
                    **task_options
                )
                time.sleep(options['delay_between_tasks'])
        else:
            cmc_max_id = CourseModuleCompletion.objects.all().order_by('-id')[:1][0].id
            cmc_min_id = CourseModuleCompletion.objects.all().order_by('id')[:1][0].id
            start = max(options['start_index'], cmc_min_id)
            stop = min(cmc_max_id + 1, options['stop_index'] or float('inf'))
            for index in range(start, stop, options['batch_size']):
                aggregation_tasks.migrate_batch.apply_async(
                    kwargs={'start': index, 'stop': min(stop, index + options['batch_size'])},
                    **task_options
                )
                time.sleep(options['delay_between_tasks'])

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
