👩‍💻 Development
=================

Quick start
-----------

To obtain a copy of the code and work on a new branch::

    git clone https://github.com/NASA-PDS/data-upload-manager.git
    git checkout -b "<issue number>_<issue name>"

Create a virtual environment in ``venv`` using Python 3.9 or later::

    python3 -m venv venv

Activate the new virtual environment::

    . venv/bin/activate

Install the package and its dependencies for development into the virtual environment::

    pip install --editable '.[dev]'

At this point, the command line tools are now available in ``venv/bin``
as explained in `usage`_.

Testing
-------

The code base includes unit tests. Once you've installed the service, you can
run the unit tests with the following command (assuming the virtual environment
has been activated, see above)::

    tox py39


Making Releases
---------------

Releases are done on GitHub and PyPI. This is implemented through the CI/CD
framework using GitHub Actions_ on the ``main`` branch. To trigger a release
via the CI/CD framework, create a tag named ``release/<version number>``,
and push it to the GitHub origin (https://github.com/NASA-PDS/data-upload-manager.git)
to trigger the Actions_ framework for release. Note that ``<version number>``
must be a fully-qualified ``X.Y.Z`` version. For example::

    git tag --annotate --message "Release 1.2.0" release/1.2.0
    git push origin release/1.2.0

From there, the Actions_ framework will determine an appropriate patch version
number, tag and build a release, and push it to PyPI.

Contribute
----------

Clone the repo from : https://github.com/NASA-PDS/data-upload-manager and then
submit a pull request for your branch when complete. At least one PDS Engineering
Node developer must approve the request before it is merged.

.. References:
.. _usage: ../usage/index.html
.. _Actions: https://github.com/features/actions
