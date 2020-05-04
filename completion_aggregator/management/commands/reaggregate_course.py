"""
run_aggregator_service management command.

Usage:

    ./manage.py run_aggregator_service

Performs the actual aggregation.

For continuous aggregation, set a cron job to run this task periodically.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging

import six
from opaque_keys.edx.keys import CourseKey

from django.core.management.base import BaseCommand

from completion.models import BlockCompletion

from ... import compat
from ...models import StaleCompletion


class Command(BaseCommand):
    """
    run_aggregator_service management command.
    """

    def add_arguments(self, parser):
        """
        Add command-line arguments
        """
        parser.add_argument(
            '-a', '--all',
            help='Reaggregate all courses',
            action='store_true',
        )
        parser.add_argument(
            'course_keys',
            help='CourseKeys of courses that need reaggregation',
            nargs='*',
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

        if options['all']:
            options['course_keys'] = BlockCompletion.objects.values_list('course_key').distinct()
        CourseEnrollment = compat.course_enrollment_model()  # pylint: disable=invalid-name
        for course in options['course_keys']:
            if isinstance(course, six.string_types):
                course = CourseKey.from_string(course)
            all_enrollments = CourseEnrollment.objects.filter(course=course).select_related('user')
            StaleCompletion.objects.bulk_create(
                (
                    StaleCompletion(
                        course_key=enrollment.course_id,
                        username=enrollment.user,
                        block_key=None,
                        force=True,
                        resolved=False
                    )
                    for enrollment in all_enrollments
                ),
                batch_size=10000,
            )

        return

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
