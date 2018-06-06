"""
API views to read completion information.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from opaque_keys.edx.keys import CourseKey
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from django.contrib.auth import get_user_model

from ... import compat
from ...models import Aggregator
from ...serializers import AggregatorAdapter, course_completion_serializer_factory, is_aggregation_name

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
        return [
            authentication.OAuth2AuthenticationAllowInactiveUser,
            authentication.SessionAuthenticationAllowInactiveUser,
        ]

    @property
    def pagination_class(self):  # pragma: no cover
        """
        Return the class to use for pagination
        """
        try:
            from edx_rest_framework_extensions import paginators  # pylint: disable=import-error
        except ImportError:  # paginators are in edx-platform in ginkgo
            from openedx.core.lib.api import paginators  # pylint: disable=import-error

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
            user = self.request.user
            self._requested_user = None
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
                    raise NotFound()
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

    def get_serializer_class(self):
        """
        Return the appropriate serializer.
        """
        return course_completion_serializer_factory(self.get_requested_fields())


class CompletionListView(CompletionViewMixin, APIView):
    """
    API view to render serialized CourseCompletions for a single user
    across all enrolled courses.

    **Example Requests**

        GET /api/completion/v1/course/
        GET /api/completion/v1/course/?requested_fields=chapter,vertical

    **Response Values**

        The response is a dictionary comprising pagination data and a page
        of results.

        * page: The page number of the current set of results.
        * next: The URL for the next page of results, or None if already on
          the last page.
        * previous: The URL for the previous page of results, or None if
          already on the first page.
        * count: The total number of available results.
        * results: A list of dictionaries representing the user's completion
          for each course.

        Standard fields for each completion dictionary:

        * course_key (CourseKey): The unique course identifier.
        * completion: A dictionary comprising of the following fields:
            * earned (float): The sum of the learner's completions.
            * possible (float): The total number of completions available
              in the course.
            * ratio (float in the range [0.0, 1.0]): The ratio of earned
              completions to possible completions in the course.

        Optional fields, as requested in "requested_fields":

        * mean (float): The average completion ratio for all students enrolled
          in the course.
        * Aggregators: The actual fields available are configurable, but
          may include `chapter`, `sequential`, or `vertical`.  If requested,
          the field will be a list of all blocks of that type containing
          completion information for that block.  Fields for each entry will
          include:

              * course_key (CourseKey): The unique course identifier.
              * usage_key: (UsageKey) The unique block identifier.
              * completion: A completion dictionary, identical in format to
                the course-level completion dictionary.

    **Parameters**

        username (optional):
            The username of the specified user for whom the course data is
            being accessed.  If not specified, this defaults to the requesting
            user.

        requested_fields (optional):
            A comma separated list of extra data to be returned.  This can be
            one of the block types specified in `AGGREGATE_CATEGORIES`, or any of
            the other optional fields specified above.  If any invalid fields
            are requested, a 400 error will be returned.

    **Returns**

        * 200 on success with above fields
        * 400 if an invalid value was sent for requested_fields.
        * 403 if a user who does not have permission to masquerade as another
          user specifies a username other than their own.
        * 404 if the course is not available or the requesting user can see no
          completable sections.

        Example response:

            GET /api/completion/v1/course

            {
              "count": 14,
              "num_pages": 1,
              "current_page": 1,
              "start": 1,
              "next": "/api/completion/v1/course/?page=2,
              "previous": None,
              "results": [
                {
                  "course_key": "edX/DemoX/Demo_course",
                  "completion": {
                    "earned": 42.0,
                    "possible": 54.0,
                    "ratio": 0.77777777777778
                  },
                  "chapter": [
                    {
                      "course_key": "edX/DemoX/Demo_course",
                      "block_key": "i4x://edX/DemoX/chapter/chapter1",
                      "completion": {
                        "earned: 20.0,
                        "possible": 30.0,
                        "ratio": 0.6666666666667
                      }
                    },
                    {
                      "course_key": "edX/DemoX/Demo_course",
                      "block_key": "i4x://edX/DemoX/chapter/chapter2",
                      "completion": {
                        "earned: 22.0,
                        "possible": 24.0,
                        "ratio": 0.9166666666667
                      }
                    }
                  ]
                },
                {
                  "course_key": "course-v1:GeorgetownX+HUMX421-02x+1T2016",
                  "completion": {
                    "earned": 12.0,
                    "possible": 24.0,
                    "ratio": 0.5
                  },
                  "chapter": [
                    {
                      "course_key": "course-v1:GeorgetownX+HUMX421-02x+1T2016",
                      "block_key": "block-v1:GeorgetownX+HUMX421-02x+1T2016+type@chapter+block@Week-2-TheVitaNuova",
                      "completion": {
                        "earned: 12.0,
                        "possible": 24.0,
                        "ratio": 0.5
                      }
                    }
                  ]
                }
              ]
            }

    This is a transitional implementation that uses the
    edx-solutions/progress-edx-platform-extensions models as a backing store.
    The replacement will have the same interface.
    """

    def get(self, request):
        """
        Handler for GET requests.
        """
        paginator = self.pagination_class()  # pylint: disable=not-callable

        # Paginate the list of active enrollments, annotated (manually) with a student progress object.
        enrollments = UserEnrollments(self.user).get_enrollments()
        paginated = paginator.paginate_queryset(enrollments, self.request, view=self)
        # Grab the progress items for these enrollments
        course_keys = [enrollment.course_id for enrollment in paginated]
        aggregator_queryset = self.get_queryset().filter(
            user=self.user,
            course_key__in=course_keys
        )

        # Create the list of aggregate completions to be serialized.
        completions = [
            AggregatorAdapter(
                user=self.user,
                course_key=enrollment.course_id,
                queryset=aggregator_queryset,
            ) for enrollment in paginated
        ]

        # Return the paginated, serialized completions
        serializer = self.get_serializer_class()(
            instance=completions,
            requested_fields=self.get_requested_fields(),
            many=True
        )
        return paginator.get_paginated_response(serializer.data)


class CompletionDetailView(CompletionViewMixin, APIView):
    """
    API view to render a serialized CourseCompletion for a single user in a
    single course.

    **Request Format**

        GET /api/completion/v1/course/<course_key>/

    **Example Requests**

        GET /api/completion/v1/course/course-v1:GeorgetownX+HUMX421-02x+1T2016/
        GET /api/completion/v1/course/course-v1:edX+DemoCourse+Demo2017/?requested_fields=chapter,vertical

    **Response Values**

        The response is a dictionary comprising pagination data and a page
        of results.

        * page: The page number of the current set of results.
        * next: The URL for the next page of results, or None if already on
          the last page.
        * previous: The URL for the previous page of results, or None if
          already on the first page.
        * count: The total number of available results.
        * results: A list of dictionaries representing the user's completion
          for each course.

        Standard fields for each completion dictionary:

        * course_key (CourseKey): The unique course identifier.
        * completion: A dictionary comprising of the following fields:
            * earned (float): The sum of the learner's completions.
            * possible (float): The total number of completions available
              in the course.
            * percent (float in the range [0.0, 1.0]): The percent of possible
              completions in the course that have been earned by the learner.

        Optional fields:

        * If "requested_fields" is specified, the response will include data
          for specific block types.  The fields available are configurable, but
          may include `chapter`, `sequential`, or `vertical`.  If requested,
          the block type will be present as another field in the response.
          Inside the field will be a list of all blocks of that type containing
          completion information for that block.  Fields for each entry will
          include:

              * course_key (CourseKey): The unique course identifier.
              * usage_key: (UsageKey) The unique block identifier.
              * completion: A dictionary comprising the following fields.
                  * earned (float): The sum of the learner's completions.
                  * possible (float): The total number of completions
                    available within the identified block.
                  * ratio (float in the range [0.0, 1.0]): The ratio of earned
                    completions to possible completions within the identified
                    block.

    **Parameters**

        username (optional):
            The username of the specified user for whom the course data is being
            accessed.
            If omitted, and the requesting user has staff access, then data for
            all enrolled users is returned. If the requesting user does not have
            staff access, then only data for the requesting user is returned.

        requested_fields (optional):
            A comma separated list of extra data to be returned.  This can be
            one of the block types specified in `AGGREGATE_CATEGORIES`.  If
            specified, completion data is also returned for the requested block
            types.  If any invalid fields are requested, a 400 error will be
            returned.

    **Returns**

        * 200 on success with above fields
        * 400 if an invalid value was sent for requested_fields.
        * 403 if a user who does not have permission to masquerade as another
          user specifies a username other than their own.
        * 404 if the user is not enrolled in the requested course.

        Example response:

            {
              "count": 14,
              "num_pages": 1,
              "current_page": 1,
              "start": 1,
              "next": "/api/completion/v1/course/course-v1:GeorgetownX+HUMX421-02x+1T2016/?page=2,
              "previous": None,
              "results": [
                {
                  "course_key": "course-v1:GeorgetownX+HUMX421-02x+1T2016",
                  "completion": {
                    "earned": 12.0,
                    "possible": 24.0,
                    "ratio": 0.5
                  },
                  "mean": 0.25,
                  "chapter": [
                    {
                      "course_key": "course-v1:GeorgetownX+HUMX421-02x+1T2016",
                      "block_key": "block-v1:GeorgetownX+HUMX421-02x+1T2016+type@chapter+block@Week-2-TheVitaNuova"
                      "completion": {
                        "earned: 12.0,
                        "possible": 24.0,
                        "ratio": 0.5
                      }
                    }
                  ],
                  "sequential": [
                    {
                      "course_key": "course-v1:GeorgetownX+HUMX421-02x+1T2016",
                      "block_key":
                        "block-v1:GeorgetownX+HUMX421-02x+1T2016+type@sequential+block@e0eb7cbc1a0c407e622c988",
                      "completion": {
                        "earned: 12.0,
                        "possible": 12.0,
                        "ratio": 1.0
                      }
                    },
                    {
                      "course_key": "course-v1:GeorgetownX+HUMX421-02x+1T2016",
                      "block_key":
                        "block-v1:GeorgetownX+HUMX421-02x+1T2016+type@sequential+block@f6e7ec3e965b48acf3418e7",
                      "completion": {
                        "earned: 0.0,
                        "possible": 12.0,
                        "ratio": 0.0
                      }
                    },
                },
                ...
              ]
            }

    This is a transitional implementation that uses the
    edx-solutions/progress-edx-platform-extensions models as a backing store.
    The replacement will have the same interface.
    """

    def get(self, request, course_key):
        """
        Handler for GET requests.
        """
        course_key = CourseKey.from_string(course_key)
        paginator = self.pagination_class()  # pylint: disable=not-callable
        requested_fields = self.get_requested_fields()

        if not self.requested_user and self.user.is_staff:
            # Use all enrollments for the course
            enrollments = UserEnrollments().get_course_enrollments(course_key)
            requested_fields.add('username')
        else:
            if not UserEnrollments(self.user).is_enrolled(course_key):
                # Return 404 if effective user does not have an active enrollment in the requested course
                raise NotFound()

            # Use enrollments for the effective user
            enrollments = UserEnrollments(self.user).get_course_enrollments(course_key)

        # Paginate the list of active enrollments, annotated (manually) with a student progress object.
        paginated = paginator.paginate_queryset(enrollments, self.request, view=self)
        aggregator_queryset = self.get_queryset().filter(course_key=course_key)

        # Create the list of aggregate completions to be serialized.
        completions = [
            AggregatorAdapter(
                user=enrollment.user,
                course_key=enrollment.course_id,
                queryset=aggregator_queryset,
            ) for enrollment in paginated
        ]

        # Return the paginated, serialized completions
        serializer = self.get_serializer_class()(
            instance=completions,
            requested_fields=requested_fields,
            many=True
        )
        return paginator.get_paginated_response(serializer.data)
