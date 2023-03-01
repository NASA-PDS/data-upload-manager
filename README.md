# PDS Data Delivery Manager

The PDS Data Delivery Manager provides the client application and server interface for managing data deliveries and retrievals between the Planetary Data Cloud and Data Providers.

## Prerequisites

The PDS Data Delivery Manager has the following prerequisties:

- `python3` for running the client application and unit tests
- `awscli` (optional) for deploying the service components to AWS (TBD)

## User Quickstart

Install with:

    pip install pds-data-delivery-manager

To deploy the service components to an AWS environment:

    TBD

To execute the client, run:

    pds-ingress-client.py <ingress path> [<ingress_path> ...]

## Code of Conduct

All users and developers of the NASA-PDS software are expected to abide by our [Code of Conduct](https://github.com/NASA-PDS/.github/blob/main/CODE_OF_CONDUCT.md). Please read this to ensure you understand the expectations of our community.

## Development

To develop this project, use your favorite text editor, or an integrated development environment with Python support, such as [PyCharm](https://www.jetbrains.com/pycharm/).

### Contributing

For information on how to contribute to NASA-PDS codebases please take a look at our [Contributing guidelines](https://github.com/NASA-PDS/.github/blob/main/CONTRIBUTING.md).

### Installation

Install in editable mode and with extra developer dependencies into your virtual environment of choice:

    pip install --editable '.[dev]'

Configure the `pre-commit` hooks:

    pre-commit install && pre-commit install -t pre-push

### Packaging

To isolate and be able to re-produce the environment for this package, you should use a [Python Virtual Environment](https://docs.python.org/3/tutorial/venv.html). To do so, run:

    python -m venv venv

Then exclusively use `venv/bin/python`, `venv/bin/pip`, etc. (It is no longer recommended to use `venv/bin/activate`.)

If you have `tox` installed and would like it to create your environment and install dependencies for you run:

    tox --devenv <name you'd like for env> -e dev

Dependencies for development are specified as the `dev` `extras_require` in `setup.cfg`; they are installed into the virtual environment as follows:

    pip install --editable '.[dev]'

### Tooling

The `dev` `extras_require` included in this repo installs `black`, `flake8` (plus some plugins), and `mypy` along with default configuration for all of them. You can run all of these (and more!) with:

    tox -e lint

### Tests

A complete "build" including test execution, linting (`mypy`, `black`, `flake8`, etc.), and documentation build is executed via:

    tox

#### Unit tests

Our unit tests are launched with command:

    pytest

### Documentation

You can build this projects' docs with:

    python setup.py build_sphinx

You can access the build files in the following directory relative to the project root:

    build/sphinx/html/
