"""
Cache wrapper that allows cache entries to be joined into groups.

Groups can be marked for manual invalidation, and all members of the group
will then be treated as if it has been removed from the cache.
"""

from collections import namedtuple
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from .models import CacheGroupInvalidation

DELETE_INVALIDATIONS_AFTER = timedelta(days=90)

_CacheGroupEntry = namedtuple('_CacheGroupEntry', ['group', 'value', 'cached_at'])


class CacheGroup(object):
    """
    Cache class that assigns cache entries to groups.

    If the group has been invalidated, all keys in its group are also
    invalidated.  This requires durable storage for the group invalidations.

    Keys are not namespaced by group, and are declared with every call to
    `CacheGroup.set`, so a cache_entry can change groups if desired.
    """

    def get(self, key):
        """
        Get an entry from the cache.

        Returns None if the entry or its group does not exist, has timed out,
        or has been invalidated.
        """
        cache_entry = cache.get(key)
        if cache_entry is None:
            return None
        invalidation = CacheGroupInvalidation.objects.filter(group=cache_entry.group).first()
        if invalidation and invalidation.invalidated_at > cache_entry.cached_at:
            return None
        return cache_entry.value

    def set(self, group, key, value, timeout):
        """
        Set an entry in the cache, assigning it to an invalidation group.
        """
        cached_at = timezone.now()

        cache_entry = _CacheGroupEntry(group, value, cached_at)
        return cache.set(key, cache_entry, timeout)

    def touch(self, key, timeout):
        """
        Update the timeout for a given key in the cache.

        Returns True if the cache key was updated.

        This functionality is available in Django 2.1 and above.
        """
        if hasattr(cache, 'touch'):
            return cache.touch(key, timeout=timeout)
        return False

    def delete(self, key):
        """
        Invalidate the entry in the cache.
        """
        return cache.delete(key)

    def delete_group(self, group):
        """
        Invalidate an entire entry from the cache.
        """
        CacheGroupInvalidation.objects.update_or_create(group=group, defaults={"invalidated_at": timezone.now()})

        # Group invalidations are expected to be relatively infrequent, so we
        # take this opportunity to clean old invalidation records out of the
        # database.

        CacheGroupInvalidation.objects.filter(invalidated_at__lt=timezone.now() - DELETE_INVALIDATIONS_AFTER).delete()
