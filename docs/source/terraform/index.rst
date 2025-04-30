 🌎  Terraform
==================

This section describes how to deploy the server side components of the DUM to
AWS via Terraform_. These instructions are intended for PDS Engineering Node
operators who will be in charge of deploying and maintaining new instances of the
DUM server components. For submitters of data to PDS Cloud, consult the usage_
section for details on running the client-side script.

Prior to utilizing this documentation, ensure Terraform 1.0.11 or greater has
been installed on the same machine that the DUM repository has been cloned to.

Deployment Scripts
------------------

The DUM repository maintains a set of Terraform deployment scripts within the
`terraform` directory at the root of the repository. These scripts define the
AWS service components and their various inter-connections which Terraform
sets up automatically on a deployment.

The high-level Terraform script components consist of the following:

* A submodule for deploying Lambda functions used by DUM (under `terraform/modules/lambda`)
* A submodule for deploying the Cognito user authentication service (under `terraform/modules/cognito`)
* A submodule for deploying the API Gateway used to communicate with the client script (under `terraform/modules/api_gateway`)
* A main module which composes each of the submodues together to form the entire deployment (`terraform/main.tf`)

Creating the deployment .tfvars file
------------------------------------

By default, the Terraform scripts/modules described above are parameterized such that the service
can be easily deployed to different AWS environments without hardcoding any sensitive or account-specific
information within.

To provide values for the parameters that the Terraform scripts expect, a `tfvars` file must be created
to define the account-specific informations pertaining to the environment to deploy to. The following
template can be used when creating a new `tfvars` file for use with a specific AWS environment::

    # Terraform override variables for use with the MCP AWS environment
    localstack_context = false
    venue = "<dev|test|prod>"

    profile         = "<AWS_Profile_Name>"
    credential_file = "<Path_to_local_aws_credentials_file>"

    lambda_s3_bucket_name = "<S3_Bucket_Name>"

    api_gateway_policy_source_vpc = "<VPC_ID>"

    api_gateway_endpoint_type = <"REGIONAL"|"PRIVATE">

    api_gateway_lambda_role_arn         = "<AWS_IAM_Role_ARN>"
    lambda_ingress_service_iam_role_arn = "<AWS_IAM_Role_ARN>"
    lambda_authorizer_iam_role_arn      = "<AWS_IAM_Role_ARN>"

    nucleus_dum_cognito_initial_users = [
      {
        "username": "<Username>",
        "password": "<Password>",
        "group": "<PDS_Group_Name>"
        "email": "<Email address>"
      },
      ...
    ]

    lambda_ingress_service_default_buckets = [
      {
        name        = "pds-sbn-staging",
        description = "Default staging bucket for PDS Small Bodies Node"
      },
      ...
    ]


Each of the bracketed values above must be filled in with an appropriate value
prior to deployment. Descriptions of each field follow:

* ``<dev|test|prod>``: Name of the MCP venue to deploy to
* ``<AWS_Profile_Name>``: The AWS Profile/Account name of the environment to deploy to.
* ``<Path_to_local_aws_credentials_file>``: Path to a local file (such as ``~/.aws/credentials``) containing a valid set of AWS credentials_ for the specifed profile.
* ``<S3_Bucket_Name>``: Name of an S3 bucket which Terraform will use to stage intermediate build products. The bucket will be created by Terraform and should not already exist.
* ``<VPC_ID>``: ID of the Virtual Private Cloud instance where the deployed service will reside.
* ``<AWS_IAM_Role_ARN>``: Amazon Resource Name (ARN) for the AWS Identity Access Management Role which grants the required permissions for the DUM server components to communicate.
* ``<"REGIONAL"|"PRIVATE">``: Select the type of endpoint of the API Gateway. "REGIONAL" should only be used for deployments to the OPS environment.

.. note::
  * The selected Role(s) must include both ``lambda.amazonaws.com`` and ``apigateway.amazonaws.com`` as "Trusted Entities".
  * The policy attached to the Role(s) must also grant adequate permissions for the following services: API Gateway, Cloudwatch, Cloudwatch Logs, Lambda, and S3

* The `nucleus_dum_cognito_initial_users` can be populated with a list of dictionaries defining a set of user accounts to
  populate the Cognito user pool with upon creation. An arbitrary number of initial users can be provided.
    * The ``<Username>`` and ``<Password>`` fields can be anything, but the password must conform to the Password policy set on the Cognito user pool.
    * For ``<PDS_Group_Name>``, one of the following may be used: ``PDS_ATM_USERS, PDS_ENG_USERS, PDS_GEO_USERS, PDS_IMG_NODE, PDS_NAIF_USERS, PDS_PPI_USERS, PDS_RS_USERS, PDS_RMS_USERS, PDS_SBN_USERS``
    * ``<Email address>`` should be a valid email address for the user, as this is where things such as password resets will be sent.

* The `lambda_ingress_service_default_buckets` can be populated with a list of the default S3 buckets that should be created
  by Terraform for use with the bucket map of the Lambda Ingress Service.
    * Typically, there should be an entry for each PDS node that is expected to utilize DUM.
    * Each bucket name provided will be appended with the name of selected venue to ensure uniqueness across accounts. For example, an entry with the name "pds-sbn-staging" will result in a bucket named "pds-sbn-staging-prod" if the venue is set to "prod".

Setting up the S3 Backend
-------------------------

The Terraform scripts for DUM expect to utilize an S3 bucket as a "backend" to store the state of the Terraform-managed
deployment. The ``backend.tf`` file holds the configuration for where the backend ``.tfstate`` file should be stored and read on
subsequent deployments.

Below is the default state of ``backend.tf``::


    terraform {
      backend "s3" {
        bucket = "pds-infra"
        key    = "dev/dum_infra.tfstate"
        region = "us-west-2"
      }

If the ``.tfstate`` file is to reside in some other location within the venue, make sure this file is updated accordingly
before runnint ``terraform init``.


Deploying the Terraform
-----------------------

Once the user ``.tfvars`` is created and saved locally, run the following commands to deploy the DUM service with terraform::

    terraform init
    terraform plan -var-file="<path to user .tfvars file>" -out="pds-dum.tfplan"
    terraform apply "pds-dum.tfplan"

If everything is configured correctly, deployment should only take about 5-10 minutes.

Utilizing Terraform Outputs
---------------------------

On successful deployment, Terraform will output a number of key/value pairs with
information needed to configure the INI config of the client-side ``pds-ingress-client``
application.

A sample of this output follows::

    ingress_client_cloudwatch_log_group_name = "<Cloudwatch_Log_Group_Name>"
    nucleus_dum_api_id = "<API_Gateway_ID>"
    nucleus_dum_api_stages = [
      [
        "<API_Gateway_Stage_Name>",
      ],
    ]
    nucleus_dum_cognito_user_pool_client_id = "<Cognito_Client_ID>"
    nucleus_dum_cognito_users = [
      tolist([
        "<Cognito_Username>",
      ]),
    ]

Each of the bracketed fields correspond directly with the fields referenced in the
Client Configuration section of the installation_ documentation. The values of these
outputs should be securly stored for reference, as installers of the client script will
have a need to know these values when setting up their local INI config.

Destroying a Deployment
-----------------------

To destroy an existing deployment of the DUM Service, run the following from the same location
the initial deploy was executed::

    terraform destroy -var-file="<path to user .tfvars file>"

Where ``<path to user .tfvars file>`` is the same `.tfvars` file used for the initial deployment.

.. References:
.. _usage: ../usage/index.html
.. _installation: ../installation/index.html
.. _credentials: https://docs.aws.amazon.com/cli/latest/userguide/cli-authentication-short-term.html
.. _Terraform: https://www.terraform.io/
