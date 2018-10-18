"""
API views to read completion information.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from collections import defaultdict

from opaque_keys.edx.keys import CourseKey
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from ... import compat
from ...serializers import AggregatorAdapter
from ..common import CompletionViewMixin, UserEnrollments


class CompletionListView(CompletionViewMixin, APIView):
    """
    API view to render serialized CourseCompletions for a single user
    across all enrolled courses.

    **Example Requests**

        GET /api/completion/v0/course/
        GET /api/completion/v0/course/?requested_fields=chapter,vertical

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
            one of the block types specified in `AGGREGATE_CATEGORIES` (except
            `course`), or any of the other optional fields specified above.
            If any invalid fields are requested, a 400 error will be returned.

        mobile_only (optional):
            A value of "true" will provide only completions that come from
            mobile courses.

    **Returns**

        * 200 on success with above fields
        * 400 if an invalid value was sent for requested_fields.
        * 403 if a user who does not have permission to masquerade as another
          user specifies a username other than their own.
        * 404 if the course is not available or the requesting user can see no
          completable sections.

        Example response:

            GET /api/course

            {
              "pagination": {
                "count": 14,
                "page": 1,
                "next": "/api/completion/v0/course/?page=2,
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
    """

    def get(self, request):
        """
        Handler for GET requests.
        """
        if 'username' not in request.query_params and not request.user.is_staff:
            self._effective_user = request.user

        paginator = self.pagination_class()  # pylint: disable=not-callable
        mobile_only = (self.request.query_params.get('mobile_only', 'false')).lower() == 'true'

        # Paginate the list of active enrollments, annotated (manually) with a student progress object.
        enrollments = UserEnrollments(self.user).get_enrollments()

        if mobile_only:
            enrollments = compat.get_mobile_only_courses(enrollments)

        paginated = paginator.paginate_queryset(enrollments, self.request, view=self)

        # Grab the progress items for these enrollments
        course_keys = [enrollment.course_id for enrollment in paginated]
        aggregator_queryset = self.get_queryset().filter(
            user=self.user,
            course_key__in=course_keys
        )
        aggregators_by_enrollment = defaultdict(list)
        for agg in aggregator_queryset:
            aggregators_by_enrollment[self.user, agg.course_key].append(agg)

        # Create the list of aggregate completions to be serialized,
        # recalculating any stale completions for this single user.
        completions = [
            AggregatorAdapter(
                user=self.user,
                course_key=enrollment.course_id,
                aggregators=aggregators_by_enrollment[self.user, enrollment.course_id],
                recalculate_stale=True,
            ) for enrollment in paginated
        ]

        # Return the paginated, serialized completions
        serializer = self.get_serializer_class(version=0)(
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

        GET /api/completion/v0/course/<course_key>/

    **Example Requests**

        GET /api/completion/v0/course/course-v1:GeorgetownX+HUMX421-02x+1T2016/
        GET /api/completion/v0/course/course-v1:edX+DemoCourse+Demo2017/?requested_fields=chapter,vertical

    **Response Values**

        Standard fields:

        * course_key (CourseKey): The unique course identifier.
        * completion: A dictionary comprising of the following fields:
            * earned (float): The sum of the learner's completions.
            * possible (float): The total number of completions available
              in the course.
            * ratio (float in the range [0.0, 1.0]): The ratio of earned
              completions to possible completions in the course.

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
                  "block_key": "block-v1:GeorgetownX+HUMX421-02x+1T2016+type@sequential+block@e0eb7cbc1a0c4000bec36b67e622c988",
                  "completion": {
                    "earned: 12.0,
                    "possible": 12.0,
                    "ratio": 1.0
                  }
                },
                {
                  "course_key": "course-v1:GeorgetownX+HUMX421-02x+1T2016",
                  "block_key": "block-v1:GeorgetownX+HUMX421-02x+1T2016+type@sequential+block@f6e7ec3e965b48428197196acf3418e7",
                  "completion": {
                    "earned: 0.0,
                    "possible": 12.0,
                    "ratio": 0.0
                  }
                }
              ]
            }
    """
    # pylint: enable=line-too-long

    def get(self, request, course_key):
        """
        Handler for GET requests.
        """
        if 'username' not in request.query_params and not request.user.is_staff:
            self._effective_user = request.user

        course_key = CourseKey.from_string(course_key)

        # Return 404 if user does not have an active enrollment in the requested course
        if not UserEnrollments(self.user).is_enrolled(course_key):
            # Return 404 if effective user does not have an active enrollment in the requested course
            raise NotFound()
        requested_fields = self.get_requested_fields()
        enrollment = UserEnrollments(self.user).get_course_enrollment(course_key)
        aggregator_queryset = self.get_queryset().filter(
            course_key=course_key,
            user=self.user,
        )

        # Create the list of aggregate completions to be serialized,
        # recalculating any stale completions for this single user.
        completions = AggregatorAdapter(
            user=enrollment.user,
            course_key=enrollment.course_id,
            aggregators=aggregator_queryset,
            recalculate_stale=True,
        )

        # Return the paginated, serialized completions
        serializer = self.get_serializer_class(version=0)(
            instance=completions,
            requested_fields=requested_fields,
        )
        return Response(serializer.data)
