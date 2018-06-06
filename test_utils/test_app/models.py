"""
Models to be used in tests
"""
from __future__ import absolute_import, unicode_literals

from opaque_keys.edx.django.models import CourseKeyField

from django.conf import settings
from django.db import models


class CourseEnrollment(models.Model):
    """
    Provides an equivalent for the edx-platform CourseEnrollment model.
    """
    is_active = models.BooleanField(default=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    course_id = CourseKeyField(max_length=255)
