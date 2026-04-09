# PDS Data Upload Manager

The PDS Data Upload Manager provides the client application and server interface for managing data deliveries and retrievals between Data Providers and the Planetary Data Cloud.

## Prerequisites

The PDS Data Upload Manager has the following prerequisites:

- `python3` for running the client application and unit tests (Python 3.13 or later)
- `terraform` for creating and deploying DUM server components to AWS
- `Docker` for Terraform to build and package Lambda functions
  - Minimum version: Docker Engine 20.10+ or Docker Desktop 4.x+
  - Architecture: If deploying from an ARM64 machine (for example, Apple M1/M2/M3) to x86_64 Lambdas, ensure Docker is configured to support `linux/amd64` builds
- `Node.js` version 18.x for the Authorizer Lambda. While the Terraform build process manages this via Docker (using `node:18-slim`), local development should align with this version to ensure dependency consistency.

## User Quickstart

Install with:

```bash
pip install pds-data-upload-manager
```

To deploy the service components to an AWS environment:

```bash
cd terraform/
terraform init
terraform apply
```

To execute the client, run:

```bash
pds-ingress-client -c <config path> -n <PDS node ID> -- <ingress path> [<ingress_path> ...]
```

To see a listing of all available arguments for the client:

```bash
pds-ingress-client --help
```

## Data Upload Manager Client Workflow

When using the DUM client script (`pds-ingress-client`), the following workflow is executed:

1. Index the requested input files and paths to determine the full input file set
2. Generate a manifest file containing information, including MD5 checksums, for each file to be ingested
3. Submit batch ingress requests for the input file set to the DUM Ingress Service in AWS
4. Upload the input file set to AWS S3 in batches
5. Create an ingress report

Determination of the input file set occurs in Step 1 by resolving the paths provided on the command line to the DUM client. Any directories provided are traversed recursively to determine the full set of files within them. Any file paths provided are included as-is in the input file set. **By default, symbolic links are followed during path resolution.** To avoid uploading duplicate data when files are symlinked into multiple locations, use the `--skip-symlinks` flag to skip symbolic links during traversal.

Depending on the size of the input file set, manifest file creation in Step 2 can become time-consuming because each file in the input file set must be hashed. To save time, use the `--manifest-path` command-line option to write the manifest contents to local disk. Specifying the same path via `--manifest-path` on subsequent executions of the DUM client causes the existing manifest to be read from disk. Any files within the input set that are referenced in the existing manifest will reuse the precomputed values, reducing upfront time before upload to S3 begins. The manifest is then rewritten to the path specified by `--manifest-path` to include any newly encountered files. In this way, a manifest file can expand across DUM executions and serve as a cache for file information.

The batch size used by Steps 3 and 4 can be configured in the INI configuration provided to the DUM client. The number of batches processed in parallel can be controlled with the `--num-threads` command-line argument.

By default, upon completion of an ingress request (Step 5), the DUM client provides a summary of the transfer results:

```text
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

A more detailed JSON-format report, containing full listings of all uploaded, skipped, and failed paths, can be written to disk via the `--report-path` command-line argument:

```json
{
  "Arguments": "Namespace(config_path='mcp.test.ingress.config.ini', node='sbn', prefix='/PDS/SBN/', force_overwrite=True, num_threads=4, log_path='/tmp/dum_log.txt', manifest_path='/tmp/dum_manifest.json', report_path='/tmp/dum_report.json', dry_run=False, log_level='info', ingress_paths=['/PDS/SBN/gbo.ast.catalina.survey/'])",
  "Batch Size": 3,
  "Total Batches": 67,
  "Start Time": "2025-02-25 18:51:10.507562+00:00",
  "Finish Time": "2025-02-25 19:41:29.504806+00:00",
  "Uploaded": [
    "gbo.ast.catalina.survey/data_calibrated/703/2020/20Apr02/703_20200402_2B_F48FC1_01_0001.arch.fz",
    "...",
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

Lastly, a detailed log file containing trace statements for each uploaded file and batch can be written to disk via the `--log-path` command-line argument. The log file path may also be specified in the INI configuration.

## Code of Conduct

All users and developers of NASA-PDS software are expected to abide by our [Code of Conduct](https://github.com/NASA-PDS/.github/blob/main/CODE_OF_CONDUCT.md). Please read it to ensure you understand the expectations of our community.

## Development

To develop this project, use your favorite text editor or an integrated development environment with Python support, such as [PyCharm](https://www.jetbrains.com/pycharm/).

### Contributing

For information on how to contribute to NASA-PDS codebases, please see our [Contributing guidelines](https://github.com/NASA-PDS/.github/blob/main/CONTRIBUTING.md).

### Installation

Install in editable mode with extra developer dependencies into your virtual environment of choice:

```bash
pip install --editable '.[dev]'
```

Configure the `pre-commit` hooks:

```bash
pre-commit install && pre-commit install -t pre-push
```

### Packaging

To isolate and reproduce the environment for this package, use a [Python virtual environment](https://docs.python.org/3/tutorial/venv.html). To do so, run:

```bash
python -m venv venv
source bin/venv/activate  # Substitute with `source bin/venv/activate.csh` for csh/tcsh users
```

If you have `tox` installed and would like it to create your environment and install dependencies for you, run:

```bash
tox --devenv <name you'd like for env> -e dev
```

Dependencies for development are specified as the `dev` extra in `setup.cfg`; they are installed into the virtual environment as follows:

```bash
pip install --editable '.[dev]'
```

### Tooling

The `dev` extra included in this repository installs `black`, `flake8` (plus some plugins), and `mypy`, along with default configuration for all of them. You can run all of these, and more, with:

```bash
tox -e lint
```

### Tests

A complete build, including test execution, linting (`mypy`, `black`, `flake8`, and more), and documentation generation, is executed via:

```bash
tox
```

#### Unit tests

Our unit tests are launched with:

```bash
pytest
```

### Documentation

You can build this project's documentation with:

```bash
sphinx-build -b html docs/source docs/build
```

You can access the build files in the following directory relative to the project root:

```text
build/sphinx/html/
```

### Migration Steps for Existing Deployments

If you are migrating from an existing deployment, follow these steps in order to transition to the new **Python 3.13** and **Docker-based** build system:

1. **Install and Start Docker**
   Install Docker Desktop or Docker Engine and ensure the daemon is running. Docker is now a **mandatory** dependency for compiling Linux-compatible binaries.

2. **Clear Local Build Artifacts**
   Remove existing temporary files to prevent version conflicts between Python 3.11, 3.12, and 3.13:

   ```bash
   rm -rf terraform/modules/lambda/service/files/
   rm -rf terraform/modules/lambda/authorizer/files/
   ```

3. **Initialize and Refresh Terraform**
   Update providers and synchronize the state with the new `null_resource` logic:

   ```bash
   cd terraform/
   terraform init -upgrade
   terraform refresh
   ```

4. **Deploy Infrastructure**
   Execute the deployment to build the new Python 3.13 layers and Node.js 18 authorizer:

   ```bash
   terraform apply
   ```

5. **Verify Runtime and Authorizer**
   Confirm that:

   - Lambda functions are using **Python 3.13**
   - The authorizer is running on **Node.js 18**
   - Files can be uploaded using the DUM client
