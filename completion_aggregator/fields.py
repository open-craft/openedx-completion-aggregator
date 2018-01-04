"""
Custom django fields.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import six
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey, UsageKey

from django.db import models


class OpaqueKeyField(models.Field):
    """
    Abstract class for defining database fields that represent opaque key types.
    """

    @property
    def key_type(self):
        """
        Return the OpaqueKey subclass used to create keys.
        """
        raise NotImplementedError  # pragma: no cover

    def __init__(self, *args, **kwargs):
        """
        Abstract class for defining database fields that represent opaque key types.
        """
        if 'max_length' not in kwargs:
            kwargs['max_length'] = 255
        super(OpaqueKeyField, self).__init__(*args, **kwargs)

    def deconstruct(self):
        """
        Return the arguments required to recreate this object.
        """
        name, path, args, kwargs = super(OpaqueKeyField, self).deconstruct()
        if kwargs['max_length'] == 255:
            del kwargs['max_length']
        return name, path, args, kwargs

    def db_type(self, connection):
        """
        Return the type of this column as seen by the database.
        """
        return "VARCHAR({})".format(self.max_length)

    def get_prep_value(self, value):
        """
        Convert the OpaqueKey to a string for insertion into the database.
        """
        if isinstance(value, self.key_type):
            return six.text_type(value)
        elif isinstance(value, six.text_type):
            try:
                self.key_type.from_string(value)
            except InvalidKeyError:
                raise TypeError("{!r} is not a valid {}".format(value, self.key_type))
            return value
        elif value is None:
            return value
        raise TypeError("{!r} must be a {} or a unicode string".format(value, self.key_type))

    def from_db_value(self, value, _expression, _connection, _context):
        """
        Convert the value from the database to an OpaqueKey, suitable for using in python code.
        """
        if value is None:
            return value
        return self.key_type.from_string(value)


class CourseKeyField(OpaqueKeyField):
    """
    Database field for CourseKeys.
    """

    key_type = CourseKey


class UsageKeyField(OpaqueKeyField):
    """
    Database field for UsageKeys.
    """

    key_type = UsageKey
