openedx-completion-aggregator
=============================

|pypi-badge| |travis-badge| |codecov-badge| |pyversions-badge| |license-badge|

openedx-completion-aggregator is a Django app that aggregates block level completion data for different block types for Open edX.

What does that mean?

A standard Open edX installation can track the completion of individual XBlocks in a course, which is done using the `completion library <https://github.com/edx/completion#completion>`_. This completion tracking is what powers the green checkmarks shown in the course outline and course navigation as the learner completes each unit in the course:

.. image:: docs/completion.png
   :width: 100%

When completion tracking is enabled (and green checkmarks are showing, as seen above), it is only tracked at the XBlock level. You can use the Course Blocks API to check the completion status of any individual XBlock in the course, for a single user. For example, to get the completion of the XBlock with usage ID ``block-v1:OpenCraft+completion+demo+type@html+block@demo_block`` on the LMS instance ``courses.opencraft.com`` by the user ``MyUsername``, you could call this REST API::

    GET https://courses.opencraft.com/api/courses/v1/blocks/block-v1:OpenCraft+completion+demo+type@html+block@demo_block?username=MyUsername&requested_fields=completion

The response will include a ``completion`` value between ``0`` and ``1``.

However, what if you want to know the overall % completion of an entire course? ("Alex, you have completed 45% of Introduction to Statistics") Or what if you as an instructor want to get a report of how much of Section 1 every student in a course has completed? Those queries are either not possible or too slow using the APIs built in to the LMS and ``completion``.

This Open edX plugin, ``openedx-completion-aggregator`` watches course activity and asynchronously updates database tables with "aggregate" completion data. "Aggregate" data means completion data summed up over all XBlocks into a course and aggregated at higher levels, like the subsection, section, and course level. The completion aggregator provides a REST API that can provide near-instant answers to queries such as:

* What % complete are each of the courses that I'm enrolled in?
* What % of each section in Course X have my students completed?
* What is the average completion % among all enrolled students in a course?

API Details
-----------

For details about how the completion aggregator's REST APIs can be used, please refer to `the docstrings in views.py <https://github.com/open-craft/openedx-completion-aggregator/blob/master/completion_aggregator/api/v1/views.py#L24>`_.

Installation and Configuration
------------------------------

openedx-completion-aggregator uses the pluggable django app pattern to ease installation. To use in edx-platform, do the following:

1.  Install the app into your virtualenv::

        $ pip install openedx-completion-aggregator

2.  [Optional] You may override the set of registered aggregator block types in your ``lms.yml`` file::

        ...
        COMPLETION_AGGREGATOR_BLOCK_TYPES:
            - course
            - chapter
            - subsection
            - vertical
        ...


3.  By default, completion is aggregated synchronously (with each created or updated BlockCompletion). While that is ideal for development, in most production instances, you will want to calculate aggregations asynchronously for better performance.  To enable asynchronous calculation for your installation, set the following in your ``lms.yml`` file::

        ...
        COMPLETION_AGGREGATOR_ASYNC_AGGREGATION: true
        ...

    Then configure up a pair of cron jobs to run ``./manage.py
    run_aggregator_service`` and ``./manage.py run_aggregator_cleanup`` as often
    as desired.


Design: Technical Details
-------------------------

The completion aggregator is designed to facilitate working with course-level,
chapter-level, and other aggregated percentages of course completion as
represented by the `BlockCompletion model <https://github.com/edx/completion/blob/e1db6a137423f6/completion/models.py#L175>`_ (from the edx-completion djangoapp).
By storing these values in the database, we are able to quickly return
information for all users in a course.

Each type of XBlock (or XModule) is assigned a completion mode of
"Completable", "Aggregator", or "Excluded".

A "completable" block is one that can directly be completed, either by viewing it
on the screen, by submitting a response, or by some custom defined means.  When
completed, a BlockCompletion is created for that user with a value of 1.0
(any value between 0.0 and 1.0 is allowed).  Completable blocks always have a
maximum possible value of 1.0.

An "excluded" block is ignored for the purposes of completion.  It always has
a completion value of 0.0, and a maximum possible value of 0.0.  If an excluded
block has children, those are also ignored for the purposes of completion.

An "aggregator" block is one that contains other blocks.  It cannot be directly
completed, but has an aggregate completion value equal to the sum of the
completion values of its immediate children, and a maximum possible value equal
to the sum of the maximum possible values of its immediate children (1.0 for
completable blocks, 0.0 for excluded blocks, and the calculated maximum for any
contained aggregators).  If an aggregator has a maximum possible value of 0.0,
(either it has no children, or all its children are excluded), it is always
considered complete.

To calculate aggregations for a user, the course graph is retrieved from the
modulestore (using block transformers) to determine which blocks are contained
by each aggregator, and values are summed recursively from the course block on
down.  Values for every node in the whole tree can be calculated in a single
traversal.  These calculations can either be performed "read-only" (to get the
latest data for each user), or "read-write" to store that data in the
`completion_aggregator.Aggregator model <https://github.com/open-craft/openedx-completion-aggregator/blob/a71ab4f077/completion_aggregator/models.py#L199>`_.

During regular course interaction, a learner will calculate aggregations on the
fly to get the latest information.  However, on-the-fly calculations are too
expensive when performed for all users in a course, so periodically (every hour
or less), a task is run to calculate all aggregators that have gone out of
date in the previous hour, and store those values in the database.  These
stored values are then used for reporting on course-wide completion (for course
admin views).

By tracking which blocks have been changed recently (in the `StaleCompletion table <https://github.com/open-craft/openedx-completion-aggregator/blob/a71ab4f077a/completion_aggregator/models.py#L272>`_
), these stored values can also be used to shortcut calculations for
portions of the course graph that are known to be up to date.  If a user has
only completed blocks in chapter 3 of a three-chapter course since the last
time aggregations were stored, there is no need to redo the calculation for
chapter 1 or chapter 2.  The course-level aggregation can just sum the
already-stored values for chapter 1 and chapter 2 with a freshly calculated
value for chapter 3.

Currently, the major bottleneck in these calculations is creating the course
graph for each user.  We are caching the graph locally to speed things up, but
this stresses the memory capabilities of the servers.

License
-------

The code in this repository is licensed under the AGPL 3.0 unless
otherwise noted.

Please see ``LICENSE.txt`` for details.

How To Contribute
-----------------

Contributions are very welcome.

Please read `How To Contribute <https://github.com/edx/edx-platform/blob/master/CONTRIBUTING.rst>`_ for details.

Reporting Security Issues
-------------------------

Please do not report security issues in public. Please email help@opencraft.com.

Getting Help
------------

Have a question about this repository, or about Open edX in general?  Please
refer to this `list of resources`_ if you need any assistance.

.. _list of resources: https://open.edx.org/getting-help


.. |pypi-badge| image:: https://img.shields.io/pypi/v/openedx-completion-aggregator.svg
    :target: https://pypi.python.org/pypi/openedx-completion-aggregator/
    :alt: PyPI

.. |travis-badge| image:: https://travis-ci.org/open-craft/openedx-completion-aggregator.svg?branch=master
    :target: https://travis-ci.org/open-craft/openedx-completion-aggregator
    :alt: Travis

.. |codecov-badge| image:: http://codecov.io/github/edx/openedx-completion-aggregator/coverage.svg?branch=master
    :target: http://codecov.io/github/open-craft/openedx-completion-aggregator?branch=master
    :alt: Codecov

.. |pyversions-badge| image:: https://img.shields.io/pypi/pyversions/openedx-completion-aggregator.svg
    :target: https://pypi.python.org/pypi/openedx-completion-aggregator/
    :alt: Supported Python versions

.. |license-badge| image:: https://img.shields.io/github/license/open-craft/openedx-completion-aggregator.svg
    :target: https://github.com/open-craft/openedx-completion-aggregator/blob/master/LICENSE.txt
    :alt: License
