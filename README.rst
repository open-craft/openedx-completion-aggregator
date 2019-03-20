openedx-completion-aggregator
=============================

|pypi-badge| |travis-badge| |codecov-badge| |pyversions-badge| |license-badge|

openedx-completion-aggregator is a Django app that aggregates block level
completion data for different block types for Open edX.

Overview
--------

openedx-completion-aggregator uses the pluggable django app pattern to
ease installation.  To use in edx-platform, do the following:

1.  Install the app into your virtualenv.

    ..code_block::

        $ pip install openedx-completion-aggregator

2.  [Optional] You may override the set of registered aggregator block types in
    your lms.env.json file::

        ...
        "COMPLETION_AGGREGATOR_BLOCK_TYPES": {
            "course",
            "chapter",
            "subsection",
            "vertical"
        },
        ...


3.  By default, completion is aggregated with each created or updated
    BlockCompletion.  In most production instances, you will want to calculate
    aggregations asynchronously.  To enable asynchronous calculation for your
    installation, set the following in your lms.env.json file::

        ...
        "COMPLETION_AGGREGATOR_ASYNC_AGGREGATION": true,
        ...

    Then configure up a pair of cron jobs to run `./manage.py
    run_aggregator_service` and `./manage.py run_aggregator_cleanup` as often
    as desired.

Note that if operating on a Hawthorne-or-later release of edx-platform, you may
override the settings in `EDXAPP_ENV_EXTRA` instead.

Design
------

The completion aggregator is designed to facilitate working with course-level,
chapter-level, and other aggregated percentages of course completion as
represented by the [BlockCompletion model](https://github.com/edx/completion/blob/master/completion/models.py#L173) (from the edx-completion djangoapp).
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
[`completion_aggregator.Aggregator` model](https://github.com/open-craft/openedx-completion-aggregator/blob/master/completion_aggregator/models.py#L199).

During regular course interaction, a learner will calculate aggregations on the
fly to get the latest information.  However, on-the-fly calculations are too
expensive when performed for all users in a course, so periodically (every hour
or less), a task is run to calculate all aggregators that have gone out of
date in the previous hour, and store those values in the database.  These
stored values are then used for reporting on course-wide completion (for course
admin views).

By tracking which blocks have been changed recently (in the [`StaleCompletion` table](https://github.com/open-craft/openedx-completion-aggregator/blob/master/completion_aggregator/models.py#L272)
table) These stored values can also be used to shortcut calculations for
portions of the course graph that are known to be up to date.  If a user has
only completed blocks in chapter 3 of a three-chapter course since the last
time aggregations were stored, there is no need to redo the calculation for
chapter 1 or chapter 2.  The course-level aggregation can just sum the
already-stored values for chapter 1 and chapter 2 with a freshly calculated
value for chapter 3.

Currently, the major bottleneck in these calculations is creating the course
graph for each user.  We are caching the graph locally to speed things up, but
this stresses the memory capabilities of the servers.  My understanding is that
more recent versions of edx-platform do a better job caching course graphs
site-wide, which should improve performance, and allow us to bypass the local
calculation, though this will need to be evaluated when our client (which is
currently on ginkgo) upgrades.

License
-------

The code in this repository is licensed under the AGPL 3.0 unless
otherwise noted.

Please see ``LICENSE.txt`` for details.

How To Contribute
-----------------

Contributions are very welcome.

Please read `How To Contribute <https://github.com/edx/edx-platform/blob/master/CONTRIBUTING.rst>`_ for details.

Even though they were written with ``edx-platform`` in mind, the guidelines
should be followed for Open edX code in general.

PR description template should be automatically applied if you are sending PR from github interface; otherwise you
can find it it at `PULL_REQUEST_TEMPLATE.md <https://github.com/open-craft/openedx-completion-aggregator/blob/master/.github/PULL_REQUEST_TEMPLATE.md>`_

Issue report template should be automatically applied if you are sending it from github UI as well; otherwise you
can find it at `ISSUE_TEMPLATE.md <https://github.com/open-craft/openedx-completion-aggregator/blob/master/.github/ISSUE_TEMPLATE.md>`_

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
