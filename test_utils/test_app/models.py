"""
Models to be used in tests
"""
from __future__ import absolute_import, unicode_literals

from opaque_keys.edx.django.models import CourseKeyField

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models

from model_utils.models import TimeStampedModel

User = get_user_model()


class CourseEnrollment(models.Model):
    """
    Provides an equivalent for the edx-platform CourseEnrollment model.
    """
    class Meta:
        app_label = "test_app"

    is_active = models.BooleanField(default=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.DO_NOTHING)
    course_id = CourseKeyField(max_length=255)

    @classmethod
    def is_enrolled(cls, user, course_id):
        """
        Return True if the specified enrollment exists.
        """
        return cls.objects.filter(is_active=True, user=user, course_id=course_id).exists()


class CourseAccessRole(models.Model):
    """
    Maps users to org, courses, and roles. Used by student.roles.CourseRole and OrgRole.
    To establish a user as having a specific role over all courses in the org, create an entry
    without a course_id.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    # blank org is for global group based roles such as course creator (may be deprecated)
    org = models.CharField(max_length=64, db_index=True, blank=True)
    # blank course_id implies org wide role
    course_id = CourseKeyField(max_length=255, db_index=True, blank=True)
    role = models.CharField(max_length=64, db_index=True)

    class Meta:
        unique_together = ('user', 'org', 'course_id', 'role')
        app_label = "test_app"


class CourseUserGroup(models.Model):
    """
    This model represents groups of users in a course.  Groups may have different types,
    which may be treated specially.  For example, a user can be in at most one cohort per
    course, and cohorts are used to split up the forums by group.
    """
    class Meta:
        unique_together = (('name', 'course_id'), )
        app_label = "test_app"

    name = models.CharField(max_length=255,
                            help_text=("What is the name of this group?  "
                                       "Must be unique within a course."))
    users = models.ManyToManyField(User, db_index=True, related_name='course_groups',
                                   help_text="Who is in this group?")

    # Note: groups associated with particular runs of a course.  E.g. Fall 2012 and Spring
    # 2013 versions of 6.00x will have separate groups.
    course_id = CourseKeyField(
        max_length=255,
        db_index=True,
        help_text="Which course is this group associated with?",
    )

    # For now, only have group type 'cohort', but adding a type field to support
    # things like 'question_discussion', 'friends', 'off-line-class', etc
    COHORT = 'cohort'  # If changing this string, update it in migration 0006.forwards() as well
    GROUP_TYPE_CHOICES = ((COHORT, 'Cohort'),)
    group_type = models.CharField(max_length=20, choices=GROUP_TYPE_CHOICES)


class CohortMembership(models.Model):
    """Used internally to enforce our particular definition of uniqueness"""

    course_user_group = models.ForeignKey(CourseUserGroup, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    course_id = CourseKeyField(max_length=255)

    class Meta:
        unique_together = (('user', 'course_id'), )
        app_label = "test_app"

# Copied over from https://github.com/edx-solutions/progress-edx-platform-extensions/blob/master/progress/models.py


class CourseModuleCompletion(TimeStampedModel):
    """
    The CourseModuleCompletion model contains user, course, module information
    to monitor a user's progression throughout the duration of a course,
    we need to observe and record completions of the individual course modules.
    """
    user = models.ForeignKey(User, db_index=True, related_name="course_completions", on_delete=models.DO_NOTHING)
    course_id = models.CharField(max_length=255, db_index=True)
    content_id = models.CharField(max_length=255, db_index=True)
    stage = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'progress_coursemodulecompletion'
        app_label = "test_app"
