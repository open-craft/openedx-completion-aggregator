"""
Test serialization of completion data.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import timedelta

import ddt
import six
from mock import PropertyMock, patch
from oauth2_provider import models as dot_models
from oauth2_provider.ext.rest_framework import OAuth2Authentication
from opaque_keys.edx.keys import CourseKey
from rest_framework.authentication import SessionAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.test import APIClient
from xblock.core import XBlock

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from completion_aggregator import models
from completion_aggregator.api.v1.views import CompletionViewMixin
from completion_aggregator.serializers import AggregationUpdater
from test_utils.compat import StubCompat
from test_utils.test_blocks import StubCourse, StubSequential

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


@ddt.ddt
@patch('completion_aggregator.api.common.compat', empty_compat)
@patch('completion_aggregator.serializers.compat', empty_compat)
@patch('completion_aggregator.tasks.aggregation_tasks.compat', empty_compat)
class CompletionViewTestCase(TestCase):
    """
    Test that the CompletionView renders completion data properly.
    """

    course_key = CourseKey.from_string('edX/toy/2012_Fall')
    other_org_course_key = CourseKey.from_string('otherOrg/toy/2012_Fall')
    list_url = '/v{}/course/'
    detail_url_fmt = '/v{}/course/{}/'
    course_enrollment_model = StubCompat([]).course_enrollment_model()

    def setUp(self):
        self.test_user = User.objects.create(username='test_user')
        self.staff_user = User.objects.create(username='staff', is_staff=True)
        self.test_enrollment = self.create_enrollment(
            user=self.test_user,
            course_id=self.course_key,
        )
        self.patch_object(
            CompletionViewMixin,
            'authentication_classes',
            new_callable=PropertyMock,
            return_value=[OAuth2Authentication, SessionAuthentication]
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
        models.Aggregator.objects.submit_completion(
            user=self.test_user,
            course_key=self.course_key,
            block_key=self.course_key.make_usage_key(block_type='sequential', block_id='vertical_sequential'),
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
            possible=12.0,
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

    def _get_expected_completion(self, version, earned=1.0, possible=12.0, percent=0.0833333333333333):
        """
        Return completion section based on version.
        """
        completion = {
            'earned': earned,
            'possible': possible,
            'percent': percent,
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
        response = self.client.get(self.list_url.format(version))
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
    @patch.object(AggregationUpdater, 'update')
    def test_list_view(self, version, mock_update):
        self.assert_expected_list_view(version)
        # no stale completions, so aggregations were not updated
        assert mock_update.call_count == 0

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @patch.object(AggregationUpdater, 'calculate_updated_aggregators')
    def test_list_view_stale_completion(self, version, mock_calculate):
        """
        Ensure that a stale completion causes the aggregations to be recalculated, but not updated in the db,
        and stale completion is not resolved.
        """
        models.StaleCompletion.objects.create(
            username=self.test_user.username,
            course_key=self.course_key,
            block_key=None,
            force=False,
        )
        assert models.StaleCompletion.objects.filter(resolved=False).count() == 1
        self.assert_expected_list_view(version)
        assert mock_calculate.call_count == 1
        assert models.StaleCompletion.objects.filter(resolved=False).count() == 1

    @ddt.data(0, 1)
    def test_list_view_enrolled_no_progress(self, version):
        """
        Test that the completion API returns a record for each course the user is enrolled in,
        even if no progress records exist yet.
        """
        self.create_enrollment(
            user=self.test_user,
            course_id=self.other_org_course_key,
        )
        response = self.client.get(self.list_url.format(version))
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
                        earned=0.0,
                        possible=None,
                        percent=0.0,
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
    def test_list_view_with_sequentials(self, version):
        response = self.client.get(self.get_list_url(version, requested_fields='sequential'))
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
                            'course_key': u'edX/toy/2012_Fall',
                            'block_key': u'i4x://edX/toy/sequential/vertical_sequential',
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
        response = self.client.get(self.get_detail_url(version, six.text_type(self.course_key)))
        self.assertEqual(response.status_code, 200)
        expected_values = {
            'course_key': 'edX/toy/2012_Fall',
            'completion': self._get_expected_completion(version)
        }
        expected = self._get_expected_detail(version, expected_values)
        self.assertEqual(response.data, expected)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @patch.object(AggregationUpdater, 'update')
    def test_detail_view(self, version, mock_update):
        self.assert_expected_detail_view(version)
        # no stale completions, so aggregations were not updated
        assert mock_update.call_count == 0

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    @patch.object(AggregationUpdater, 'calculate_updated_aggregators')
    def test_detail_view_stale_completion(self, version, mock_calculate):
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
        self.assert_expected_detail_view(version)
        assert mock_calculate.call_count == 1
        assert models.StaleCompletion.objects.filter(resolved=False).count() == 1

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
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
            self.get_detail_url(version, self.course_key),
            HTTP_AUTHORIZATION="Bearer {0}".format(token)
        )
        self.assertEqual(response.status_code, 200)
        if version == 0:
            self.assertEqual(response.data['completion']['earned'], 1.0)
        else:
            self.assertEqual(response.data['results'][0]['completion']['earned'], 1.0)

    @ddt.data(0, 1)
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
    def test_detail_view_inactive_enrollment(self, version):
        self.test_enrollment.is_active = False
        self.test_enrollment.save()
        response = self.client.get(self.get_detail_url(version, self.course_key))
        self.assertEqual(response.status_code, 404)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_detail_view_no_completion(self, version):
        """
        Test that requesting course completions for a course which has started, but the user has not yet started,
        will return an empty completion record with its "possible" field filled in.
        """
        self.create_enrollment(
            user=self.test_user,
            course_id=self.other_org_course_key,
        )
        response = self.client.get(self.get_detail_url(version, self.other_org_course_key))
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
    def test_detail_view_with_sequentials(self, version):
        response = self.client.get(self.get_detail_url(version, self.course_key, requested_fields='sequential'))
        self.assertEqual(response.status_code, 200)
        expected_values = {
            'course_key': 'edX/toy/2012_Fall',
            'completion': self._get_expected_completion(version),
            'sequential': [
                {
                    'course_key': u'edX/toy/2012_Fall',
                    'block_key': u'i4x://edX/toy/sequential/vertical_sequential',
                    'completion': self._get_expected_completion(version, earned=1.0, possible=5.0, percent=0.2),
                },
            ]
        }
        expected = self._get_expected_detail(version, expected_values)
        self.assertEqual(response.data, expected)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
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
            block_key=self.course_key.make_usage_key(block_type='sequential', block_id='vertical_sequential'),
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

    @ddt.data(0, 1)
    def test_invalid_optional_fields(self, version):
        response = self.client.get(
            self.detail_url_fmt.format(version, 'edX/toy/2012_Fall') + '?requested_fields=INVALID'
        )
        self.assertEqual(response.status_code, 400)

    @ddt.data(0, 1)
    def test_unauthenticated(self, version):
        self.client.force_authenticate(None)
        detailresponse = self.client.get(self.get_detail_url(version, self.course_key))
        self.assertEqual(detailresponse.status_code, 401)
        listresponse = self.client.get(self.get_list_url(version))
        self.assertEqual(listresponse.status_code, 401)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_request_self(self, version):
        response = self.client.get(self.get_list_url(version, username=self.test_user.username))
        self.assertEqual(response.status_code, 200)

    @ddt.data(0, 1)
    def test_wrong_user(self, version):
        user = User.objects.create(username='wrong')
        self.client.force_authenticate(user)
        response = self.client.get(self.get_list_url(version, username=self.test_user.username))
        self.assertEqual(response.status_code, 404)

    @ddt.data(0, 1)
    def test_no_user(self, version):
        self.client.logout()
        response = self.client.get(self.get_list_url(version))
        self.assertEqual(response.status_code, 401)

    @ddt.data(0, 1)
    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_staff_access(self, version):
        self.client.force_authenticate(self.staff_user)
        response = self.client.get(self.get_list_url(version, username=self.test_user.username))
        self.assertEqual(response.status_code, 200)
        expected_completion = self._get_expected_completion(version)
        self.assertEqual(response.data['results'][0]['completion'], expected_completion)

    @ddt.data(0, 1)
    def test_staff_access_non_user(self, version):
        self.client.force_authenticate(self.staff_user)
        response = self.client.get(self.get_list_url(version, username='who-dat'))
        self.assertEqual(response.status_code, 404)

    @XBlock.register_temp_plugin(StubCourse, 'course')
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


def append_params(base, params):
    """
    Append the parameters to the base url, if any are provided.
    """
    if params:
        return '?'.join([base, six.moves.urllib.parse.urlencode(params)])
    return base
