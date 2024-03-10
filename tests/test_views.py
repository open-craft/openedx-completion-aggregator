"""
Test serialization of completion data.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import json
from datetime import timedelta

import ddt
import six
from mock import PropertyMock, patch
from oauth2_provider import models as dot_models
from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from opaque_keys.edx.keys import CourseKey
from rest_framework.authentication import SessionAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.test import APIClient
from waffle.testutils import override_flag
from xblock.core import XBlock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from completion.models import BlockCompletion, BlockCompletionManager
from completion_aggregator import models
from completion_aggregator.api.v1.views import CompletionViewMixin
from completion_aggregator.core import AggregationUpdater
from completion_aggregator.utils import WAFFLE_AGGREGATE_STALE_FROM_SCRATCH
from test_utils.compat import StubCompat
from test_utils.test_blocks import StubCourse, StubHTML, StubSequential

User = get_user_model()

empty_compat = StubCompat([])


def _create_oauth2_token(user):
    """
    Create an OAuth2 Access Token for the specified user,
    to test OAuth2-based API authentication

    Returns the token as a string.
    """
    # Use django-oauth-toolkit (DOT) models to create the app and token:
    dot_app = dot_models.Application.objects.create(
        name='test app',
        user=User.objects.create(),
        client_type='confidential',
        authorization_grant_type='authorization-code',
        redirect_uris='http://none.none'
    )
    dot_access_token = dot_models.AccessToken.objects.create(
        user=user,
        application=dot_app,
        expires=timezone.now() + timedelta(weeks=1),
        scope='read',
        token='s3cur3t0k3n12345678901234567890'
    )
    return dot_access_token.token


class CompletionAPITestMixin:
    """
    Common utility functions for completion tests
    """

    @property
    def course_enrollment_model(self):
        return StubCompat([]).course_enrollment_model()

    def patch_object(self, obj, method, **kwargs):
        """
        Patch an object for the lifetime of the given test.
        """
        patcher = patch.object(obj, method, **kwargs)
        patcher.start()

        self.addCleanup(patcher.__exit__, None, None, None)
        return patcher

    def mark_completions(self):
        """
        Create completion data to test against.
        """
        BlockCompletion.objects.create(
            user=self.test_user,
            context_key=self.course_key,
            block_key=self.blocks[3],
            block_type='html',
            completion=1.0,
        )
        models.StaleCompletion.objects.update(resolved=True)
        models.Aggregator.objects.submit_completion(
            user=self.test_user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key(block_type='sequential', block_id='course-sequence1'),
            aggregation_name='sequential',
            earned=1.0,
            possible=5.0,
            last_modified=timezone.now(),
        )

        models.Aggregator.objects.submit_completion(
            user=self.test_user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key(block_type='course', block_id='course'),
            aggregation_name='course',
            earned=1.0,
            possible=8.0,
            last_modified=timezone.now(),
        )

    def create_enrollment(self, user, course_id):
        """
        create a CourseEnrollment.
        """
        return self.course_enrollment_model.objects.create(
            user=user,
            course_id=course_id,
        )

    def create_enrolled_users(self, count):
        """
        Create 'count' number of enrolled users.
        """
        users = []
        for user_id in range(count):
            username = f'user{user_id}'
            user = User.objects.create(username=username)
            users.append(user)
            self.create_enrollment(
                user=user,
                course_id=self.course_key,
            )
        return users

    def create_course_completion_data(self, user, earned, possible):
        """
        Create course-level completion data.
        """
        models.Aggregator.objects.submit_completion(
            user=user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key(block_type='course', block_id='course'),
            aggregation_name='course',
            earned=earned,
            possible=possible,
            last_modified=timezone.now()
        )


@ddt.ddt
class CompletionViewTestCase(CompletionAPITestMixin, TestCase):
    """
    Test that the CompletionView renders completion data properly.
    """

    course_key = CourseKey.from_string('edX/toy/2012_Fall')
    other_org_course_key = CourseKey.from_string('otherOrg/toy/2012_Fall')
    list_url = '/v{}/course/'
    detail_url_fmt = '/v{}/course/{}/'
    course_stat_url_fmt = '/v1/stats/{}/'
    course_enrollment_model = StubCompat([]).course_enrollment_model()

    def setUp(self):
        super().setUp()
        self.test_user = User.objects.create(username='test_user')
        self.staff_user = User.objects.create(username='staff', is_staff=True)
        self.test_enrollment = self.create_enrollment(
            user=self.test_user,
            course_id=self.course_key,
        )
        self.blocks = [
            self.course_key.make_usage_key('course', 'course'),
            self.course_key.make_usage_key('sequential', 'course-sequence1'),
            self.course_key.make_usage_key('sequential', 'course-sequence2'),
            self.course_key.make_usage_key('html', 'course-sequence1-html1'),
            self.course_key.make_usage_key('html', 'course-sequence1-html2'),
            self.course_key.make_usage_key('html', 'course-sequence1-html3'),
            self.course_key.make_usage_key('html', 'course-sequence1-html4'),
            self.course_key.make_usage_key('html', 'course-sequence1-html5'),
            self.course_key.make_usage_key('html', 'course-sequence2-html6'),
            self.course_key.make_usage_key('html', 'course-sequence2-html7'),
            self.course_key.make_usage_key('html', 'course-sequence2-html8'),
            self.course_key.make_usage_key('html', 'course-optional-sequence2-html9'),
        ]
        compat = StubCompat(self.blocks)
        for compat_import in (
                'completion_aggregator.api.common.compat',
                'completion_aggregator.serializers.compat',
                'completion_aggregator.core.compat',
        ):
            patcher = patch(compat_import, compat)
            patcher.start()
            self.addCleanup(patcher.__exit__, None, None, None)

        self.patch_object(
            CompletionViewMixin,
            'get_authenticators',
            return_value=[OAuth2Authentication(), SessionAuthentication()]
        )
        self.patch_object(
            CompletionViewMixin,
            'pagination_class',
            new_callable=PropertyMock,
            return_value=PageNumberPagination
        )
        self.mark_completions()
        self.client = APIClient()
        self.client.force_authenticate(user=self.test_user)

    def _get_expected_completion(self, version, earned=1.0, possible=8.0, percent=0.125, optional=False):
        """
        Return completion section based on version.
        """
        completion = {
            'earned': earned,
            'possible': possible,
            'percent': percent,
            'optional': optional,
        }
        if version == 0:
            completion['ratio'] = percent
        return completion

    def _get_expected_detail(self, version, values, count=1, previous=None, next_page=None):
        """
        Return base result for detail view based on version.
        """
        if version == 1:
            if isinstance(values, dict):
                values = [values]
            return {
                'count': count,
                'previous': previous,
                'next': next_page,
                'results': values
            }
        else:
            return values

    def assert_expected_list_view(self, version):
        """
        Ensures that the expected data is returned from the versioned list view.
        """
        response = self.client.get(self.get_list_url(version, username=self.test_user.username))
        self.assertEqual(response.status_code, 200)
        expected = {
            'count': 1,
            'previous': None,
            'next': None,
            'results': [
                {
                    'course_key': 'edX/toy/2012_Fall',
                    'completion': self._get_expected_completion(version),
                }
            ],
        }
        self.assertEqual(response.data, expected)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    @patch.object(AggregationUpdater, 'update')
    def test_list_view(self, version, mock_update):
        self.assert_expected_list_view(version)
        # no stale completions, so aggregations were not updated
        assert mock_update.call_count == 0

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_list_view_stale_completion(self, version):
        """
        Ensure that a stale completion causes the aggregations to be
        recalculated, but not updated in the db, and stale completion is not
        resolved.
        """
        models.StaleCompletion.objects.create(
            username=self.test_user.username,
            course_key=self.course_key,
            block_key=None,
            force=True,
            resolved=False,
        )
        assert models.StaleCompletion.objects.filter(resolved=False).count() == 1
        self.assert_expected_list_view(version)
        # assert mock_calculate.call_count == 1
        assert models.StaleCompletion.objects.filter(resolved=False).count() == 1

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_list_view_enrolled_no_progress(self, version):
        """
        Test that the completion API returns a record for each course the user is enrolled in,
        even if no progress records exist yet.
        """
        self.create_enrollment(
            user=self.test_user,
            course_id=self.other_org_course_key,
        )
        response = self.client.get(self.get_list_url(version, username=self.test_user.username))
        self.assertEqual(response.status_code, 200)
        expected = {
            'count': 2,
            'previous': None,
            'next': None,
            'results': [
                {
                    'course_key': 'edX/toy/2012_Fall',
                    'completion': self._get_expected_completion(
                        version,
                        earned=1.0,
                        possible=8.0,
                        percent=0.125,
                    ),
                },
                {
                    'course_key': 'otherOrg/toy/2012_Fall',
                    'completion': self._get_expected_completion(
                        version,
                        earned=0.0,
                        possible=None,
                        percent=0.0,
                    ),
                }
            ],
        }
        self.assertEqual(response.data, expected)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_list_view_with_sequentials(self, version):
        response = self.client.get(self.get_list_url(
            version,
            username=self.test_user.username,
            requested_fields='sequential'))
        self.assertEqual(response.status_code, 200)
        expected = {
            'count': 1,
            'previous': None,
            'next': None,
            'results': [
                {
                    'course_key': 'edX/toy/2012_Fall',
                    'completion': self._get_expected_completion(version),
                    'sequential': [
                        {
                            'course_key': 'edX/toy/2012_Fall',
                            'block_key': 'i4x://edX/toy/sequential/course-sequence1',
                            'completion': self._get_expected_completion(
                                version,
                                earned=1.0,
                                possible=5.0,
                                percent=0.2,
                            ),
                        },
                    ]
                }
            ],
        }
        self.assertEqual(response.data, expected)

    def assert_expected_detail_view(self, version):
        """
        Ensures that the expected data is returned from the versioned detail view.
        """
        response = self.client.get(self.get_detail_url(
            version,
            six.text_type(self.course_key),
            username=self.test_user.username))
        self.assertEqual(response.status_code, 200)
        expected_values = {
            'course_key': 'edX/toy/2012_Fall',
            'completion': self._get_expected_completion(version)
        }
        expected = self._get_expected_detail(version, expected_values)
        self.assertEqual(response.data, expected)

    @ddt.data(
        (0, True),
        (0, False),
        (1, True),
        (1, False)
    )
    @ddt.unpack
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    @patch.object(AggregationUpdater, 'update')
    def test_detail_view(self, version, waffle_active, mock_update):
        with override_flag(WAFFLE_AGGREGATE_STALE_FROM_SCRATCH, active=waffle_active):
            self.assert_expected_detail_view(version)
        # no stale completions, so aggregations were not updated
        assert mock_update.call_count == 0

    @ddt.data(
        (0, True),
        (0, False),
        (1, True),
        (1, False)
    )
    @ddt.unpack
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_detail_view_stale_completion(self, version, waffle_active):
        """
        Ensure that a stale completion causes the aggregations to be recalculated once.

        Verify that the stale completion not resolved.
        """
        models.StaleCompletion.objects.create(
            username=self.test_user.username,
            course_key=self.course_key,
            block_key=None,
            force=False,
        )
        assert models.StaleCompletion.objects.filter(resolved=False).count() == 1
        with override_flag('completion_aggregator.aggregate_stale_from_scratch', active=waffle_active):
            self.assert_expected_detail_view(version)
        assert models.StaleCompletion.objects.filter(resolved=False).count() == 1

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_detail_view_root_block(self):
        """
        Ensure that a stale completion causes the aggregations to be recalculated once.

        Verify that the stale completion not resolved.
        """
        models.StaleCompletion.objects.create(
            username=self.test_user.username,
            course_key=self.course_key,
            block_key=None,
            force=False,
        )
        response = self.client.get(
            self.get_detail_url(
                1,
                six.text_type(self.course_key),
                username=self.test_user.username,
                root_block=six.text_type(self.blocks[1]),
                requested_fields='sequential',
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [
            {
                'completion': {
                    'earned': 0.0,
                    'possible': None,
                    'percent': 0.0,
                    'optional': False
                },
                'course_key': six.text_type(self.course_key),
                'sequential': [
                    {
                        'course_key': six.text_type(self.course_key),
                        'block_key': six.text_type(self.blocks[1]),
                        'completion': {
                            'earned': 1.0,
                            'possible': 5.0,
                            'percent': 0.2,
                            'optional': False,
                        }
                    },
                ],
            }
        ])

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_detail_view_oauth2(self, version):
        """
        Test the detail view using OAuth2 Authentication
        """
        # Try with no authentication:
        self.client.logout()
        response = self.client.get(self.get_detail_url(version, self.course_key))
        self.assertEqual(response.status_code, 401)
        # Now, try with a valid token header:
        token = _create_oauth2_token(self.test_user)
        response = self.client.get(
            self.get_detail_url(version, self.course_key, username=self.test_user.username),
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        self.assertEqual(response.status_code, 200)
        if version == 0:
            self.assertEqual(response.data['completion']['earned'], 1.0)
        else:
            self.assertEqual(response.data['results'][0]['completion']['earned'], 1.0)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_detail_view_not_enrolled(self, version):
        """
        Test that requesting course completions for a course the user is not enrolled in
        will return a 404.
        """
        response = self.client.get(
            self.get_detail_url(
                version,
                self.other_org_course_key,
                username=self.test_user.username
            )
        )
        self.assertEqual(response.status_code, 404)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_detail_view_inactive_enrollment(self, version):
        self.test_enrollment.is_active = False
        self.test_enrollment.save()
        response = self.client.get(self.get_detail_url(version, self.course_key, username=self.test_user.username))
        self.assertEqual(response.status_code, 404)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_detail_view_no_completion(self, version):
        """
        Test that requesting course completions for a course which has started, but the user has not yet started,
        will return an empty completion record with its "possible" field filled in.
        """
        self.create_enrollment(
            user=self.test_user,
            course_id=self.other_org_course_key,
        )
        response = self.client.get(self.get_detail_url(
            version,
            self.other_org_course_key,
            username=self.test_user.username))
        self.assertEqual(response.status_code, 200)
        expected_values = {
            'course_key': 'otherOrg/toy/2012_Fall',
            'completion': self._get_expected_completion(version, earned=0.0, possible=None, percent=0.0),
        }
        expected = self._get_expected_detail(version, expected_values)
        self.assertEqual(response.data, expected)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_detail_view_with_sequentials(self, version):
        response = self.client.get(self.get_detail_url(
            version,
            self.course_key,
            username=self.test_user.username,
            requested_fields='sequential'))
        self.assertEqual(response.status_code, 200)
        expected_values = {
            'course_key': 'edX/toy/2012_Fall',
            'completion': self._get_expected_completion(version),
            'sequential': [
                {
                    'course_key': 'edX/toy/2012_Fall',
                    'block_key': 'i4x://edX/toy/sequential/course-sequence1',
                    'completion': self._get_expected_completion(version, earned=1.0, possible=5.0, percent=0.2),
                },
            ]
        }
        expected = self._get_expected_detail(version, expected_values)
        self.assertEqual(response.data, expected)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_detail_view_staff_requested_user(self, version):
        """
        Test that requesting course completions for a specific user filters out the other enrolled users
        """
        self.client.force_authenticate(self.staff_user)
        response = self.client.get(self.get_detail_url(version, self.course_key, username=self.test_user.username))
        self.assertEqual(response.status_code, 200)
        expected_values = {
            'course_key': 'edX/toy/2012_Fall',
            'completion': self._get_expected_completion(version)
        }
        expected = self._get_expected_detail(version, expected_values)
        self.assertEqual(response.data, expected)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    @patch.object(AggregationUpdater, 'update')
    def test_detail_view_staff_all_users(self, mock_update):
        """
        Test that staff requesting course completions can see all completions,
        and that the presence of stale completions does not trigger a recalculation.
        """
        # Add an additonal completion for the staff user
        another_user = User.objects.create(username='test_user_2')
        self.create_enrollment(
            user=another_user,
            course_id=self.course_key,
        )
        models.Aggregator.objects.submit_completion(
            user=another_user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key(block_type='sequential', block_id='course-sequence1'),
            aggregation_name='sequential',
            earned=3.0,
            possible=5.0,
            last_modified=timezone.now(),
        )
        models.Aggregator.objects.submit_completion(
            user=another_user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key(block_type='course', block_id='course'),
            aggregation_name='course',
            earned=3.0,
            possible=12.0,
            last_modified=timezone.now(),
        )
        # Create some stale completions too, to test recalculations are skipped
        for user in (another_user, self.test_user):
            models.StaleCompletion.objects.create(
                username=user.username,
                course_key=self.course_key,
                block_key=None,
                force=False,
            )
        assert models.StaleCompletion.objects.filter(resolved=False).count() == 2

        self.client.force_authenticate(self.staff_user)
        response = self.client.get(self.get_detail_url(1, self.course_key))
        self.assertEqual(response.status_code, 200)
        expected_values = [
            {
                'username': 'test_user',
                'course_key': 'edX/toy/2012_Fall',
                'completion': self._get_expected_completion(1)
            },
            {
                'username': 'test_user_2',
                'course_key': 'edX/toy/2012_Fall',
                'completion': self._get_expected_completion(1, earned=3.0, possible=12.0, percent=0.25),
            },
        ]
        expected = self._get_expected_detail(1, expected_values, count=2)
        self.assertEqual(response.data, expected)
        assert mock_update.call_count == 0
        assert models.StaleCompletion.objects.filter(resolved=False).count() == 2

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_detail_view_staff_requested_multiple_users(self):
        """
        Test that requesting course completions for a set of users filters out the other enrolled users
        """
        version = 1
        users = self.create_enrolled_users(3)
        self.create_course_completion_data(users[0], 3.0, 12.0)
        self.create_course_completion_data(users[1], 9.0, 12.0)
        self.create_course_completion_data(users[2], 6.0, 12.0)
        self.client.force_authenticate(self.staff_user)
        user_ids = f"{users[0].id},{users[2].id}"
        response = self.client.get(self.get_detail_url(version, self.course_key, user_ids=user_ids))
        self.assertEqual(response.status_code, 200)
        expected_values = [
            {
                'username': users[0].username,
                'course_key': 'edX/toy/2012_Fall',
                'completion': self._get_expected_completion(1, earned=3.0, possible=12.0, percent=0.25),
            },
            {
                'username': users[2].username,
                'course_key': 'edX/toy/2012_Fall',
                'completion': self._get_expected_completion(1, earned=6.0, possible=12.0, percent=0.5),
            },
        ]
        expected = self._get_expected_detail(version, expected_values, count=2)
        self.assertEqual(response.data, expected)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_detail_view_staff_requested_multiple_users_with_post(self):
        """
        Test that requesting course completions for a set of users filters out the other enrolled users
        using POST request values
        """
        version = 1
        users = self.create_enrolled_users(3)
        self.create_course_completion_data(users[0], 3.0, 12.0)
        self.create_course_completion_data(users[1], 9.0, 12.0)
        self.create_course_completion_data(users[2], 6.0, 12.0)
        self.client.force_authenticate(self.staff_user)
        body = {
            'user_ids': [int(users[0].id), int(users[2].id)]
        }
        response = self.client.post(
            self.get_detail_url(
                version,
                self.course_key
            ),
            data=json.dumps(body),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        expected_values = [
            {
                'username': users[0].username,
                'course_key': 'edX/toy/2012_Fall',
                'completion': self._get_expected_completion(1, earned=3.0, possible=12.0, percent=0.25),
            },
            {
                'username': users[2].username,
                'course_key': 'edX/toy/2012_Fall',
                'completion': self._get_expected_completion(1, earned=6.0, possible=12.0, percent=0.5),
            },
        ]
        expected = self._get_expected_detail(version, expected_values, count=2)
        self.assertEqual(response.data, expected)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_detail_view_staff_requested_username_with_post(self):
        """
        Test that requesting course completions for a defined username
        using POST request values
        """
        version = 1
        users = self.create_enrolled_users(2)
        self.create_course_completion_data(users[0], 3.0, 12.0)
        self.create_course_completion_data(users[1], 9.0, 12.0)
        self.client.force_authenticate(self.staff_user)
        body = {
            'username': users[0].username
        }
        response = self.client.post(
            self.get_detail_url(
                version,
                self.course_key,
            ),
            data=json.dumps(body),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        expected_values = [
            {
                'course_key': 'edX/toy/2012_Fall',
                'completion': self._get_expected_completion(1, earned=3.0, possible=12.0, percent=0.25),
            }
        ]
        expected = self._get_expected_detail(version, expected_values, count=1)
        self.assertEqual(response.data, expected)

    def _create_cohort(self, owner, users):
        """
        Create and populate a user group, as well as a cohort.
        """
        user_group = empty_compat.course_user_group().objects.create(
            name='test',
            course_id=self.course_key,
            group_type='cohort',
        )
        user_group.users.add(*users)
        owner.cohortmembership_set.add(
            empty_compat.cohort_membership_model().objects.create(
                course_user_group=user_group,
                user=owner,
                course_id=self.course_key,
            ),
        )

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_stat_view_course_no_cohorts(self):
        response = self.client.get(self.get_course_stat_url(
            'edX/toy/2012_Fall',
            cohorts=1,
            exclude_roles='staff',
        ))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['results'][0]['mean_completion']['earned'], 1.0)
        self.assertEqual(data['results'][0]['mean_completion']['possible'], 8.0)
        self.assertEqual(data['results'][0]['mean_completion']['percent'], .125)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_stat_view_staff_user_excluded_from_results(self):
        self.create_enrollment(user=self.staff_user, course_id=self.course_key)
        self._create_cohort(self.staff_user, [self.staff_user])
        models.Aggregator.objects.submit_completion(
            user=self.staff_user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key(
                block_type='course', block_id='course'),
            aggregation_name='course',
            earned=4.0,
            possible=8.0,
            last_modified=timezone.now(),
        )
        response = self.client.get(self.get_course_stat_url(
            'edX/toy/2012_Fall',
            cohorts=1,
            exclude_roles='staff'
        ))
        data = json.loads(response.content.decode('utf-8'))

        self.assertEqual(data['results'][0]['mean_completion']['earned'], 2.5)
        self.assertEqual(data['results'][0]['mean_completion']['possible'], 8.0)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_stat_view_unengaged_user(self):
        self.create_enrollment(user=self.staff_user, course_id=self.course_key)
        response = self.client.get(self.get_course_stat_url(
            'edX/toy/2012_Fall',
        ))
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['results'][0]['mean_completion']['earned'], 0.5)
        self.assertEqual(data['results'][0]['mean_completion']['possible'], 8.0)
        self.assertEqual(data['results'][0]['mean_completion']['percent'], 0.0625)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_stat_view_exclude_user_based_on_role(self):
        beta_user = User.objects.create(username='beta_user')
        self.create_enrollment(user=beta_user, course_id=self.course_key)
        self._create_cohort(beta_user, [beta_user])
        models.Aggregator.objects.submit_completion(
            user=beta_user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key(
                block_type='course', block_id='course'),
            aggregation_name='course',
            earned=7.0,
            possible=8.0,
            last_modified=timezone.now(),
        )

        response = self.client.get(self.get_course_stat_url(
            'edX/toy/2012_Fall',
            cohorts=1,
            exclude_roles='beta'
        ))
        data = json.loads(response.content.decode('utf-8'))

        self.assertEqual(data['results'][0]['mean_completion']['earned'], 1.0)
        self.assertEqual(data['results'][0]['mean_completion']['possible'], 8.0)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_stat_view_multiple_users_correct_calculations(self):
        users_in_cohort = []
        for x in range(1, 5):
            user = User.objects.create(username=f'test_user_{x}')
            users_in_cohort.append(user)
            self.create_enrollment(user=user, course_id=self.course_key)

            models.Aggregator.objects.submit_completion(
                user=user,
                course_key=self.course_key,
                block_key=self.course_key.make_usage_key(
                    block_type='course', block_id='course'),
                aggregation_name='course',
                earned=4.0,
                possible=8.0,
                last_modified=timezone.now(),
            )
        self._create_cohort(users_in_cohort[0], users_in_cohort)

        response = self.client.get(self.get_course_stat_url(
            'edX/toy/2012_Fall',
            cohorts=1,
            exclude_roles='staff'
        ))
        data = json.loads(response.content.decode('utf-8'))

        self.assertEqual(data['results'][0]['mean_completion']['possible'], 8.0)
        self.assertEqual(data['results'][0]['mean_completion']['earned'], 3.4)
        self.assertEqual(data['results'][0]['mean_completion']['percent'], 0.425)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_invalid_optional_fields(self, version):
        response = self.client.get(
            self.get_detail_url(
                version,
                'edX/toy/2012_Fall',
                username=self.test_user.username,
                requested_fields="INVALID"
            )
        )
        self.assertEqual(response.status_code, 400)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_unauthenticated(self, version):
        self.client.force_authenticate(None)
        detailresponse = self.client.get(self.get_detail_url(version, self.course_key))
        self.assertEqual(detailresponse.status_code, 401)
        listresponse = self.client.get(self.get_list_url(version))
        self.assertEqual(listresponse.status_code, 401)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_request_self(self, version):
        response = self.client.get(self.get_list_url(version, username=self.test_user.username))
        self.assertEqual(response.status_code, 200)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_wrong_user(self, version):
        user = User.objects.create(username='wrong')
        self.client.force_authenticate(user)
        response = self.client.get(self.get_list_url(version, username=self.test_user.username))
        self.assertEqual(response.status_code, 403)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_no_user(self, version):
        self.client.logout()
        response = self.client.get(self.get_list_url(version))
        self.assertEqual(response.status_code, 401)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_staff_access(self, version):
        self.client.force_authenticate(self.staff_user)
        response = self.client.get(self.get_list_url(version, username=self.test_user.username))
        self.assertEqual(response.status_code, 200)
        expected_completion = self._get_expected_completion(version)
        self.assertEqual(response.data['results'][0]['completion'], expected_completion)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_staff_access_non_user(self, version):
        self.client.force_authenticate(self.staff_user)
        response = self.client.get(self.get_list_url(version, username='who-dat'))
        self.assertEqual(response.status_code, 404)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_no_staff_access_other_user_detail(self, version):
        self.client.force_authenticate(self.test_user)
        test_user2 = User.objects.create(username='test_user2')
        self.create_enrollment(
            user=test_user2,
            course_id=self.course_key,
        )
        response = self.client.get(self.get_detail_url(version, self.course_key, username=test_user2.username))
        self.assertEqual(response.status_code, 403)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_no_staff_access_other_user(self, version):
        self.client.force_authenticate(self.test_user)
        test_user2 = User.objects.create(username='test_user2')
        self.create_enrollment(
            user=test_user2,
            course_id=self.course_key,
        )
        response = self.client.get(self.get_list_url(version, username=test_user2.username))
        self.assertEqual(response.status_code, 403)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_no_staff_access_no_user(self, version):
        self.client.force_authenticate(self.test_user)
        response = self.client.get(self.get_list_url(version))
        self.assertEqual(response.status_code, 403 if version == 1 else 200)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_staff_access_no_user(self, version):
        self.client.force_authenticate(self.staff_user)
        response = self.client.get(self.get_list_url(version))
        self.assertEqual(response.status_code, 200)

    def get_course_stat_url(self, course_key, **params):
        """
        Given a course_key and a number of key-value pairs as keyword arguments,
        create a URL to the stats view.
        """
        return append_params(
            self.course_stat_url_fmt.format(six.text_type(course_key)), params)

    def get_detail_url(self, version, course_key, **params):
        """
        Given a course_key and a number of key-value pairs as keyword arguments,
        create a URL to the detail view.
        """
        return append_params(self.detail_url_fmt.format(version, six.text_type(course_key)), params)

    def get_list_url(self, version, **params):
        """
        Given a number of key-value pairs as keyword arguments,
        create a URL to the list view.
        """
        return append_params(self.list_url.format(version), params)


class CompletionBlockUpdateViewTestCase(CompletionAPITestMixin, TestCase):
    """
    Test that CompletionBlockUpdateView can be used to mark XBlocks as completed.

    Ensure that it handles authorization as well.
    """

    course_key = CourseKey.from_string('edX/toy/2012_Fall')
    usage_key = course_key.make_usage_key('html', 'course-sequence1-html1')

    def setUp(self):
        super().setUp()
        self.test_user = User.objects.create(username='test_user')
        self.staff_user = User.objects.create(username='staff', is_staff=True)
        self.test_enrollment = self.create_enrollment(
            user=self.test_user,
            course_id=self.course_key,
        )
        self.blocks = [
            self.course_key.make_usage_key('course', 'course'),
            self.course_key.make_usage_key('sequential', 'course-sequence1'),
            self.course_key.make_usage_key('sequential', 'course-sequence2'),
            self.course_key.make_usage_key('html', 'course-sequence1-html1'),
            self.course_key.make_usage_key('html', 'course-sequence1-html2'),
            self.course_key.make_usage_key('html', 'course-sequence1-html3'),
            self.course_key.make_usage_key('html', 'course-sequence1-html4'),
            self.course_key.make_usage_key('html', 'course-sequence1-html5'),
            self.course_key.make_usage_key('html', 'course-sequence2-html6'),
            self.course_key.make_usage_key('html', 'course-sequence2-html7'),
            self.course_key.make_usage_key('html', 'course-sequence2-html8'),
        ]
        compat = StubCompat(self.blocks)
        for compat_import in (
                'completion_aggregator.api.common.compat',
                'completion_aggregator.api.v0.views.compat',
                'completion_aggregator.serializers.compat',
                'completion_aggregator.core.compat',
        ):
            patcher = patch(compat_import, compat)
            patcher.start()
            self.addCleanup(patcher.__exit__, None, None, None)

        self.patch_object(
            CompletionViewMixin,
            'get_authenticators',
            return_value=[OAuth2Authentication(), SessionAuthentication()]
        )
        self.patch_object(
            CompletionViewMixin,
            'pagination_class',
            new_callable=PropertyMock,
            return_value=PageNumberPagination
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.test_user)
        self.update_url = reverse(
            'completion_api_v0:blockcompletion-update',
            kwargs={'course_key': six.text_type(self.course_key), 'block_key': six.text_type(self.usage_key)}
        )

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    @patch.object(BlockCompletionManager, 'submit_completion', return_value=(None, True))
    def test_create_view(self, stub_submit):
        create_response = self.client.post(self.update_url, {'completion': 1})
        assert create_response.status_code == 201
        stub_submit.assert_called_once()

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    @patch.object(BlockCompletionManager, 'submit_completion', return_value=(None, True))
    def test_create_view_oauth2(self, stub_submit):
        """
        Test the create view using OAuth2 Authentication
        """

        self.client.logout()
        response = self.client.post(self.update_url, {'completion': 1.0})
        self.assertEqual(response.status_code, 401)
        stub_submit.assert_not_called()

        # Now, try with a valid token header:
        token = _create_oauth2_token(self.test_user)
        response = self.client.post(self.update_url, {'completion': 1.0}, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 201)
        stub_submit.assert_called_once()

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    @XBlock.register_temp_plugin(StubHTML, 'html')
    def test_unauthenticated(self):
        self.client.force_authenticate(None)
        response = self.client.post(self.update_url, {'completion': 1.0})
        self.assertEqual(response.status_code, 401)


def append_params(base, params):
    """
    Append the parameters to the base url, if any are provided.
    """
    if params:
        return '?'.join([base, six.moves.urllib.parse.urlencode(params)])
    return base
