"""
API views to read completion information.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from opaque_keys.edx.keys import CourseKey
from rest_framework import status
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.contrib.auth import get_user_model

from ...models import Aggregator
from ...serializers import CourseAggregationAdapter, course_completion_serializer_factory, is_aggregation_name

User = get_user_model()  # pylint: disable=invalid-name


class UserEnrollments(object):
    """
    Class for managing user enrollments
    """
    def __init__(self, user):
        self.user = user

    def get_enrollments(self):  # pragma: no cover
        """
        Return a collection CourseEnrollments.

        The collection must have a .__len__() attribute, be sliceable,
        and consist of objects that have a user attribute and a course_id
        attribute.
        """

        from student.models import CourseEnrollment  # pylint: disable=import-error
        return CourseEnrollment.objects.filter(user=self.user, is_active=True).order_by('course_id')

    def is_enrolled(self, course_key):  # pragma: no cover
        """
        Return a boolean stating whether user is enrolled in the named course.
        """
        from student.models import CourseEnrollment  # pylint: disable=import-error
        return CourseEnrollment.objects.filter(user=self.user, course_id=course_key, is_active=True).exists()


class CompletionViewMixin(object):
    """
    Common functionality for completion views.
    """

    _allowed_requested_fields = {'mean'}
    permission_classes = (IsAuthenticated,)
    _user = None

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
    def user(self):
        """
        Return the effective user.

        Usually the requesting user, but a staff user can override this.
        """
        if self._user:
            return self._user

        requested_username = self.request.GET.get('username')
        if not requested_username:
            user = self.request.user
            print(user, user.is_authenticated())
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
        self._user = user
        return self._user

    def get_queryset(self):
        """
        Build a base queryset of relevant course-level Aggregator objects.
        """
        aggregations = {'course'}
        aggregations.update(category for category in self.get_requested_fields() if is_aggregation_name(category))
        return Aggregator.objects.filter(user=self.user, aggregation_name__in=aggregations)

    # TODO: Coverage will be added when dummy values get used
    def create_dummy_aggregation(self, course_key):  # pragma: no cover
        """
        Build an empty StudentProgress object for the current user and given course.
        """
        return Aggregator(
            user=self.user,
            course_key=course_key,
            usage_key=course_key.make_usage_key(block_type='course', block_id='xxx'),
            aggregation_name='course',
            earned=0.0,
            possible=0.0,  # How to get the right value for this?
        )

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

    def get_serializer(self):
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

        * pagination: A dict of pagination information, containing the fields:
            * page: The page number of the current set of results.
            * next: The URL for the next page of results, or None if already on
              the last page.
            * previous: The URL for the previous page of results, or None if
              already on the first page.
            * count: The total number of available results.
        * results: A list of dictionaries representing the user's completion
          for each course.

        Standard fields for each completion dictionary:

        * completion: A dictionary comprising of the following fields:
            * earned (float): The sum of the learner's completions.
            * possible (float): The total number of completions available
              in the course.
            * ratio (float in the range [0.0, 1.0]): The ratio of earned
              completions to possible completions in the course.

        Optional fields, as requested in "requested_fields":

        * mean (float): The average completion ratio for all students enrolled
          in the course.
        * Aggregations: The actual fields available are configurable, but
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
              "pagination": {
                "count": 14,
                "page": 1,
                "next": "/api/completion/v1/course/?page=2,
                "previous": None
              },
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

    @property
    def pagination_class(self):  # pragma: no cover
        """
        Return the class to use for pagination
        """
        from openedx.core.lib.api import paginators  # pylint: disable=import-error
        return paginators.NamespacedPageNumberPagination

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
        aggregations_queryset = self.get_queryset().filter(
            course_key__in=course_keys
        )

        # Create the list of aggregate completions to be serialized.
        completions = [
            CourseAggregationAdapter(
                user=self.user,
                course_key=enrollment.course_id,
                queryset=aggregations_queryset,
            ) for enrollment in paginated
        ]

        # Return the paginated, serialized completions
        serializer = self.get_serializer()(
            instance=completions,
            requested_fields=self.get_requested_fields(),
            many=True
        )
        return paginator.get_paginated_response(serializer.data)


class CompletionDetailView(CompletionViewMixin, APIView):
    # pylint: disable=line-too-long
    """
    API view to render a serialized CourseCompletion for a single user in a
    single course.

    **Request Format**

        GET /api/completion/v1/course/<course_key>/

    **Example Requests**

        GET /api/completion/v1/course/course-v1:GeorgetownX+HUMX421-02x+1T2016/
        GET /api/completion/v1/course/course-v1:edX+DemoCourse+Demo2017/?requested_fields=chapter,vertical

    **Response Values**

        Standard fields:

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
            The username of the specified user for whom the course data is
            being accessed.  If not specified, this defaults to the requesting
            user.

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
                  "block_key": "block-v1:GeorgetownX+HUMX421-02x+1T2016+type@sequential+block@e0eb7cbc1a0c407e622c988",
                  "completion": {
                    "earned: 12.0,
                    "possible": 12.0,
                    "ratio": 1.0
                  }
                },
                {
                  "course_key": "course-v1:GeorgetownX+HUMX421-02x+1T2016",
                  "block_key": "block-v1:GeorgetownX+HUMX421-02x+1T2016+type@sequential+block@f6e7ec3e965b48acf3418e7",
                  "completion": {
                    "earned: 0.0,
                    "possible": 12.0,
                    "ratio": 0.0
                  }
                }
              ]
            }

    This is a transitional implementation that uses the
    edx-solutions/progress-edx-platform-extensions models as a backing store.
    The replacement will have the same interface.
    """
    # pylint: enable=line-too-long

    def get(self, request, course_key):
        """
        Handler for GET requests.
        """
        course_key = CourseKey.from_string(course_key)

        # Return 404 if user does not have an active enrollment in the requested course
        if not UserEnrollments(self.user).is_enrolled(course_key):
            return Response(status=status.HTTP_404_NOT_FOUND)

        try:
            # Fetch the Aggregate completions for the course
            completion = self.get_queryset().filter(course_key=course_key)
        except Aggregator.DoesNotExist:
            # Otherwise, use an empty, unsaved Aggregation object
            # TODO: Coverage will be added when test_detail_view_no_completion is supported
            completion = self.create_dummy_aggregation(course_key)  # pragma: no cover

        aggregation = CourseAggregationAdapter(
            user=self.user,
            course_key=course_key,
        )
        aggregation.update_aggregators(completion)
        return Response(self.get_serializer()(aggregation, requested_fields=self.get_requested_fields()).data)
