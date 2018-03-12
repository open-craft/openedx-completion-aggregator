"""
Models to facilitate testing
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from opaque_keys.edx.django.models import CourseKeyField, UsageKeyField

from django.db import models


class Completable(models.Model):
    """
    Local stand-in for lms.djangoapps.completion.BlockCompletion
    """
    user = models.ForeignKey('auth.User')
    course_key = CourseKeyField(max_length=255)
    block_key = UsageKeyField(max_length=255)
    completion = models.FloatField()
