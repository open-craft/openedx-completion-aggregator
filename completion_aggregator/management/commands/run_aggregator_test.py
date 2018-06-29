# -*- coding: utf-8 -*-
"""
Performance tests for completion aggregator.
"""

from __future__ import absolute_import, division, unicode_literals

import cProfile
import datetime
import random
from timeit import default_timer

import pytz

from django.core.management.base import BaseCommand, CommandError
from django.db import connections, reset_queries

from completion.models import BlockCompletion

from ...models import Aggregator
from ...signals import course_published_handler, item_deleted_handler

try:
    import numpy
    from student.tests.factories import UserFactory, CourseEnrollmentFactory
    from xmodule.modulestore import ModuleStoreEnum
    from xmodule.modulestore.django import SignalHandler, modulestore
except ImportError:
    pass


class Command(BaseCommand):
    """
    Run performance tests for completion aggregator.


    CELERY_ALWAYS_EAGER = True must be set so that the tasks are executed in the thread.
    The SQL queries are only logged by Django if DEBUG = True.
    cProfile adds around 25% overhead for this code.
    """

    help = "Run performance tests for completion aggregator."

    def add_arguments(self, parser):
        parser.add_argument(
            'test',
            help='Test to run.'
        )
        parser.add_argument(
            '--course-breadth',
            nargs=4,
            type=int,
            default=(3, 3, 3, 3),
            help='Number of blocks at the first four levels in course. Default is 3 3 3 3.'
        )
        parser.add_argument(
            '--learners',
            type=int,
            default=2,
            help='Number of learners. Default is 2.'
        )
        parser.add_argument(
            '--completions',
            type=int,
            default=30,
            help='Number of completions to perform. Default is 30.'
        )

    def handle(self, *args, **options):
        test = options.get('test')

        if not hasattr(self, test):
            raise CommandError('%s not found.' % test)

        self.setUp(**options)
        getattr(self, test)()

    def setUp(self, **options):
        """ Set up the course and users. """

        self.course_breadth = options['course_breadth']
        self.learners_count = options['learners']
        self.completions_count = options['completions']

        self.executed_queries = []
        self.timer = default_timer
        self.store = modulestore()
        self.blocks = []

        with self.store.default_store(ModuleStoreEnum.Type.split):
            fields = {'display_name': 'Course', 'start': datetime.datetime(2015, 1, 1, 1, tzinfo=pytz.utc)}
            self.course = modulestore().create_course(
                'completion',
                '101',
                str(random.randint(1, 9999)),
                ModuleStoreEnum.UserID.test,
                fields=fields
            )

            with self.store.branch_setting(ModuleStoreEnum.Branch.draft_preferred):
                with self.store.bulk_operations(self.course.id):
                    for __ in range(self.course_breadth[0]):
                        chapter = self._create_block(parent=self.course, category='chapter')
                        for __ in range(self.course_breadth[1]):
                            sequence = self._create_block(parent=chapter, category='sequential')
                            for __ in range(self.course_breadth[2]):
                                vertical = self._create_block(parent=sequence, category='vertical')
                                self.blocks += [
                                    self._create_block(
                                        parent=vertical, category='html'
                                    ) for __ in range(self.course_breadth[3])
                                ]
                                self.store.publish(vertical.location, ModuleStoreEnum.UserID.test)

            self.course = self.store.get_course(self.course.id)

        self.users = [UserFactory.create() for __ in range(self.learners_count)]
        for user in self.users:
            CourseEnrollmentFactory(user=user, course_id=self.course.id)

    def _create_block(self, parent, category):
        fields = {'display_name': category, 'start': datetime.datetime(2015, 1, 1, 1, tzinfo=pytz.utc)}
        return self.store.create_child(ModuleStoreEnum.UserID.test, parent.location, category, fields=fields)

    def _print_results_header(self, test_name, time_taken=None):
        """ Print header. """
        self.stdout.write("\n")
        self.stdout.write("----- Completion Aggregator Performance Test Results -----")
        self.stdout.write("Test: {}".format(test_name))
        self.stdout.write("Course: {}".format(self.course.id))

        chapter_count = self.course_breadth[0]
        sequential_count = chapter_count * self.course_breadth[1]
        vertical_count = sequential_count * self.course_breadth[2]

        self.stdout.write("Course Breadth: {} | Chapters: {} | Sequentials: {} | Verticals: {}".format(
            self.course_breadth, chapter_count, sequential_count, vertical_count
        ))
        self.stdout.write("Learners: {}".format(self.learners_count))
        self.stdout.write("Completions: {}".format(self.completions_count))

        query_data = {}
        query_total_time = 0
        for query in self.executed_queries:
            query_type = query['sql'].split()[0]
            query_data.setdefault(query_type, {'count': 0, 'times': []})
            query_data[query_type]['count'] = query_data[query_type]['count'] + 1
            query_data[query_type]['times'].append(float(query['time']))
            query_total_time += float(query['time'])

        self.stdout.write(
            "SQL Queries | All Count: {} | Time: {}".format(len(self.executed_queries), query_total_time)
        )
        for query_type, data in query_data.items():
            self.stdout.write("SQL Queries | {} Count: {} Time: {} Percentiles: {}".format(
                query_type, data['count'], sum(data['times']), self._get_percentiles(data['times'])
            ))

        if time_taken:
            self.stdout.write("Total Time: {:.3f}s".format(time_taken))

    def _print_results_footer(self):
        """ Print footer. """
        self.stdout.write("----------------------------------------------------------")

    def _get_percentiles(self, items):
        return " | ".join(
            ["{}%: {:.3f}s".format(p, numpy.percentile(items, p)) for p in [
                50, 66, 75, 80, 90, 95, 98, 99, 100]
             ]
        )

    def _copy_executed_queries(self):
        self.executed_queries = []
        for c in connections.all():
            self.executed_queries.extend(c.queries_log)

    def _complete_blocks_for_users(self, blocks, users):
        for user in users:
            for block in blocks:
                BlockCompletion.objects.submit_completion(
                    user=user,
                    course_key=self.course.id,
                    block_key=block.location,
                    completion=1.0
                )

    def _complete_random_blocks_for_users(self, blocks, users):
        completions_left = self.completions_count
        max_completions_per_user = 2 * (self.completions_count // len(users))
        for user in users:
            # For each user pick a random number of blocks to complete.
            number_of_completions_for_user = min(random.choice(range(max_completions_per_user)), completions_left)
            completions_left -= number_of_completions_for_user
            if completions_left <= 0:
                return
            blocks_to_complete = random.sample(blocks, number_of_completions_for_user)
            self._complete_blocks_for_users(blocks_to_complete, [user])

    def _assert_vertical_completion_for_all_users(self, vertical, expected_completion):
        for user in self.users:
            vertical_completion = Aggregator.objects.get(
                user=user, course_key=self.course.id, block_key=vertical.location
            ).percent
            assert abs(vertical_completion - expected_completion) < 0.01

    def _time_handler(self, handler, **kwargs):
        """ Time how long it takes to run handler. """
        timer_start = self.timer()
        handler(**kwargs)
        timer_end = self.timer()
        return timer_end - timer_start

    def test_course_published_handler_when_block_is_added(self):

        # Other listeners are connected so we time the handler alone later.
        SignalHandler.course_published.disconnect(course_published_handler)

        self.stdout.write("\n--- Complete random blocks ---\n")
        self._complete_random_blocks_for_users(self.blocks, self.users)

        vertical = self.course.get_children()[-1].get_children()[-1].get_children()[-1]
        self.stdout.write("\n--- Complete blocks in last vertical ---\n")
        self._complete_blocks_for_users(vertical.get_children(), self.users)
        self._assert_vertical_completion_for_all_users(vertical, 1.0)

        self.stdout.write("\n--- Call course_published_handler to seed Aggregator table. ---\n")
        pr = cProfile.Profile()
        pr.enable()
        self._time_handler(course_published_handler, course_key=self.course.id)
        pr.disable()
        pr.print_stats(sort='cumtime')

        self.stdout.write("\n--- Add block to last vertical ---\n")
        with self.store.branch_setting(ModuleStoreEnum.Branch.draft_preferred, self.course.id):
            with self.store.bulk_operations(self.course.id):
                self._create_block(parent=vertical, category='html')
                self.store.publish(vertical.location, ModuleStoreEnum.UserID.test)

        self.stdout.write("\n--- Call course_published_handler again ---\n")
        reset_queries()
        pr = cProfile.Profile()
        pr.enable()
        time_taken = self._time_handler(course_published_handler, course_key=self.course.id)
        pr.disable()
        pr.print_stats(sort='cumtime')
        self._copy_executed_queries()

        self._print_results_header("test_course_published_handler_when_block_is_added", time_taken=time_taken)
        self._assert_vertical_completion_for_all_users(
            vertical, self.course_breadth[3] / (self.course_breadth[3] + 1.0)
        )
        self._print_results_footer()

    def test_item_deleted_handler_when_block_is_deleted(self):

        # Other listeners are connected so we time the handler alone later.
        SignalHandler.course_published.disconnect(item_deleted_handler)

        self.stdout.write("\n--- Complete random blocks excluding those in the last vertical ---\n")
        self._complete_random_blocks_for_users(self.blocks[:(-1 * self.course_breadth[3])], self.users)

        vertical = self.course.get_children()[-1].get_children()[-1].get_children()[-1]
        self.stdout.write("\n--- Complete blocks in last vertical ---\n")
        self._complete_blocks_for_users(vertical.get_children()[1:], self.users)
        self._assert_vertical_completion_for_all_users(
            vertical, (self.course_breadth[3] - 1.0) / self.course_breadth[3]
        )

        self.stdout.write("\n--- Call course_published_handler to seed Aggregator table. ---\n")
        pr = cProfile.Profile()
        pr.enable()
        self._time_handler(course_published_handler, course_key=self.course.id)
        pr.disable()
        pr.print_stats(sort='cumtime')

        self.stdout.write("\n--- Remove block from last vertical ---\n")
        block = vertical.get_children()[0]
        with self.store.branch_setting(ModuleStoreEnum.Branch.draft_preferred, self.course.id):
            self.store.delete_item(block.location, ModuleStoreEnum.UserID.test)

        self.stdout.write("\n--- Call course_published_handler again ---\n")
        reset_queries()
        pr = cProfile.Profile()
        pr.enable()
        time_taken = self._time_handler(item_deleted_handler, usage_key=block.location, user_id=None)
        pr.disable()
        pr.print_stats(sort='cumtime')
        self._copy_executed_queries()

        self._print_results_header("test_item_deleted_handler_when_block_is_deleted", time_taken=time_taken)
        self._assert_vertical_completion_for_all_users(vertical, 1.0)
        self._print_results_footer()

    def test_individual_block_completions(self):

        times_taken = []

        for user in self.users:
            user.next_block_index_to_complete = 0

        users = list(self.users)

        self.stdout.write("\n--- Call course_published_handler to seed Aggregator table. ---\n")
        self._time_handler(course_published_handler, course_key=self.course.id)

        self.stdout.write("\n--- Do block completions ---\n")
        reset_queries()
        pr = cProfile.Profile()
        pr.enable()

        for __ in range(self.completions_count):
            random_user = random.choice(users)
            next_block = self.blocks[random_user.next_block_index_to_complete]
            random_user.next_block_index_to_complete += 1
            if random_user.next_block_index_to_complete >= len(self.blocks):
                users.remove(random_user)

            timer_start = self.timer()
            self._complete_blocks_for_users([next_block], [random_user])
            timer_end = self.timer()
            elapsed_milliseconds = (timer_end - timer_start)
            times_taken.append(elapsed_milliseconds)

        pr.disable()
        pr.print_stats(sort='cumtime')
        self._copy_executed_queries()

        for user in self.users:
            expected_verticals_completed = user.next_block_index_to_complete // self.course_breadth[3]
            verticals_completed = Aggregator.objects.filter(
                user=user, course_key=self.course.id, aggregation_name='vertical', percent=1.0
            ).count()
            assert expected_verticals_completed == verticals_completed

        time_sum = numpy.sum(times_taken)
        time_average = (time_sum / self.completions_count)

        self._print_results_header("test_individual_block_completions", time_taken=time_sum)
        self.stdout.write("Average Time: {:.3f}s".format(time_average))
        self.stdout.write("Time Percentiles: {}".format(self._get_percentiles(times_taken)))
        self._print_results_footer()
