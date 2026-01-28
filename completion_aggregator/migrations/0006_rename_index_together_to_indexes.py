# Rename indexes from index_together to Meta.indexes with explicit names.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('completion_aggregator', '0005_cachegroupinvalidation'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='aggregator',
            new_name='aggr_name_user_course_idx',
            old_fields=('user', 'aggregation_name', 'course_key'),
        ),
        migrations.RenameIndex(
            model_name='aggregator',
            new_name='aggr_name_course_block_per_idx',
            old_fields=('course_key', 'aggregation_name', 'block_key', 'percent'),
        ),
        migrations.RenameIndex(
            model_name='stalecompletion',
            new_name='stale_user_course_resolved_idx',
            old_fields=('username', 'course_key', 'created', 'resolved'),
        ),
    ]
