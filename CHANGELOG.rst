Change Log
----------

..
   All enhancements and patches to completion_aggregator will be documented
   in this file.  It adheres to the structure of http://keepachangelog.com/ ,
   but in reStructuredText instead of Markdown (for ease of incorporation into
   Sphinx documentation and the PyPI description).

   This project adheres to Semantic Versioning (http://semver.org/).

.. There should always be an "Unreleased" section for changes pending release.

Unreleased
~~~~~~~~~~

[4.2.0] - 2024-06-21
~~~~~~~~~~~~~~~~~~~~

* Transform `openedx.completion_aggregator.progress.*` tracking log events into xAPI using edx-event-routing-backends so
  they can be included in Aspects analytics data.

[4.1.0] - 2024-06-18
~~~~~~~~~~~~~~~~~~~~

* Emit `openedx.completion_aggregator.progress.*` tracking log events for the
  various block/course types

[4.0.3] - 2023-10-24
~~~~~~~~~~~~~~~~~~~~

* Replace `xblockutils.*` imports with `xblock.utils.*`. The old imports are
  used as a fallback for compatibility with older releases.
* Remove `xblockutils` dependency.

[4.0.2] - 2023-03-03
~~~~~~~~~~~~~~~~~~~~

* Update GitHub workflows.
* Update requirements to logically organize them and allow scheduled
  requirements updates.
* Add base requirements to `setup.py`.

[4.0.1] - 2022-07-13
~~~~~~~~~~~~~~~~~~~~

* Add `COMPLETION_AGGREGATOR_AGGREGATE_UNRELEASED_BLOCKS` setting, which
  enables the use of course blocks with a release date set to a future date in
  the course completion calculation.

[4.0.0] - 2022-06-17
~~~~~~~~~~~~~~~~~~~~

* Add Maple support.
* Drop support for Python 2.
* Drop support for Django 2.X.
* Replace Travis CI with GitHub Actions.
* Fix docs quality checks.
* Fix pylint quality checks.
* Fix the build & release pipeline.

[3.2.0] - 2021-11-26
~~~~~~~~~~~~~~~~~~~~

* Add Lilac support.

[3.1.0] - 2021-04-28
~~~~~~~~~~~~~~~~~~~~

* Add Koa support.
* Upgrade Python to 3.8.

[2.2.1] - 2020-06-05
~~~~~~~~~~~~~~~~~~~~

* Fix handling of invalid keys.

[2.1.3] - 2020-05-08
~~~~~~~~~~~~~~~~~~~~

* Fix `all` option in `reaggregate_course`.

[2.1.1] - 2020-04-20
~~~~~~~~~~~~~~~~~~~~

* Pass `user.username` to Celery task instead of `user`.
* Convert `course_key` string to `CourseKey` in `reaggregate_course`.

[2.1.0] - 2020-04-17
~~~~~~~~~~~~~~~~~~~~

* Add locking mechanism to batch operations.
* Replace `course_key` with `course` in `reaggregate_course` management command.

[2.0.1] - 2020-04-17
~~~~~~~~~~~~~~~~~~~~

* Convert `course_key` to string before sending it to Celery task.

[1.0.0] - 2018-01-04
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* First release on PyPI.
* On-demand asynchronous aggregation of xblock completion.
* Provides an API to retrieve aggregations for one or many users, for one or
  many courses.
