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
full set of files and directories to  be processed without actually submitting
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

Lastly, the ``pds-ingress-client`` by default utilizes all available CPUs on the
local machine to perform parallelized ingress requests to the ingress service. The exact
number of threads can be controlled via the ``--num-threads`` argument.

.. References:
.. _installation: ../installation/index.html
