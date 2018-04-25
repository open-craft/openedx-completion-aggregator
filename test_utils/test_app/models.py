"""
Models to be used in tests
"""
from __future__ import absolute_import, unicode_literals

from opaque_keys.edx.django.models import CourseKeyField

from django.contrib.auth import get_user_model
from django.db import models


class CourseEnrollment(models.Model):
    """
    Provides an equivalent for the edx-platform CourseEnrollment model.
    """
    is_active = models.BooleanField(default=True)
    user = models.ForeignKey(get_user_model())
    course_id = CourseKeyField(max_length=255)
