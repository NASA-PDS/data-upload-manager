🏃‍ ️Usage
============

This section describes how to use the PDS DUM client script.

pds-ingress-client Description
------------------------------

Upon installation of the DUM application, the ``pds-ingress-client`` script will
be available for use on the command-line.

To see the usage documentation, you can run the following::

    $ pds-ingress-client --help

The client application only has two arguments which must provided on each invocation,
at least one path to files or directories to be uploaded, and the name of the PDS
node the submission is on behalf of (via the ``--node`` argument).

When specifying the list of paths to be uploaded, any paths corresponding to
directories will be automatically recursed by the client script, and each file
within the directory will be included in the set uploaded to PDS Cloud. Any
sub-directories will be similarly recursed to find any additional files within,
until the entire directory tree is traversed.

The client script provides ``--include`` and ``--exclude`` arguments which can
be used to filter the set of files included in the upload request. Both arguments
support Unix shell-style wildcards (e.g. ``*.xml``), and can be specified multiple
times to include or exclude multiple patterns. The ``--include`` argument is applied
first, followed by the ``--exclude`` argument. If no ``--include`` arguments are
provided, all files are included by default.

Specifying the node ID of the requestor is accomplished via the ``--node`` argument,
specifying one of the following node name values: ``atm,eng,geo,img,naif,ppi,rs,rms,sbn``

The ``--dry-run`` flag can be used to have ``pds-ingress-client`` determine the
full set of files and directories to be processed without actually submitting
anything for ingest to PDS Cloud. This feature can be useful to ensure the correct
set of files are being included for a request before performing any communication
with the Server side of DUM.

The details of where the client script should submit ingest requests to are configured
within an INI file. After installing DUM, a new INI config should be created with the
appropriate values for each field. Once available, the config for use with a request
can be specified via the ``--config-path`` argument. See the Client Configuration section
of the installation_ instructions for more details on creating the INI config.

In its default configuration, the ``pds-ingress-client`` script includes the full path
of each discovered file when sending the request to the Server side components. Typically,
this can include unwanted path components, such as a user's home directory. To control
the path components included, the ``--prefix`` argument can be used to specify a path
prefix that will be trimmed from all file paths discovered by ``pds-ingress-client``.

For example, if the file ``/home/user/bundle/file.xml`` were to be uploaded, and
``--prefix /home/user`` were also provided, the path provided to the ingress service
in AWS would resolve to ``bundle/file.xml``.

The ``--weblogs LOG_TYPE`` argument can be used to indicate that weblog files are being uploaded.
The type of log files (e.g. ``apache``, ``nginx``, etc.) should be specified as the
``LOG_TYPE`` argument. When this flag is provided, the client will automatically adjust
the "trimmed" path for each ingested file to replace the specified path prefix with ``weblog/``,
ensuring that all weblog files are routed to a specific S3 bucket used for web analytics.
Because of this, the ``--prefix`` argument must be provided when using the ``--weblogs`` argument.

**Important:** When using the ``--weblogs`` flag, all files must be GZip-compressed (i.e., have a ``.gz``
extension). The client will validate this requirement and report an error if any non-GZipped files are
detected. For information on how to compress files using GZip:

- **Unix/Linux/macOS:** The ``gzip`` command is typically pre-installed. See the `GNU Gzip documentation`_ for usage details.
- **Windows:** Install gzip via `GnuWin32 gzip`_ or use the ``gzip`` command included with `Git for Windows`_.

The ``pds-ingress-client`` by default utilizes all available CPUs on the
local machine to perform parallelized ingress requests to the ingress service. The exact
number of threads can be controlled via the ``--num-threads`` argument.

The client script also provides several arguments for reporting status of an ingress request:

- ``--report-path`` : Specifies a path to write a detailed report file in JSON format, containing details about which files were uploaded, skipped or failed during transfer.
- ``--manifest-path`` : Specifies a path to write the manifest of all files included in ingress request, including file checksums. This option may also be used to provide an existing Manifest file to bypass its recomputation during subsequent requests.
- ``--log-path`` : Specifies a path to write a trace log of the ingress request which does not go to the console. Can be useful for troubleshooting tranfer failures.

Lastly, the ``--version`` option may be used to verify the version number of installed DUM client.

Data Upload Manager Client Workflow
-----------------------------------

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
results of the transfer::

    Ingress Summary Report for 2025-02-25 11:41:29.507022
    -----------------------------------------------------
    Uploaded: 200 file(s)
    Skipped: 0 file(s)
    Failed: 0 file(s)
    Unprocessed: 0 file(s)
    Total: 200 files(s)
    Time elapsed: 3019.00 seconds
    Bytes transferred: 3087368895

A more detailed JSON-format report, containing full listings of all uploaded/skipped/failed paths,
can be written to disk via the `--report-path` command-line argument::

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


Lastly, a detailed log file containing trace statements for each file/batch uploaded can be written
to disk via the `--log-path` command-line argument. The log file path may also be specifed within
the INI config.

Automatic Retry of Failed Uploads
---------------------------------

The DUM client script is configured to automatically retry any failed uploads to S3 using exponential
backoff_ and retry. When an intermittent failure occurs during upload, messages pertaining to the
backoff and retry are logged to the log file (which can be specified via the `--log-path` argument).

Here is an example of such log messages::

    ...
    [2025-09-23 16:21:24,491] INFO Thread-9 (worker) ingress_file_to_s3 : Batch 0 : Ingesting mflat.703.19Dec20.fits.xml to https://pds-staging.s3.amazonaws.com/mflat.703.19Dec20.fits.xml
    [2025-09-23 16:21:24,493] WARNING Thread-9 (worker) backoff_handler : Backing off ingress_file_to_s3() for 0.2 seconds after 1 tries, reason: HTTPError
    [2025-09-23 16:21:24,665] INFO Thread-9 (worker) ingress_file_to_s3 : Batch 0 : Ingesting mflat.703.19Dec20.fits.xml to https://pds-staging.s3.amazonaws.com/mflat.703.19Dec20.fits.xml
    [2025-09-23 16:21:24,667] WARNING Thread-9 (worker) backoff_handler : Backing off ingress_file_to_s3() for 1.2 seconds after 2 tries, reason: HTTPError
    [2025-09-23 16:21:25,832] INFO Thread-9 (worker) ingress_file_to_s3 : Batch 0 : Ingesting mflat.703.19Dec20.fits.xml to https://pds-staging.s3.amazonaws.com/mflat.703.19Dec20.fits.xml
    [2025-09-23 16:21:25,833] WARNING Thread-9 (worker) backoff_handler : Backing off ingress_file_to_s3() for 1.8 seconds after 3 tries, reason: HTTPError
    [2025-09-23 16:21:27,644] INFO Thread-9 (worker) ingress_file_to_s3 : Batch 0 : Ingesting mflat.703.19Dec20.fits.xml to https://pds-staging.s3.amazonaws.com/mflat.703.19Dec20.fits.xml
    [2025-09-23 16:21:27,720] INFO Thread-9 (worker) ingress_file_to_s3 : Batch 0 : mflat.703.19Dec20.fits.xml Ingest complete

Typically, log messages pertaining to backoff and retry can be safely ignored if upload is eventually succesful, as in the above example.
However, if an upload ultimately fails after all retries are exhausted it could indicate a more serious problem that needs to be investigated::

    ...
    [2025-09-23 16:31:47,231] WARNING Thread-9 (worker) backoff_handler : Backing off ingress_file_to_s3() for 30.9 seconds after 6 tries, reason: HTTPError
    [2025-09-23 16:32:18,099] INFO Thread-9 (worker) ingress_file_to_s3 : Batch 0 : Ingesting mflat.703.19Dec20.fits.fz to https://pds-staging.s3.amazonaws.com/mflat.703.19Dec20.fits.fz
    [2025-09-23 16:32:18,101] WARNING Thread-9 (worker) backoff_handler : Backing off ingress_file_to_s3() for 23.2 seconds after 7 tries, reason: HTTPError
    [2025-09-23 16:32:41,324] INFO Thread-9 (worker) ingress_file_to_s3 : Batch 0 : Ingesting mflat.703.19Dec20.fits.fz to https://pds-staging.s3.amazonaws.com/mflat.703.19Dec20.fits.fz
    [2025-09-23 16:32:41,326] WARNING Thread-9 (worker) backoff_handler : Backing off ingress_file_to_s3() for 54.8 seconds after 8 tries, reason: HTTPError
    [2025-09-23 16:33:36,086] INFO Thread-9 (worker) ingress_file_to_s3 : Batch 0 : Ingesting mflat.703.19Dec20.fits.fz to https://pds-staging.s3.amazonaws.com/mflat.703.19Dec20.fits.fz
    [2025-09-23 16:33:36,087] ERROR Thread-9 (worker) _process_batch : Batch 0 : Ingress failed for mflat.703.19Dec20.fits.fz, Reason: 403 Client Error

Any files that fail to upload after all retries are exhausted are reattempted in one final attempt at the end of DUM client execution::

    ...
    [2025-09-23 16:33:36,094] INFO MainThread main : All batches processed
    [2025-09-23 16:33:36,094] INFO MainThread main : ----------------------------------------
    [2025-09-23 16:33:36,094] INFO MainThread main : Reattempting ingress for failed files...
    [2025-09-23 16:33:36,096] INFO Thread-16 (worker) _prepare_batch_for_ingress : Batch 0 : Preparing for ingress
    [2025-09-23 16:33:36,096] INFO Thread-16 (worker) _prepare_batch_for_ingress : Batch 0 : Prep completed in 0.00 seconds
    [2025-09-23 16:33:36,108] INFO Thread-23 (worker) request_batch_for_ingress : Batch 0 : Requesting ingress
    [2025-09-23 16:33:36,732] INFO Thread-23 (worker) request_batch_for_ingress : Batch 0 : Ingress request completed in 0.62 seconds
    [2025-09-23 16:33:36,734] INFO Thread-23 (worker) ingress_file_to_s3 : Batch 0 : Ingesting mflat.703.19Dec20.fits.fz to https://pds-sbn-staging-dev.s3.amazonaws.com/mflat.703.19Dec20.fits.fz

Files that still fail to upload during this final attempt are recorded in the final summary report::

    Ingress Summary Report for 2025-09-23 16:35:37.532468
    -----------------------------------------------------
    Uploaded: 0 file(s)
    Skipped: 0 file(s)
    Failed: 1 file(s)
    Unprocessed: 0 file(s)
    Total: 1 files(s)
    Time elapsed: 244.87 seconds
    Bytes transferred: 0

Should persistent failures like this occur, they should be communicated to the PDS Operations team for investigation.

.. References:
.. _backoff: https://pypi.org/project/backoff/
.. _installation: ../installation/index.html
.. _GNU Gzip documentation: https://www.gnu.org/software/gzip/
.. _GnuWin32 gzip: http://gnuwin32.sourceforge.net/packages/gzip.htm
.. _Git for Windows: https://gitforwindows.org/
