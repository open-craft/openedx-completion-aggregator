"""
Configure django admin for completion_aggregator.
"""

from django.contrib import admin

from . import models


class AggregatorAdmin(admin.ModelAdmin):
    """
    Custom admin for Aggregator model.
    """

    date_hierarchy = 'modified'
    list_display = ['id', 'course_key', 'block_key', 'user', 'earned', 'possible', 'percent', 'created', 'modified']
    list_filter = ['aggregation_name']
    raw_id_fields = ['user']
    readonly_fields = ['created', 'modified']
    search_fields = ['^course_key', '^block_key', '^user__username', 'user__email']


class StaleCompletionAdmin(admin.ModelAdmin):
    """
    Custom admin for Aggregator model.
    """

    date_hierarchy = 'modified'
    list_display = ['id', 'course_key', 'block_key', 'username', 'force', 'resolved', 'created', 'modified']
    list_filter = ['resolved']
    search_fields = ['^course_key', '^block_key', '^username']


admin.site.register(models.Aggregator, AggregatorAdmin)
admin.site.register(models.StaleCompletion, StaleCompletionAdmin)
