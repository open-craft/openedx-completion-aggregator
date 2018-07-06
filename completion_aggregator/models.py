# -*- coding: utf-8 -*-
"""
Database models for completion aggregator.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from opaque_keys.edx.django.models import CourseKeyField, UsageKeyField
from opaque_keys.edx.keys import CourseKey, UsageKey

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import pre_save
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext as _

from model_utils.models import TimeStampedModel


def validate_percent(value):
    """
    Verify that the passed value is between 0.0 and 1.0.
    """
    if not 0.0 <= value <= 1.0:
        raise ValidationError(_('{value} must be between 0.0 and 1.0').format(value=value))


def validate_positive_float(value):
    """
    Verify that the passed in value is greater than 0.
    """
    if value < 0.0:
        raise ValidationError(_('{value} must be larger than 0.').format(value=value))


class AggregatorManager(models.Manager):
    """
    Custom manager for Aggregator model.
    """

    def validate(self, user, course_key, block_key):
        """
        Perform validation.

        Parameters
        ----------
        * user (django.contrib.auth.models.User):
        * course_key (opaque_keys.edx.keys.CourseKey):
        * block_key (opaque_keys.edx.keys.UsageKey):

        Raises
        ------
        TypeError:
            If the wrong type is passed for the parameters.

        """
        if not isinstance(user, User):
            raise TypeError(
                _("user must be an instance of `django.contrib.auth.models.User`.  Got {}".format(
                    type(user)
                ))
            )
        if not isinstance(course_key, CourseKey):
            raise TypeError(
                _("course_key must be an instance of `opaque_keys.edx.keys.CourseKey`.  Got {}".format(
                    type(course_key)
                ))
            )
        if not isinstance(block_key, UsageKey):
            raise TypeError(
                _("block_key must be an instance of `opaque_keys.edx.keys.UsageKey`.  Got {}".format(
                    type(block_key)
                ))
            )

    @staticmethod
    def pre_save(sender, instance, **kwargs):  # pylint: disable=unused-argument
        """
        Validate all fields before saving to database.
        """
        instance.full_clean()

    def submit_completion(self, user, course_key, block_key, aggregation_name, earned, possible, last_modified):
        """
        Insert and Update the completion Aggregator for the specified record.

        Parameters
        ----------
        * user (django.contrib.auth.models.User): The user for whom the
          completion is being submitted.
        * course_key (opaque_keys.edx.keys.CourseKey): The course in
          which the submitted block is found.
        * block_key (opaque_keys.edx.keys.UsageKey): The block that has had
          its completion changed.
        * aggregation_name (string): The name of the aggregated blocks.
          This is set by the level that the aggregation
          is occurring. Possible values include "course", "chapter",
          "sequential", "vertical"
        * earned (float): The positive sum of the fractional completions of all
          descendant blocks up to the value of possible.
        * possible (float): The total sum of the possible completion values of
          all descendant blocks that are visible to the user. This should be a
          positive integer.
        * last_modified (datetime): When the aggregator's blocks were most
          recently updated.  Note this is different from the value of
          `Aggregator.modified`, which is inherited from TimestampedModel, and
          always updates to the current time when the model is updated.  This
          instead reflects the most recent modification time of the
          BlockCompletion objects it represents.  This is to prevent race
          conditions that might cause the Aggregator to miss updates.

        Return Value
        ------------
        (Aggregator, bool)
            A tuple comprising the created or updated Aggregator object and a
            boolean value indicating whether the object was newly created by
            this call.

        Raises
        ------
        TypeError:
            If the wrong type is passed for the parameters.

        ValueError:
            If the value of earned is greater than possible.

        django.core.exceptions.ValidationError:
            If earned / possible results in a number that is less than 0 or
            greater than 1 or any float is less than zero.

        django.db.DatabaseError:
            If there was a problem getting, creating, or updating the
            BlockCompletion record in the database.  This will also be a more
            specific error, as described at
            https://docs.djangoproject.com/en/1.11/ref/exceptions/#database-exceptions.
            IntegrityError and OperationalError are relatively common
            subclasses.

        """
        self.validate(user, course_key, block_key)
        if earned > possible:
            raise ValueError(_('Earned cannot be greater than the possible value.'))
        if possible > 0.0:
            percent = earned / possible
        else:
            percent = 1.0
        obj, is_new = self.update_or_create(
            user=user,
            course_key=course_key,
            aggregation_name=aggregation_name,
            block_key=block_key,
            defaults={
                'percent': percent,
                'possible': possible,
                'earned': earned,
                'last_modified': last_modified,
            },
        )
        return obj, is_new


@python_2_unicode_compatible
class Aggregator(TimeStampedModel):
    """
    Aggregators are blocks that contain other blocks, are not themselves completable.

    They are considered 100% complete when all descendant blocks are complete.
    """

    user = models.ForeignKey(User)
    course_key = CourseKeyField(max_length=255)
    aggregation_name = models.CharField(max_length=255)
    block_key = UsageKeyField(max_length=255)
    earned = models.FloatField(validators=[validate_positive_float])
    possible = models.FloatField(validators=[validate_positive_float])
    percent = models.FloatField(validators=[validate_percent])
    last_modified = models.DateTimeField()

    objects = AggregatorManager()

    class Meta(object):
        """
        Metadata describing the Aggregator model.
        """

        index_together = [
            ('user', 'aggregation_name', 'course_key'),
            ('course_key', 'aggregation_name', 'block_key', 'percent'),
        ]

        unique_together = [
            ('course_key', 'block_key', 'user', 'aggregation_name')
        ]

    def __str__(self):
        """
        Get a string representation of this model instance.
        """
        return 'Aggregator: {username}, {course_key}, {block_key}: {percent}'.format(
            username=self.user.username,
            course_key=self.course_key,
            block_key=self.block_key,
            percent=self.percent,
        )

    @classmethod
    def block_is_registered_aggregator(cls, block_key):
        """
        Return True if the block is registered to aggregate completions.
        """
        return block_key.block_type in settings.COMPLETION_AGGREGATOR_BLOCK_TYPES


pre_save.connect(
    AggregatorManager.pre_save,
    Aggregator,
    dispatch_uid="completion.models.Aggregator"
)


@python_2_unicode_compatible
class StaleCompletion(TimeStampedModel):
    """
    Tracking model for aggregation work that needs to be done.
    """

    username = models.CharField(max_length=255)
    course_key = CourseKeyField(max_length=255)
    block_key = UsageKeyField(max_length=255, null=True, blank=True)
    force = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)

    def __str__(self):
        """
        Render the StaleCompletion.
        """
        parts = ['{}/{}'.format(self.username, self.course_key)]
        if self.block_key:
            parts.append('/{}'.format(self.block_key))
        if self.resolved:
            parts.append('*')
        return ''.join(parts)
