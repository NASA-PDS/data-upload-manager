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

The ``pds-ingress-client`` by default utilizes all available CPUs on the
local machine to perform parallelized ingress requests to the ingress service. The exact
number of threads can be controlled via the ``--num-threads`` argument.

The client script also provides several arguments for reporting status of an ingress request:

- ``--report-path`` : Specifies a path to write a detailed report file in JSON format, containing details about which files were uploaded, skipped or failed during transfer.
- ``--manifest-path`` : Specifies a path to write the manifest of all files included in ingress request, including file checksums. This option may also be used to provide an existing Manifest file to bypass its recomputation during subsequent requests.
- ``--log-path`` : Specifies a path to write a trace log of the ingress request which does not go to the console. Can be useful for troubleshooting tranfer failures.

Lastly, the ``--version`` option may be used to verify the version number of installed DUM client.


.. References:
.. _installation: ../installation/index.html
