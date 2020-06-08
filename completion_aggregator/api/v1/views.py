"""
API views to read completion information.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import re
from collections import defaultdict

import waffle
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey, UsageKey
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.views import APIView

from django.db.models import Avg, Sum
from django.http import JsonResponse

from ... import compat, serializers
from ...models import StaleCompletion
from ...utils import WAFFLE_AGGREGATE_STALE_FROM_SCRATCH
from ..common import CompletionViewMixin, UserEnrollments


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
            being accessed. If not specified, this will show data for all users
            if requested by a staff user, otherwise it will throw a 403 Error.

        requested_fields (optional):
            A comma separated list of extra data to be returned.  This can be
            one of the block types specified in `AGGREGATE_CATEGORIES`, or any of
            the other optional fields specified above.  If any invalid fields
            are requested, a 400 error will be returned.

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
    """
    course_completion_serializer = serializers.CourseCompletionSerializer
    block_completion_serializer = serializers.BlockCompletionSerializer

    def get(self, request):
        """
        Handler for GET requests.
        """
        paginator = self.pagination_class()  # pylint: disable=not-callable
        mobile_only = self.request.query_params.get('mobile_only', 'false').lower() == 'true'

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
            aggregators_by_enrollment[agg.user, agg.course_key].append(agg)

        # Create the list of aggregate completions to be serialized,
        # recalculating any stale completions for this single user.
        completions = [
            serializers.AggregatorAdapter(
                user=self.user,
                course_key=enrollment.course_id,
                aggregators=aggregators_by_enrollment[self.user, enrollment.course_id],
                recalculate_stale=True,
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
    API view to render serialized aggregators for a single course.

    **Request Format**

        GET /api/completion/v1/course/<course_key>/
        or
        POST /api/completion/v1/course/<course_key>/
        With filters on the body of the request:
        {
            "user_ids": [1,2,3,5],
            "requested_fields": ["chapter", "vertical"],
            "root_block": "root_block",
            "username": "username"
        }

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
            accessed. If non-staff users try to access another user's data they
            will get a 403 Error.
            If omitted, and the requesting user has staff access, then data for
            all enrolled users is returned. If the requesting user does not have
            staff access, it will return a 403 Error.

        root_block (optional):
            Get aggregators under a certain block, not for the whole course.

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
    """
    course_completion_serializer = serializers.CourseCompletionSerializer
    block_completion_serializer = serializers.BlockCompletionSerializer

    def _parse_aggregator(self, course_key, params=None):
        """
        Handles fetching and return aggregator data, regardless of the method used
        """
        try:
            course_key = CourseKey.from_string(course_key)
        except InvalidKeyError:
            raise NotFound("Invalid course key: '{}'.".format(course_key))
        paginator = self.pagination_class()  # pylint: disable=not-callable
        requested_fields = self.get_requested_fields()

        # Recalculate stale completions only if a single user's data was requested.
        recalculate_stale = True

        if not self.requested_user and self.user.is_staff:
            # Use all enrollments for the course
            enrollments = UserEnrollments().get_course_enrollments(course_key)
            requested_fields.add('username')
            recalculate_stale = False
            is_stale = False
        else:
            if not UserEnrollments(self.user).is_enrolled(course_key):
                # Return 404 if effective user does not have an active enrollment in the requested course
                raise NotFound(
                    "User '{user}' does not have an active enrollment in course '{course_key}'."
                    .format(user=self.user, course_key=course_key)
                )
            is_stale = StaleCompletion.objects.filter(
                username=self.user.username,
                course_key=course_key,
                resolved=False,
            ).exists()

            # Use enrollments for the effective user
            enrollments = UserEnrollments(self.user).get_course_enrollments(course_key)

        user_ids = params.get('user_ids')
        if user_ids:
            enrollments = enrollments.filter(user_id__in=user_ids)
        # Paginate the list of active enrollments, annotated (manually) with a student progress object.
        paginated = paginator.paginate_queryset(enrollments.select_related('user'), self.request, view=self)

        root_block = params.get('root_block')
        if root_block:
            try:
                root_block = UsageKey.from_string(root_block).map_into_course(course_key)
            except InvalidKeyError:
                raise NotFound("Invalid block key: '{}'.".format(root_block))

        if is_stale and waffle.flag_is_active(self.request, WAFFLE_AGGREGATE_STALE_FROM_SCRATCH):
            aggregator_queryset = []
        else:
            aggregator_queryset = self.get_queryset().filter(
                course_key=course_key,
                user__in=[enrollment.user for enrollment in paginated],
            ).select_related('user')
        aggregators_by_user = defaultdict(list)
        for aggregator in aggregator_queryset:
            aggregators_by_user[aggregator.user_id].append(aggregator)
        # Create the list of aggregate completions to be serialized.
        completions = [
            serializers.AggregatorAdapter(
                user=enrollment.user,
                course_key=enrollment.course_id,
                aggregators=aggregators_by_user[enrollment.user_id],
                root_block=root_block,
                recalculate_stale=recalculate_stale,
            ) for enrollment in paginated
        ]

        # Return the paginated, serialized completions
        serializer = self.get_serializer_class()(
            instance=completions,
            requested_fields=requested_fields,
            many=True
        )
        return paginator.get_paginated_response(serializer.data)

    def get(self, request, course_key):
        """
        Handler for GET requests.
        """
        params = {}
        if request.query_params.get('user_ids'):
            params['user_ids'] = (int(id) for id in re.split(r'[,.]', request.query_params['user_ids']))

        params['root_block'] = request.query_params.get('root_block')

        return self._parse_aggregator(course_key, params)

    def post(self, request, course_key):
        """
        Handler for POST requests.
        """
        params = {
            'user_ids': request.data.get('user_ids'),
            'root_block': request.data.get('root_block'),
        }

        return self._parse_aggregator(course_key, params)


class CourseLevelCompletionStatsView(CompletionViewMixin, APIView):
    """
    API view to render stats for a single course.

    **Request Format**

        GET /api/completion/v1/stats/<course_key>/

    **Example Requests**

        GET /api/completion/v1/stats/edX/toy/2012_Fall/
        GET /api/completion/v1/stats/edX/toy/2012_Fall/?exclude_roles=beta,staff
        GET /api/completion/v1/stats/edX/toy/2012_Fall/?cohorts=1&exclude_roles=staff

    **Response Values**

        The response is a dictionary comprising the course key and a result
        of the mean completion of said course key.

        * course_key (CourseKey): The unique course identifier.
        * results (list): A list currently only containing the mean completion
            of all selected users in the course.
            * mean_completion: a dictionary containing the following fields:
                * earned (float): The average completion achieved by all
                    selected students in the course.
                * possible (float): The total number of completions available
                    in the course.
                * percent (float in the range [0.0, 1.0]): The percentage of
                    earned completions.
        * filters: A dictionary containing fields based on parameters.
            Possible fields are:
            * cohorts (int): The id of the requested cohort. Users should at
                least be a member of this cohort to be included in the result.
            * exclude_roles (list): Members of any of the listed roles should
                be excluded from the total results.
                If no roles are excluded, include all active learners in the
                result.

    **Parameters**
        cohorts (int):
            Specify the cohorts for which to fetch the results.
            Currently limited to a single cohort, but likely to be expanded
            later.

        exclude_roles (optional):
            A comma separated list of roles to exclude from the results.

    **Returns**

        * 200 on success with above fields
              (this includes the case if the course is not cohorted).
        * 400 if an invalid value was sent for requested_fields and cohorts,

        Example response:

            {
                "results": [
                    {
                        "course_key": "edX/toy/2012_Fall",
                        "mean_completion": {
                            "earned": 3.4,
                            "possible": 8.0,
                            "percent": 0.425
                        }
                    }
                ]
            }

    """
    course_completion_serializer = serializers.CourseCompletionStatsSerializer
    block_completion_serializer = serializers.BlockCompletionSerializer

    def _parse_cohort_filter(self, cohort_filter):
        """
        Helper function to parse cohort filter query parameter.
        """
        if cohort_filter is not None:
            try:
                cohort_filter = int(cohort_filter)
            except TypeError:
                raise ParseError(
                    'could not parse cohort_filter={!r} as an integer'.format(
                        cohort_filter,
                    )
                )
        return cohort_filter

    def get(self, request, course_key):
        """
        Handler for GET requests
        """
        try:
            course_key = CourseKey.from_string(course_key)
        except InvalidKeyError:
            raise NotFound("Invalid course key: '{}'.".format(course_key))
        requested_fields = self.get_requested_fields()
        roles_to_exclude = self.request.query_params.get('exclude_roles', '').split(',')
        cohort_filter = self._parse_cohort_filter(
            self.request.query_params.get('cohorts'))
        enrollments = UserEnrollments().get_course_enrollments(course_key)
        if roles_to_exclude:
            enrollments = enrollments.exclude(
                user__courseaccessrole__role__in=roles_to_exclude)
        if cohort_filter is not None:
            enrollments = enrollments.exclude(
                user__cohortmembership__course_user_group__pk=cohort_filter)
        aggregator_qs = self.get_queryset().filter(
            course_key=course_key,
            aggregation_name='course',
            user_id__in=[enrollment.user_id for enrollment in enrollments])
        completion_stats = aggregator_qs.aggregate(
            possible=Avg('possible'),
            earned=Sum('earned') / len(enrollments),
            percent=Sum('earned') / (Avg('possible') * len(enrollments)))
        completion_stats['course_key'] = course_key

        serializer = self.get_serializer_class()(
            instance=completion_stats,
            requested_fields=requested_fields,
        )

        return JsonResponse({'results': [serializer.data]}, status=200)
