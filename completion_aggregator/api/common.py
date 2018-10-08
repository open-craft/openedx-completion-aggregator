"""
Common classes for api views
"""
from rest_framework.exceptions import NotFound, ParseError, PermissionDenied
from rest_framework.permissions import IsAuthenticated

from django.contrib.auth import get_user_model

from .. import compat
from ..models import Aggregator
from ..serializers import course_completion_serializer_factory, is_aggregation_name

User = get_user_model()  # pylint: disable=invalid-name


class UserEnrollments(object):
    """
    Class for querying user enrollments
    """
    def __init__(self, user=None):
        """
        Filter active course enrollments for the given user, if any.
        """
        self.queryset = compat.course_enrollment_model().objects.filter(is_active=True)
        if user:
            self.queryset = self.queryset.filter(user=user)

    def get_course_enrollments(self, course_key):
        """
        Return a collection of CourseEnrollments.

        **Parameters**

        course_id:
            Return all the enrollments for this course.

        The collection must have a .__len__() attribute, be sliceable,
        and consist of objects that have a user attribute and a course_id
        attribute.
        """
        queryset = self.queryset.filter(course_id=course_key)
        return queryset.order_by('user')

    def get_course_enrollment(self, course_key):
        """
        Return a collection of CourseEnrollments.

        **Parameters**

        course_id:
            Return all the enrollments for this course.

        The collection must have a .__len__() attribute, be sliceable,
        and consist of objects that have a user attribute and a course_id
        attribute.
        """
        return self.queryset.get(course_id=course_key)

    def get_enrollments(self):
        """
        Return a collection of CourseEnrollments for the current user (if specified).

        The collection must have a .__len__() attribute, be sliceable,
        and consist of objects that have a user attribute and a course_id
        attribute.
        """
        return self.queryset.order_by('user', 'course_id')

    def is_enrolled(self, course_key):
        """
        Return a boolean stating whether user is enrolled in the named course.
        """
        return self.queryset.filter(course_id=course_key).exists()


class CompletionViewMixin(object):
    """
    Common functionality for completion views.
    """

    _allowed_requested_fields = {'mean', 'username'}
    permission_classes = (IsAuthenticated,)
    _effective_user = None
    _requested_user = None

    @property
    def authentication_classes(self):  # pragma: no cover
        """
        Allow users authenticated via OAuth2 or normal session authentication.
        """
        from openedx.core.lib.api import authentication  # pylint: disable=import-error
        from edx_rest_framework_extensions.authentication import JwtAuthentication  # pylint: disable=import-error
        return [
            JwtAuthentication,
            authentication.OAuth2AuthenticationAllowInactiveUser,
            authentication.SessionAuthenticationAllowInactiveUser,
        ]

    @property
    def pagination_class(self):  # pragma: no cover
        """
        Return the class to use for pagination
        """
        try:
            from edx_rest_framework_extensions import paginators
        except ImportError:  # paginators are in edx-platform in ginkgo
            from openedx.core.lib.api import paginators

        return paginators.NamespacedPageNumberPagination

    @property
    def user(self):
        """
        Return the effective user.

        Usually the requesting user, but a staff user can override this.
        """
        if self._effective_user:
            return self._effective_user

        requested_username = self.request.GET.get('username')
        if not requested_username:
            if self.request.user.is_staff:
                user = self.request.user
                self._requested_user = None
            else:
                raise PermissionDenied()
        else:
            if self.request.user.is_staff:
                try:
                    user = User.objects.get(username=requested_username)
                except User.DoesNotExist:
                    raise NotFound()
            else:
                if self.request.user.username.lower() == requested_username.lower():
                    user = self.request.user
                else:
                    raise PermissionDenied()
            self._requested_user = user
        self._effective_user = user
        return self._effective_user

    @property
    def requested_user(self):
        """
        Return the requested user.

        Will be None if no specific username was in the request.
        """
        # Populating the user property also sets the requested user
        self.user  # pylint: disable=pointless-statement
        return self._requested_user

    def get_queryset(self):
        """
        Build a base queryset of relevant course-level Aggregator objects.
        """
        aggregations = {'course'}
        aggregations.update(category for category in self.get_requested_fields() if is_aggregation_name(category))
        return Aggregator.objects.filter(aggregation_name__in=aggregations)

    def get_requested_fields(self):
        """
        Parse and return value for requested_fields parameter.
        """
        fields = {
            field for field in self.request.GET.get('requested_fields', '').split(',') if field
        }
        invalid = set()
        for field in fields:
            if not (is_aggregation_name(field) or field in self._allowed_requested_fields):
                invalid.add(field)

        if invalid:
            msg = 'Invalid requested_fields value(s): {}'
            raise ParseError(msg.format(invalid))
        return fields

    def get_serializer_class(self, version=1):
        """
        Return the appropriate serializer.
        """
        return course_completion_serializer_factory(self.get_requested_fields(), version=version)
