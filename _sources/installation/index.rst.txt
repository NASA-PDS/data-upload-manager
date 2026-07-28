📦 Installation
================

This section describes how to install the PDS Data Upload Manager (DUM) Service.

Requirements
------------

Prior to installing this software, ensure your system meets the following
requirements:

* Python_ 3.13 or above. Python 2 is *not* supported.
* Terraform 1.0.11 or above. Note that Terraform is only required when deploying
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
    batch_size = 100

Bracketed fields within the template correspond to values which need to be filled
in by an end-user prior to using the `pds-ingress-client` script to transfer
files to PDS. The remaining fields should be left as-is.

To obtain the correct values for `<API_Gateway_ID>`, `<API_Gateway_Stage_Name>`
and `<Cognito_Client_ID>`, `<Cloudwatch_Log_Group_Name>` contact a PDS Operator.

To obtain values for `<Cognito_Username>` and `<Cognito_Password>`, consult
the section on User Registration within this document.

Running the Client script
^^^^^^^^^^^^^^^^^^^^^^^^^

Once the `pds-data-upload-manager` has been installed, you can run ``pds-ingress-client --help``
to get a usage message and ensure the client-side service is properly installed. You can
also consult the `usage_` documentation for more details.

Updating the Tool
-----------------

To check for and install an update to the tool, run the following command in
your virtual environment::

  pip install --upgrade pds-data-upload-manager

.. note::

    An update to an existing virtualenv installation of the PDS DUM Service may fail
    if the underlying minimum required Python version has changed. If so, a new
    virtual environment should be created using the required version of Python, after
    which the latest version of the Service may be installed into it. Consult the
    installation instructions above on how to create a new virtual environment.


.. References:
.. _usage: ../usage/index.html
.. _development: ../development/index.html
.. _terraform: ../terraform/index.html
.. _Pip: https://pip.pypa.io/en/stable/
.. _Python: https://www.python.org/
.. _`virtual environment`: https://docs.python.org/3/library/venv.html
.. _INI: https://en.wikipedia.org/wiki/INI_file
