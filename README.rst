openedx-completion-aggregator
=============================

|pypi-badge| |travis-badge| |codecov-badge| |doc-badge| |pyversions-badge|
|license-badge|

openedx-completion-aggregator is a Django app that aggregates block level 
completion data for different block types for Open edX.  

Overview
--------

..code_block::

    $ pip install openedx-completion-aggregator

Add to settings.py::

    INSTALLED_APPS += 'completion_aggregator'
    COMPLETION_AGGREGATED_BLOCKS = [
        'chapter',
        'subsection',
        'vertical',
    ]
    
Add to urls.py::

    urlpatterns += [
       url('^completion/', include('completion_aggregator.urls'))
    ]

Documentation
-------------

The full documentation is at https://openedx-completion-aggregator.readthedocs.org.

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
can find it it at `PULL_REQUEST_TEMPLATE.md <https://github.com/edx/openedx-completion-aggregator/blob/master/.github/PULL_REQUEST_TEMPLATE.md>`_

Issue report template should be automatically applied if you are sending it from github UI as well; otherwise you
can find it at `ISSUE_TEMPLATE.md <https://github.com/edx/openedx-completion-aggregator/blob/master/.github/ISSUE_TEMPLATE.md>`_

Reporting Security Issues
-------------------------

Please do not report security issues in public. Please email security@edx.org.

Getting Help
------------

Have a question about this repository, or about Open edX in general?  Please
refer to this `list of resources`_ if you need any assistance.

.. _list of resources: https://open.edx.org/getting-help


.. |pypi-badge| image:: https://img.shields.io/pypi/v/openedx-completion-aggregator.svg
    :target: https://pypi.python.org/pypi/openedx-completion-aggregator/
    :alt: PyPI

.. |travis-badge| image:: https://travis-ci.org/edx/openedx-completion-aggregator.svg?branch=master
    :target: https://travis-ci.org/edx/openedx-completion-aggregator
    :alt: Travis

.. |codecov-badge| image:: http://codecov.io/github/edx/openedx-completion-aggregator/coverage.svg?branch=master
    :target: http://codecov.io/github/edx/openedx-completion-aggregator?branch=master
    :alt: Codecov

.. |doc-badge| image:: https://readthedocs.org/projects/openedx-completion-aggregator/badge/?version=latest
    :target: http://openedx-completion-aggregator.readthedocs.io/en/latest/
    :alt: Documentation

.. |pyversions-badge| image:: https://img.shields.io/pypi/pyversions/openedx-completion-aggregator.svg
    :target: https://pypi.python.org/pypi/openedx-completion-aggregator/
    :alt: Supported Python versions

.. |license-badge| image:: https://img.shields.io/github/license/edx/openedx-completion-aggregator.svg
    :target: https://github.com/edx/openedx-completion-aggregator/blob/master/LICENSE.txt
    :alt: License
