# PDS Data Upload Manager

The PDS Data Upload Manager provides the client application and server interface for managing data deliveries and retrievals from the Data Providers to and from the Planetary Data Cloud.

## Prerequisites

The PDS Data Delivery Manager has the following prerequisties:

- `python3` for running the client application and unit tests (Python 3.13 or later)
- `terraform` for creating and deploying DUM server components to AWS

## User Quickstart

Install with:

    pip install pds-data-upload-manager

To deploy the service components to an AWS environment:

    cd terraform/
    terraform init
    terraform apply

To execute the client, run:

    pds-ingress-client -c <config path> -n <PDS node ID> -- <ingress path> [<ingress_path> ...]

To see a listing of all available arguments for the client:

    pds-ingress-client --help

## Data Upload Manager Client Workflow

When utilizing the DUM Client script (`pds-ingress-client`), the following workflow is executed:

1. Indexing of the requested input files/paths to determine the full input file set
2. Generation of a Manifest file, containing information, including MD5 checksums, of each file to be ingested
3. Batch ingress requesting of input file set to the DUM Ingress Service in AWS
4. Batch upload of input file set to AWS S3
5. Ingress report creation

Determination of the input file set is determined in Step 1 by resolving the paths providing on
the command-line to the DUM client. Any directories provided are recursed to determine the full set
of files within. Any paths provided are included as-is into the input file set.

Depending on the size of the input file set, the Manifest file creation in Step 2 can become
time-consuming due to the hashing of each file in the input file set. To save time, the `--manifest-path`
command-line option should be leveraged to write the contents of the Manifest to local disk. Specifying
the same path via `--manifest-path` on subsequent executions of the DUM client will result in
a read of the existing Manifest from disk. Any files within the input set referenced within the
read Manifest will reuse the precomputed values within, saving upfront time prior to start of upload
to S3. The Manifest will then be re-written to the path specified by `--manifest-path` to include
any new files encountered. In this way, a Manifest file can expand across executions of DUM to serve
as a sort of cache for file information.

The batch size utilized by Steps 3 and 4 can be configured within the INI config provided to the
DUM client. The number of batches processed in parallel can be controlled via the `--num-threads`
command-line argument.

By default, at completion of an ingress request (Step 5), the DUM client provides a summary of the
results of the transfer:

```
Ingress Summary Report for 2025-02-25 11:41:29.507022
-----------------------------------------------------
Uploaded: 200 file(s)
Skipped: 0 file(s)
Failed: 0 file(s)
Unprocessed: 0 file(s)
Total: 200 files(s)
Time elapsed: 3019.00 seconds
Bytes transferred: 3087368895
```

A more detailed JSON-format report, containing full listings of all uploaded/skipped/failed paths,
can be written to disk via the `--report-path` command-line argument:

```
{
    "Arguments": "Namespace(config_path='mcp.test.ingress.config.ini', node='sbn', prefix='/PDS/SBN/', force_overwrite=True, num_threads=4, log_path='/tmp/dum_log.txt', manifest_path='/tmp/dum_manifest.json', report_path='/tmp/dum_report.json', dry_run=False, log_level='info', ingress_paths=['/PDS/SBN/gbo.ast.catalina.survey/'])",
    "Batch Size": 3,
    "Total Batches": 67,
    "Start Time": "2025-02-25 18:51:10.507562+00:00",
    "Finish Time": "2025-02-25 19:41:29.504806+00:00",
    "Uploaded": [
        "gbo.ast.catalina.survey/data_calibrated/703/2020/20Apr02/703_20200402_2B_F48FC1_01_0001.arch.fz",
        ...
        "gbo.ast.catalina.survey/data_calibrated/703/2020/20Apr02/703_20200402_2B_N02055_01_0001.arch.xml"
    ],
    "Total Uploaded": 200,
    "Skipped": [],
    "Total Skipped": 0,
    "Failed": [],
    "Total Failed": 0,
    "Unprocessed": [],
    "Total Unprocessed": 0,
    "Bytes Transferred": 3087368895,
    "Total Files": 200
}
```

Lastly, a detailed log file containing trace statements for each file/batch uploaded can be written
to disk via the `--log-path` command-line argument. The log file path may also be specifed within
the INI config.

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
    source bin/venv/activate  # Substitute with `source bin/venv/activate.csh` for csh/tcsh users

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

Our unit tests are launched with the command:

    pytest

### Documentation

You can build this projects' docs with:

    sphinx-build -b html docs/source docs/build

You can access the build files in the following directory relative to the project root:

    build/sphinx/html/
