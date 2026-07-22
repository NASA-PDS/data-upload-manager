⚙️ Operations
==============

This section covers tasks performed by PDS operators who deploy and administer
the DUM service in AWS.

Configuring the Server Side Bucket Map
---------------------------------------

Once the Server side components of DUM have been deployed to AWS (see terraform_ section),
how ingested files are routed to S3 buckets is controlled via a "Bucket Map" configuration
file which gets bundled with the "nucleus-dum-ingress-service" lambda function.

The format of the file is a simple YAML_ format file. An example bucket map is shown below::

    MAP:
      NODES:
        ATM:
          default:
            bucket:
              name: pds-nucleus-dum
        ENG:
          - prefix: path/to/archive/2022
            bucket:
              name: bucket-for-2022
              storage_class: STANDARD
          - prefix: weblogs/*
            bucket:
              name: pds-nucleus-weblogs
              storage_class: STANDARD
          default:
            bucket:
              name: pds-nucleus-dum
        GEO:
          default:
            bucket:
              name: pds-nucleus-dum
        IMG:
          default:
            bucket:
              name: pds-nucleus-dum
        NAIF:
          default:
            bucket:
              name: pds-nucleus-dum
        PPI:
          default:
            bucket:
              name: pds-nucleus-dum
        RMS:
          default:
            bucket:
              name: pds-nucleus-dum
        RS:
          default:
            bucket:
              name: pds-nucleus-dum
        SBN:
          default:
            bucket:
              name: pds-nucleus-dum


Within the mapping is are separate entries for each PDS Node which could make
an ingress request via the client script. Within each Node section are one or
more entry mappings, where an expected path prefix of a file requested for ingest
is mapped to the name of an S3 bucket where the file should be uploaded to.

In the above example, we can see that a default mapping is configured for all
nodes (except ENG) that instructs the Ingress Lambda function to route all files to the ``pds-nucleus-dum``
bucket. This is the mapping that is used when no other mapping for a path prefix exists.

Within the ``ENG`` section, we also see that a mapping from the ``path/to/archive/2022``
path prefix to the ``bucket-for-2022``, is also defined. This means that any requests
file paths that begin with ``path/to/archive/2022`` will be routed to the ``bucket-for-2022``
bucket during upload.

Bucket configuration settings can also be provided for each mapping.
Consult the current bucket map schema (available within the DUM repo under ``src/pds/ingress/service/config``)
for the full set of available options.

.. note::

    The ``--prefix`` argument of the ``pds-ingress-client`` script can be instrumental to ensure
    that paths requested for ingress have a prefix that matches one of the mappings expected by
    the bucket config. Consult the usage_ page for the ``pds-ingress-client`` for more details
    on using the ``--prefix`` argument.

Should there ever be a need to make modifications to the bucket map used with a
deployment of the DUM service, changes can be made to the file directly from within the
AWS Console Lambda Code Source editor window. Be sure that the function is redeployed after
any updates are made to the bucket map to ensure they take affect for subsequent ingress requests.

Adding Users to the AWS Cognito User Pool
------------------------------------------

Before the client-side script can be used to request ingest of files to PDS Cloud,
a valid user account must exist in the AWS Cognito User Pool deployed with the rest
of the DUM Server side components. Credentials for the user must then be provided in
the INI config used with the ``pds-ingress-client`` script.

Currently, there are only two ways to configure new users within the User Pool:

* Specify the list of users to pre-populate the User Pool with via the `.tfvars` file used with a Terraform deployment. See the terraform_ section for more information on how to configure this.
* Manually add new users via the AWS Admin Console for the Cognito service. More information on how to do so can be found here: https://docs.aws.amazon.com/cognito/latest/developerguide/how-to-create-user-accounts.html


Deploying the DUM Service
--------------------------

For instructions on deploying the DUM server-side components to AWS using Terraform,
see the :doc:`Terraform Deployment </terraform/index>` guide.

.. toctree::
   :hidden:

   /terraform/index

.. References:
.. _usage: ../usage/index.html
.. _YAML: https://yaml.org
