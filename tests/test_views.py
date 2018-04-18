"""
Test serialization of completion data.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from collections import namedtuple
from datetime import timedelta
from unittest import expectedFailure

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
from completion_aggregator.api.v1.views import CompletionListView, CompletionViewMixin, UserEnrollments
from test_utils.test_blocks import StubCourse, StubSequential

_StubEnrollment = namedtuple('_StubEnrollment', ['user', 'course_id'])


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


class CompletionViewTestCase(TestCase):
    """
    Test that the CompletionView renders completion data properly.
    """

    course_key = CourseKey.from_string('edX/toy/2012_Fall')
    other_org_course_key = CourseKey.from_string('otherOrg/toy/2012_Fall')
    list_url = '/v1/course/'
    detail_url_fmt = '/v1/course/{}/'

    def setUp(self):
        self.test_user = User.objects.create(username='test_user')
        self.staff_user = User.objects.create(username='staff', is_staff=True)
        self.mock_get_enrollment = self.patch_object(UserEnrollments, 'get_enrollments', return_value=[
            _StubEnrollment(user=self.test_user, course_id=self.course_key)
        ])
        self.patch_object(UserEnrollments, 'is_enrolled', side_effect=lambda course: course == self.course_key)
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

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_list_view(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        expected = {
            'count': 1,
            'previous': None,
            'next': None,
            'results': [
                {
                    'course_key': 'edX/toy/2012_Fall',
                    'completion': {
                        'earned': 1.0,
                        'possible': 12.0,
                        'percent': 1 / 12,
                    },
                }
            ],
        }
        self.assertEqual(response.data, expected)

    @expectedFailure
    def test_list_view_enrolled_no_progress(self):
        """
        Test that the completion API returns a record for each course the user is enrolled in,
        even if no progress records exist yet.

        @expectedFailure:

        This test depends on being able to fill in missing data to get an appropriate value for
        "possible" or "percent".  Actual calculation of Aggregator values is coming in a
        later story (OC-3098)

        """
        self.mock_get_enrollment.return_value += [  # pylint: disable=no-member
            _StubEnrollment(self.test_user, self.other_org_course_key)
        ]
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        expected = {
            'pagination': {'count': 2, 'previous': None, 'num_pages': 1, 'next': None},
            'results': [
                {
                    'course_key': 'edX/toy/2012_Fall',
                    'completion': {
                        'earned': 1.0,
                        'possible': 12.0,
                        'percent': 1 / 12,
                    },
                },
                {
                    'course_key': 'otherOrg/toy/2012_Fall',
                    'completion': {
                        'earned': 0.0,
                        'possible': 12.0,
                        'percent': 0.0,
                    },
                }
            ],
        }
        self.assertEqual(response.data, expected)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    def test_list_view_with_sequentials(self):
        response = self.client.get(self.get_list_url(requested_fields='sequential'))
        self.assertEqual(response.status_code, 200)
        expected = {
            'count': 1,
            'previous': None,
            'next': None,
            'results': [
                {
                    'course_key': 'edX/toy/2012_Fall',
                    'completion': {
                        'earned': 1.0,
                        'possible': 12.0,
                        'percent': 1 / 12,
                    },
                    'sequential': [
                        {
                            'course_key': u'edX/toy/2012_Fall',
                            'block_key': u'i4x://edX/toy/sequential/vertical_sequential',
                            'completion': {'earned': 1.0, 'possible': 5.0, 'percent': 0.2},
                        },
                    ]
                }
            ],
        }
        self.assertEqual(response.data, expected)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    def test_detail_view(self):
        response = self.client.get(self.get_detail_url(six.text_type(self.course_key)))
        self.assertEqual(response.status_code, 200)
        expected = {
            'count': 1,
            'previous': None,
            'next': None,
            'results': [
                {
                    'course_key': 'edX/toy/2012_Fall',
                    'completion': {
                        'earned': 1.0,
                        'possible': 12.0,
                        'percent': 1 / 12,
                    },
                }
            ]
        }

        self.assertEqual(response.data, expected)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_detail_view_oauth2(self):
        """
        Test the detail view using OAuth2 Authentication
        """
        # Try with no authentication:
        self.client.logout()
        response = self.client.get(self.get_detail_url(self.course_key))
        self.assertEqual(response.status_code, 401)
        # Now, try with a valid token header:
        token = _create_oauth2_token(self.test_user)
        response = self.client.get(self.get_detail_url(self.course_key), HTTP_AUTHORIZATION="Bearer {0}".format(token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['completion']['earned'], 1.0)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_detail_view_not_enrolled(self):
        """
        Test that requesting course completions for a course the user is not enrolled in
        will return a 404.
        """
        response = self.client.get(self.get_detail_url(self.other_org_course_key,
                                                       username=self.test_user.username))
        self.assertEqual(response.status_code, 404)

    @expectedFailure
    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_detail_view_no_completion(self):
        """
        Test that requesting course completions for a course which has started, but the user has not yet started,
        will return an empty completion record with its "possible" field filled in.

        @expectedFailure:

        This test depends on being able to fill in missing data to get an appropriate value for
        "possible" or "percent".  Actual calculation of Aggregator values is coming in a
        later story (OC-3098)
        """
        self.mock_get_enrollment.return_value += [  # pylint: disable=no-member
            _StubEnrollment(self.test_user, self.other_org_course_key)
        ]
        response = self.client.get(self.get_detail_url(self.other_org_course_key))
        self.assertEqual(response.status_code, 200)
        expected = {
            'course_key': 'otherOrg/toy/2012_Fall',
            'completion': {
                'earned': 0.0,
                'possible': 12.0,
                'percent': 0.0,
            },
        }
        self.assertEqual(response.data, expected)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    @XBlock.register_temp_plugin(StubSequential, 'sequential')
    def test_detail_view_with_sequentials(self):
        response = self.client.get(self.get_detail_url(self.course_key, requested_fields='sequential'))
        self.assertEqual(response.status_code, 200)
        expected = {
            'count': 1,
            'previous': None,
            'next': None,
            'results': [
                {
                    'course_key': 'edX/toy/2012_Fall',
                    'completion': {
                        'earned': 1.0,
                        'possible': 12.0,
                        'percent': 1 / 12,
                    },
                    'sequential': [
                        {
                            'course_key': u'edX/toy/2012_Fall',
                            'block_key': u'i4x://edX/toy/sequential/vertical_sequential',
                            'completion': {'earned': 1.0, 'possible': 5.0, 'percent': 0.2},
                        },
                    ]
                }
            ]
        }
        self.assertEqual(response.data, expected)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_detail_view_staff_requested_user(self):
        """
        Test that requesting course completions for a specific user filters out the other enrolled users
        """
        self.client.force_authenticate(self.staff_user)
        response = self.client.get(self.get_detail_url(self.course_key, username=self.test_user.username))
        self.assertEqual(response.status_code, 200)
        expected = {
            'count': 1,
            'previous': None,
            'next': None,
            'results': [
                {
                    'course_key': 'edX/toy/2012_Fall',
                    'completion': {
                        'earned': 1.0,
                        'possible': 12.0,
                        'percent': 1 / 12,
                    },
                }
            ]
        }
        self.assertEqual(response.data, expected)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_invalid_optional_fields(self):
        response = self.client.get(self.detail_url_fmt.format('edX/toy/2012_Fall') + '?requested_fields=INVALID')
        self.assertEqual(response.status_code, 400)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_unauthenticated(self):
        self.client.force_authenticate(None)
        detailresponse = self.client.get(self.get_detail_url(self.course_key))
        self.assertEqual(detailresponse.status_code, 401)
        listresponse = self.client.get(self.get_list_url())
        self.assertEqual(listresponse.status_code, 401)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_request_self(self):
        response = self.client.get(self.list_url + '?username={}'.format(self.test_user.username))
        self.assertEqual(response.status_code, 200)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_wrong_user(self):
        user = User.objects.create(username='wrong')
        self.client.force_authenticate(user)
        response = self.client.get(self.list_url + '?username={}'.format(self.test_user.username))
        self.assertEqual(response.status_code, 404)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_no_user(self):
        self.client.logout()
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_staff_access(self):
        self.client.force_authenticate(self.staff_user)
        response = self.client.get(self.get_list_url(username=self.test_user.username))
        self.assertEqual(response.status_code, 200)
        expected_completion = {'earned': 1.0, 'possible': 12.0, 'percent': 1 / 12}
        self.assertEqual(response.data['results'][0]['completion'], expected_completion)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def test_staff_access_non_user(self):
        self.client.force_authenticate(self.staff_user)
        response = self.client.get(self.get_list_url(username='who-dat'))
        self.assertEqual(response.status_code, 404)

    @XBlock.register_temp_plugin(StubCourse, 'course')
    def get_detail_url(self, course_key, **params):
        """
        Given a course_key and a number of key-value pairs as keyword arguments,
        create a URL to the detail view.
        """
        return append_params(self.detail_url_fmt.format(six.text_type(course_key)), params)

    def get_list_url(self, **params):
        """
        Given a number of key-value pairs as keyword arguments,
        create a URL to the list view.
        """
        return append_params(self.list_url, params)


def append_params(base, params):
    """
    Append the parameters to the base url, if any are provided.
    """
    if params:
        return '?'.join([base, six.moves.urllib.parse.urlencode(params)])
    return base
