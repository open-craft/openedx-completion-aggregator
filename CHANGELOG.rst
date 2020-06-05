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
