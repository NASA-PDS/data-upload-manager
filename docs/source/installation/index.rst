📦 Installation
================

This section describes how to install the PDS Data Upload Manager (DUM) Service.

Requirements
------------

Prior to installing this software, ensure your system meets the following
requirements:

* Python_ 3.9 or above. Python 2 is *not* supported.
* Terraform_ 1.0.11 or above. Note that Terraform is only required when deploying
  the server side components. It is not required to run the client-side script.
  For more information on deploying the server side components via Terraform,
  consult the terraform_ section of the documentation.

Consult your operating system instructions or system administrator to install
the required packages. For those without system administrator access, you
can use a local Python_ 3 installation using a `virtual environment`_
installation.

Installation Instructions
-------------------------

This section documents the installation procedure.

Installation
^^^^^^^^^^^^

The easiest way to install this software is to use Pip_, the Python Package
Installer. If you have Python on your system, you probably already have Pip;
you can run ``pip3 --help`` to check. Then run::

    pip3 install pds-data-upload-manager

.. note::

    The above command will install the latest approved release.
    To install a prior release, you can run::

        pip3 install pds-data-upload-manager==<version>

    The released versions are listed on https://pypi.org/project/pds-data-upload-manager/#history

    If you want to use the latest unstable version, refer to the `development`_ documentation

If you don't want the package dependencies to interfere with your local system
you can use a `virtual environment`_  for your deployment.
To do so::

    mkdir -p $HOME/.venv
    python3 -m venv $HOME/.venv/pds-data-upload-manager
    source $HOME/.venv/pds-data-upload-manager/bin/activate
    pip3 install pds-data-upload-manager

At this point, the PDS DUM client script is available under
``$HOME/.venv/pds-data-upload-manager/bin/pds-ingress-client``.

Client Configuration
^^^^^^^^^^^^^^^^^^^^
The PDS DUM client script utilizes an INI_ file for its configuration. While there
is a default configuration file bundled with the service, to properly communicate
with the server side components within AWS, end-users must provide their own
INI configuration with the correct endpoints and user credentials filled in.

The following may be used as a template for a new INI configuration file::

    [AWS]
    profile = <AWS_Profile_Name>

    [API_GATEWAY]
    url_template = https://{id}.execute-api.{region}.amazonaws.com/{stage}/{resource}
    id           = <API_Gateway_ID>
    region       = us-west-2
    stage        = <API_Gateway_Stage_Name>
    resource     = request

    [COGNITO]
    client_id    = <Cognito_Client_ID>
    username     = <Cognito_Username>
    password     = <Cognito_Password>
    region       = us-west-2

    [OTHER]
    log_level = INFO
    file_format = "[%(asctime)s] %(levelname)s %(threadName)s %(funcName)s : %(message)s"
    cloudwatch_format = '%(levelname)s %(threadName)s %(funcName)s : %(message)s'
    console_format = "%(message)s"
    log_group_name = "<Cloudwatch_Log_Group_Name>"
    log_file_path =

Bracketed fields within the template correspond to values which need to be filled
in by an end-user prior to using the `pds-ingress-client` script to transfer
files to PDS. The remaining fields should be left as-is.

To obtain the correct values for `<AWS_Profile_Name>`, `<API_Gateway_ID>`,
`<API_Gateway_Stage_Name>` and `<Cognito_Client_ID>`, `<Cloudwatch_Log_Group_Name>`
contact a PDS Operator.

To obtain values for `<Cognito_Username>` and `<Cognito_Password>`, consult
the section on User Registration within this document.

Running the Client script
^^^^^^^^^^^^^^^^^^^^^^^^^

Once the `pds-data-upload-manager` has been installed, you can run ``pds-ingress-client --help``
to get a usage message and ensure the client-side service is properly installed. You can
also consult the `usage_` documentation for more details.

Upgrading the Service
---------------------

To check for and install an upgrade to the service, run the following command in
your virtual environment::

  pip install --upgrade pds-data-upload-manager

.. note::

    An update to an existing virtualenv installation of the PDS DUM Service may fail
    if the underlying minimum required Python version has changed. If so, a new
    virtual environment should be created using the required version of Python, after
    which the latest version of the Service may be installed into it. Consult the
    installation instructions above on how to create a new virtual environment.

Configuring the Server side Bucket Map
--------------------------------------

Once the Server side components of DUM have been deployed to AWS (see terraform_ section),
how ingested files are routed to S3 buckets is controlled via a "Bucket Map" configuration
file which gets bundled with the "nucleus-dum-ingress-service" lambda function.

The format of the file is a simple YAML_ format file. An example bucket map is shown below::

    MAP:
      NODES:
        ATM:
          default: pds-nucleus-dum
        ENG:
          default: pds-nucleus-dum
        GEO:
          default: pds-nucleus-dum
        IMG:
          default: pds-nucleus-dum
        NAIF:
          default: pds-nucleus-dum
        PPI:
          default: pds-nucleus-dum
        RMS:
          default: pds-nucleus-dum
        RS:
          default: pds-nucleus-dum
        SBN:
          gbo.ast.catalina.survey: pds-nucleus-staging
          default: pds-nucleus-dum

Within the mapping is are separate entries for each PDS Node which could make
an ingress request via the client script. Within each Node section are one or
more key/value mappings, where keys correspond to an expected path prefix of
a file requested for ingest, and each value is the name of an S3 bucket where the
file should be uploaded to.

In the above example, we can see that a default mapping is configured for all
nodes that instructs the ingress lambda function to route all files to the ``pds-nucleus-dum``
bucket. This is the mapping that will be used when no other mapping for a path prefix exists.

Within the ``SBN`` section, we also see that a mapping from the ``gbo.ast.catalina.survey``
path prefix to the ``pds-nucleus-staging`` bucket is also defined. This means that any
requests file paths that begin with ``gbo.ast.catalina.survey`` will be routed to the
``pds-nucleus-staging`` bucket during upload.

.. note::

    The ``--prefix`` argument of the ``pds-ingress-client`` script can be instrumental to ensure
    that paths requested for ingress have a prefix that matches one of the mappings expected by
    the bucket config. Consult the usage_ page for the ``pds-ingress-client`` for more details
    on using the ``--prefix`` argument.

Should there ever be a need to make modifications to the bucket map used with a
deployment of the DUM service, changes can be made to the file directly from within the
AWS Console Lambda Code Source editor window. Be sure that the function is redeployed after
any updates are made to the bucket map to ensure they take affect for subsequent ingress reqeusts.

Adding users to the AWS Cognito User Pool
-----------------------------------------

Before the client-side script can be used to request ingest of files to PDS Cloud,
a valid user account must exist in the AWS Cognito User Pool deployed with the rest
of the DUM Server side components. Credentials for the user must then be provided in
the INI config used with the ``pds-ingress-client`` script.

Currently, there are only two ways to configure new users within the User Pool:

* Specify the list of users to pre-populate the User Pool with via the `.tfvars` file used with a Terraform deployment. See the terraform_ section for more information on how to configure this.
* Manually add new users via the AWS Admin Console for the Cognito service. More information on how to do so can be found here: https://docs.aws.amazon.com/cognito/latest/developerguide/how-to-create-user-accounts.html


.. References:
.. _usage: ../usage/index.html
.. _development: ../development/index.html
.. _terraform: ../terraform/index.html
.. _Pip: https://pip.pypa.io/en/stable/
.. _Python: https://www.python.org/
.. _Terraform: https://www.terraform.io/
.. _`virtual environment`: https://docs.python.org/3/library/venv.html
.. _INI: https://en.wikipedia.org/wiki/INI_file
.. _YAML: https://yaml.org
