"""
Asynchronous tasks for performing aggregation of completions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from celery import shared_task
from celery_utils.logged_task import LoggedTask
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey, UsageKey

from django.contrib.auth.models import User
from django.db import connection

from .. import core
from ..models import StaleCompletion

try:
    from progress.models import CourseModuleCompletion
    PROGRESS_IMPORTED = True
except ImportError:
    PROGRESS_IMPORTED = False


# SQLite doesn't support the ON DUPLICATE KEY syntax.  INSERT OR REPLACE will
# have a similar effect, but uses new primary keys.  The drawbacks of this are:
# * It will consume the available keyspace more quickly.
# * It will not preserve foreign keys pointing to our table.
# SQLite is only used in testing environments, so neither of these drawbacks
# poses an actual problem.

INSERT_OR_UPDATE_MYSQL = """
    INSERT INTO completion_blockcompletion
        (user_id, course_key, block_key, block_type, completion)
    VALUES
        (%s, %s, %s, %s, 1.0)
    ON DUPLICATE KEY UPDATE
        completion=VALUES(completion);
"""

INSERT_OR_UPDATE_SQLITE = """
    INSERT OR REPLACE
    INTO completion_blockcompletion
        (user_id, course_key, block_key, block_type, completion)
    VALUES
        (%s, %s, %s, %s, 1.0);
"""


log = logging.getLogger(__name__)


@shared_task(task=LoggedTask)
def update_aggregators(username, course_key, block_keys=(), force=False):
    """
    Update aggregators for the specified enrollment (user + course).

    Parameters
    ----------
        username (str):
            The user whose aggregators need updating.
        course_key (str):
            The course in which the aggregators need updating.
        block_key (list[str]):
            A list of completable blocks that have changed.
        force (bool):
            If True, update aggregators even if they are up-to-date.

    Takes a collection of block_keys that have been updated, to enable future
    optimizations in how aggregators are recalculated.
    """
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        log.warning("User %s does not exist.  Marking stale completions resolved.", username)
        StaleCompletion.objects.filter(username=username).update(resolved=True)
        return

    course_key = CourseKey.from_string(course_key)
    block_keys = set(UsageKey.from_string(key).map_into_course(course_key) for key in block_keys)
    log.info("Updating aggregators in %s for %s. Changed blocks: %s", course_key, user.username, block_keys)
    return core.update_aggregators(user, course_key, block_keys, force)


@shared_task
def migrate_batch(start, stop):  # Cannot pass a queryset to a task.
    """
    Convert a batch of CourseModuleCompletions to BlockCompletions.

    Given a starting ID and a stopping ID, this task will:

    * Fetch all CourseModuleCompletions with an ID in range(start_id, stop_id).
    * Update the BlockCompletion table with those CourseModuleCompletion
      records.
    """
    if not PROGRESS_IMPORTED:
        log.error("Cannot perform migration: CourseModuleCompletion not importable.")

    queryset = CourseModuleCompletion.objects.all().select_related('user')
    course_module_completions = queryset.filter(id__gte=start, id__lt=stop)

    processed = {}  # Dict has format: {course: {user: [blocks]}
    insert_params = []
    for cmc in course_module_completions:
        try:
            course_key = CourseKey.from_string(cmc.course_id)
            block_key = UsageKey.from_string(cmc.content_id).map_into_course(course_key)
            block_type = block_key.block_type
        except InvalidKeyError:
            log.exception(
                "Could not migrate CourseModuleCompletion with values: %s",
                cmc.__dict__,
            )
            continue
        if course_key not in processed:
            processed[course_key] = set()
        if cmc.user not in processed[course_key]:
            processed[course_key].add(cmc.user)
        # Param order: (user_id, course_key, block_key, block_type)
        insert_params.append((cmc.user_id, cmc.course_id, cmc.content_id, block_type))
    if connection.vendor == 'mysql':
        sql = INSERT_OR_UPDATE_MYSQL
    else:
        sql = INSERT_OR_UPDATE_SQLITE
    with connection.cursor() as cur:
        cur.executemany(sql, insert_params)
    # Create aggregators later.
    stale_completions = []
    for course_key in processed:
        for user in processed[course_key]:
            stale_completions.append(
                StaleCompletion(
                    username=user.username,
                    course_key=course_key,
                    block_key=None,
                    force=True
                )
            )
    StaleCompletion.objects.bulk_create(
        stale_completions,
    )
    log.info("Completed progress migration batch from %s to %s", start, stop)
