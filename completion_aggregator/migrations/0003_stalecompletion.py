# -*- coding: utf-8 -*-
# Generated by Django 1.11.10 on 2018-04-27 18:23
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone
import model_utils.fields
import opaque_keys.edx.django.models


class Migration(migrations.Migration):

    dependencies = [
        ('completion_aggregator', '0002_aggregator_last_modified'),
    ]

    operations = [
        migrations.CreateModel(
            name='StaleCompletion',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('username', models.CharField(max_length=255)),
                ('course_key', opaque_keys.edx.django.models.CourseKeyField(max_length=255)),
                ('block_key', opaque_keys.edx.django.models.UsageKeyField(blank=True, max_length=255, null=True)),
                ('force', models.BooleanField(default=False)),
                ('resolved', models.BooleanField(default=False)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
