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


Smoke Testing Weblog Ingress
-----------------------------

After deploying the DUM service, or after changing the bucket map, the weblog path can be checked end to end with
the ``integration/scripts/weblog_smoke_test.sh`` script. The script:

1. Creates a few empty gzip files named like weblogs.
2. Uploads them as the Engineering node with ``pds-ingress-client --weblogs``.
3. Confirms each file arrived in the weblogs bucket at the expected key with the expected size.
4. Deletes exactly those objects from the bucket and confirms they are gone.

The weblogs bucket, AWS region and AWS CLI profile are required arguments. The AWS credentials in use need
permission to read and delete objects in that bucket, and the INI config must contain valid Cognito credentials for
a user in the Engineering node group::

    WEBLOGS_BUCKET="<weblogs bucket name>"
    DUM_CONFIG="<path to the client INI config>"
    AWS_REGION="<aws region>"
    AWS_PROFILE_NAME="<aws cli profile>"
    integration/scripts/weblog_smoke_test.sh \
      --bucket "${WEBLOGS_BUCKET}" \
      --config "${DUM_CONFIG}" \
      --region "${AWS_REGION}" \
      --profile "${AWS_PROFILE_NAME}"

The script exits with status 0 only if the upload, verification, delete and delete verification all succeed. Use
``--node`` to test a different node, ``--log-type`` to change the log type, and ``--count`` to change the number of
files. Run the script with ``--help`` for the full list of options.

Every file created by the script contains a unique run ID, and only those exact object keys are deleted. If the
weblogs bucket has versioning enabled, the delete leaves a delete marker and the uploaded (empty) object versions
are retained.

If the script reports a failure at the upload step, follow the procedure in the next section.

Troubleshooting Ingress Request Failures
-----------------------------------------

When the ``pds-ingress-client`` reports a failure while requesting a batch, it prints only the HTTP
status and a generic message. The client does not display the service response body, so the cause of
a failure is found in the AWS-side logs. The procedure below applies to any ingress request that fails with
an HTTP 5xx status, for example::

    Ingress request failed with HTTP status 500 (Internal Server Error)
    The ingestion service encountered an internal error and could not process this request.
    Please contact PDS Engineering for assistance.

The steps require the AWS CLI, with credentials that can read CloudWatch Logs and Lambda
configuration in the account where DUM is deployed.

Step 1: Collect Details From the Reporter
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Ask the person who hit the failure for the following:

* The exact command line they ran, with credentials removed.
* The DUM client version printed at startup (``Starting PDS Data Upload Manager Client vX.Y.Z``).
* The PDS node ID (``--node``) and whether ``--weblogs`` was used.
* The client log file. Its location is printed at startup (``Logging to file ...``).
* The date and time of each failed attempt, including the time zone.

Note the timestamp of the ``Requesting Batch`` log line in the client log for each failed attempt.
Convert it to UTC, because CloudWatch Logs search windows are specified in UTC.

Step 2: Set Shell Variables
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Set the values used by every command in the remaining steps. The Lambda function name is the value of the
``lambda_ingress_service_function_name`` Terraform variable (``nucleus-dum-ingress-service`` unless overridden).
Set ``START_UTC`` and ``END_UTC`` to a window of a few minutes around the failed attempt::

    AWS_REGION="us-west-2"
    FUNCTION_NAME="nucleus-dum-ingress-service"
    LOG_GROUP="/aws/lambda/${FUNCTION_NAME}"
    START_UTC="2026-01-01T00:00:00Z"
    END_UTC="2026-01-01T00:10:00Z"

Convert the window to the epoch milliseconds that CloudWatch expects. On Linux::

    START_MS=$(date -u -d "${START_UTC}" +%s)000
    END_MS=$(date -u -d "${END_UTC}" +%s)000

On macOS::

    START_MS=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "${START_UTC}" +%s)000
    END_MS=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "${END_UTC}" +%s)000

Step 3: Search the Ingress Lambda Logs
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Look for errors the Lambda logged during the failure window::

    aws logs filter-log-events \
      --region "${AWS_REGION}" \
      --log-group-name "${LOG_GROUP}" \
      --start-time "${START_MS}" \
      --end-time "${END_MS}" \
      --filter-pattern "?ERROR ?Traceback ?\"Task timed out\" ?\"Runtime exited\"" \
      --query "events[].message" \
      --output text

Each failure produces one of the outcomes below. Match what is found to the table in Step 4.

* **Log lines containing** ``Ingress request failed inside worker thread`` **followed by a Python traceback.**
  The client prints the ``request_id`` from the service response and the API Gateway request IDs when a request
  fails. Search the log group for the ``request_id`` value to find all log lines for that invocation.
  The Lambda handled the request and failed while processing one of the files. The last line of the traceback
  is the cause.
* **Log lines containing** ``INTERNAL ERROR: Lambda cannot access staging bucket`` **or**
  ``INTERNAL ERROR: Lambda cannot access archive bucket``. The Lambda execution role cannot reach the
  bucket that the bucket map selected for the file.
* **A traceback with no** ``worker thread`` **message.** The Lambda failed before it began processing files
  (loading the bucket map, parsing the request body, or reading the version file).
* **A** ``Task timed out`` **or** ``Runtime exited`` **message.** The Lambda ran out of time or memory.
* **No events at all in the window.** The request never reached the Lambda. Go to Step 6.

To read every log line in the window, including the ``START``, ``END`` and ``REPORT`` lines that show the
request ID, duration and memory use of each invocation, run the same command without a filter pattern.
Narrow ``START_UTC`` and ``END_UTC`` to a minute or two first, because all invocations in the window are shown::

    aws logs filter-log-events \
      --region "${AWS_REGION}" \
      --log-group-name "${LOG_GROUP}" \
      --start-time "${START_MS}" \
      --end-time "${END_MS}" \
      --query "events[].message" \
      --output text

Step 4: Match the Log Message to a Cause
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 35 35 30

   * - Log evidence
     - Likely cause
     - Where to go next
   * - ``Staging bucket '<name>' does not exist (404 Not Found)`` or ``Archive bucket '<name>' does not exist (404 Not Found)``,
       followed by ``INTERNAL ERROR: Lambda cannot access ... bucket``
     - The bucket map names a bucket that does not exist in the account and region of the Lambda. The bucket
       name is misspelled in the bucket map, or the bucket has not been created.
     - Step 5b, then 5c
   * - ``Staging bucket '<name>' exists but access is forbidden (403)`` or the same message for the archive bucket,
       followed by ``INTERNAL ERROR: Lambda cannot access ... bucket``
     - The bucket exists but the Lambda role or the bucket policy denies access.
     - Step 5a
   * - ``TypeError: 'NoneType' object is not subscriptable`` raised from ``process_ingress_request``
     - The bucket map has no entry matching the requested path and no ``default`` entry for the node.
     - Step 5b
   * - Log line ``No bucket map entries configured for node ID`` followed by a bare ``RuntimeError``
     - The node ID in the request has no section in the bucket map.
     - Step 5b
   * - ``ValueError`` or ``binascii.Error`` raised from ``bytes.fromhex``
     - The request carried a malformed MD5 checksum.
     - Step 5d
   * - ``One or more missing fields in request index N``
     - The request body is missing one of ``ingress_path``, ``trimmed_path``, ``md5``, ``size`` or ``last_modified``.
     - Step 5d
   * - ``RuntimeError: No version file found``
     - The version file is missing from the deployed Lambda package.
     - Redeploy the Lambda, then retry.
   * - ``Failed to generate a presigned URL``
     - The Lambda role lacks permission to sign requests for the bucket, or the S3 call failed.
     - Step 5a
   * - ``Task timed out after N seconds``
     - The batch is too large or S3 calls are slow.
     - Ask the client to retry with a smaller ``batch_size`` in the INI config.

Step 5: Verify the Suspected Cause
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**5a. Lambda cannot reach a bucket.**

Find the role the function runs as and the bucket names the Lambda tried to use::

    ROLE_ARN=$(aws lambda get-function-configuration \
      --region "${AWS_REGION}" \
      --function-name "${FUNCTION_NAME}" \
      --query "Role" \
      --output text)
    echo "${ROLE_ARN}"

Take the bucket name from the ``INTERNAL ERROR`` log line and confirm the bucket exists::

    BUCKET_NAME="<bucket name from the log line>"
    aws s3api head-bucket --bucket "${BUCKET_NAME}" --region "${AWS_REGION}"

Then check that the role is allowed to read and write objects in it::

    aws iam simulate-principal-policy \
      --policy-source-arn "${ROLE_ARN}" \
      --action-names s3:ListBucket s3:GetObject s3:PutObject s3:CreateMultipartUpload \
      --resource-arns "arn:aws:s3:::${BUCKET_NAME}" "arn:aws:s3:::${BUCKET_NAME}/*" \
      --query "EvaluationResults[].[EvalActionName,EvalDecision]" \
      --output text

Every action must report ``allowed``. For a bucket in another account, the bucket policy in that
account must also grant the role access. Add the missing permission to the role policy or bucket
policy, then retry the upload.

**5b. Bucket map does not cover the request.**

The bucket map is the file ``config/bucket-map.yaml`` inside the ingress Lambda's code package. To view it in the
AWS Console, open **Lambda > Functions**, select the ingress function, and open ``config/bucket-map.yaml`` from the
file tree on the **Code** tab. The environment variables ``BUCKET_MAP_LOCATION`` and ``BUCKET_MAP_FILE`` under
**Configuration > Environment variables** identify the file. The status Lambda is deployed with its own copy.

The file is generated by Terraform from ``src/pds/ingress/service/config/bucket-map.yaml.tmpl``, with the ``venue``
Terraform variable substituted into the bucket names. Changes made in the Console editor are replaced by the next
Terraform apply, so make lasting changes in the template or the ``.tfvars`` file.

To read the file from the command line instead, download the code package deployed to the Lambda::

    CODE_URL=$(aws lambda get-function \
      --region "${AWS_REGION}" \
      --function-name "${FUNCTION_NAME}" \
      --query "Code.Location" \
      --output text)
    WORK_DIR=$(mktemp -d)
    curl -s -o "${WORK_DIR}/lambda.zip" "${CODE_URL}"
    unzip -q "${WORK_DIR}/lambda.zip" -d "${WORK_DIR}/code"
    find "${WORK_DIR}/code" -name "*.yaml" -o -name "*.yml"

Open the bucket map file and confirm all of the following for the requesting node:

1. The node ID (upper case, for example ``NAIF``) has a section under ``NODES``.
2. The section has a ``default`` entry, or a path entry whose ``prefix`` matches the requested
   path. For weblog uploads the path starts with ``weblogs/<node>-<log_type>/``, for example
   ``weblogs/naif-apache/``.
3. Every bucket named in the section exists and passes Step 5a.

Add the missing entry (see `Configuring the Server Side Bucket Map`_), redeploy the function, and retry.

**5c. Bucket named in the bucket map does not exist.**

Confirm that the bucket is missing, then find the bucket that should have been named::

    BUCKET_NAME="<bucket name from the 404 log line>"
    aws s3api head-bucket --bucket "${BUCKET_NAME}" --region "${AWS_REGION}"
    aws s3api list-buckets --query "Buckets[].Name" --output text

A ``404`` from ``head-bucket`` confirms the bucket does not exist. Compare the names in the ``list-buckets`` output
with the staging and archive bucket names in the node's section of the bucket map (Step 5b). Either correct the
names in the bucket map and redeploy the function, or create the missing buckets and grant the Lambda role
access to them (Step 5a). The staging and archive buckets are both checked for every request, so both must exist.

**5d. Malformed request.**

Ask the reporter to re-run the client with ``--manifest-path`` pointing to a new file, then inspect the
manifest for entries with an empty or non-hexadecimal ``md5`` value, or a ``size`` or
``last_modified`` that is missing. Zero-length or unreadable files in the input set are a common cause.

Step 6: No Lambda Logs Exist for the Failure
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When Step 3 finds no events for the window, the request failed before reaching the ingress Lambda.
Work through these checks in order:

1. Confirm the time window and time zone. Widen ``START_UTC`` and ``END_UTC`` by an hour in each direction.
2. Check the authorizer Lambda log group for errors in the same window. The authorizer function name is the
   value of the ``lambda_authorizer_function_name`` Terraform variable::

       AUTHORIZER_NAME="<authorizer function name>"
       aws logs filter-log-events \
         --region "${AWS_REGION}" \
         --log-group-name "/aws/lambda/${AUTHORIZER_NAME}" \
         --start-time "${START_MS}" \
         --end-time "${END_MS}" \
         --query "events[].message" \
         --output text

3. Check the ingress Lambda for throttling or errors with CloudWatch metrics::

       aws cloudwatch get-metric-statistics \
         --region "${AWS_REGION}" \
         --namespace AWS/Lambda \
         --metric-name Errors \
         --dimensions Name=FunctionName,Value="${FUNCTION_NAME}" \
         --start-time "${START_UTC}" \
         --end-time "${END_UTC}" \
         --period 60 \
         --statistics Sum

   Repeat with ``--metric-name Throttles`` and ``--metric-name Invocations``.
4. Enable API Gateway execution logging for the stage in the AWS Console (Stage > Logs and tracing), repeat
   the upload, and read the ``API-Gateway-Execution-Logs`` log group.

Step 7: Reproduce the Request and Read the Response Body
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To see the response body the client does not print, send one request directly. Run this from a network
that is allowed to reach the API Gateway endpoint, using a Cognito user that belongs to the node's user group::

    AWS_REGION="us-west-2"
    API_ID="<api gateway id from the INI config>"
    API_STAGE="<api gateway stage from the INI config>"
    CLIENT_ID="<cognito app client id from the INI config>"
    COGNITO_USER="<cognito user name>"
    NODE_ID="naif"
    NODE_NAME="<node long name as used by the client>"
    USER_GROUP="<cognito group name for the node>"
    CLIENT_VERSION="<client version reported by the user>"
    read -r -s -p "Cognito password: " COGNITO_PASSWORD
    ACCESS_TOKEN=$(aws cognito-idp initiate-auth \
      --region "${AWS_REGION}" \
      --auth-flow USER_PASSWORD_AUTH \
      --client-id "${CLIENT_ID}" \
      --auth-parameters "USERNAME=${COGNITO_USER},PASSWORD=${COGNITO_PASSWORD}" \
      --query "AuthenticationResult.AccessToken" \
      --output text)

Build a request body with a single file. Use the same ``trimmed_path`` form the client sends, for example a
path under ``weblogs/<node>-<log_type>/`` for a weblog upload::

    cat > request.json <<EOF
    [
      {
        "ingress_path": "/path/to/local/access.log.gz",
        "trimmed_path": "weblogs/${NODE_ID}-apache/access.log.gz",
        "md5": "d41d8cd98f00b204e9800998ecf8427e",
        "size": 1024,
        "last_modified": 1767225600.0
      }
    ]
    EOF

Send it. The URL is built from the ``url_template`` in the client INI config::

    API_URL="https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com/${API_STAGE}/request"
    curl -i -X POST "${API_URL}?node=${NODE_ID}&node_name=${NODE_NAME}" \
      -H "Authorization: Bearer ${ACCESS_TOKEN}" \
      -H "UserGroup: ${USER_GROUP}" \
      -H "ForceOverwrite: 0" \
      -H "ClientVersion: ${CLIENT_VERSION}" \
      -H "content-type: application/json" \
      --data @request.json

Read the response:

* ``{"error": "Internal server error: the ingestion service encountered a failure ..."}`` is a handled Lambda
  failure. The cause is in the log group (Step 3).
* ``{"message": "Internal server error"}`` is an unhandled Lambda error returned by API Gateway.
  The cause is a traceback in the log group that has no ``worker thread`` message (Step 3).
* ``403`` indicates the caller's network is blocked by the web ACL, and ``401`` indicates the Cognito user is not
  in the required user group.

The ``x-amzn-requestid`` response header can be used as the ``REQUEST_ID`` in Step 3.

Step 8: Record the Result
^^^^^^^^^^^^^^^^^^^^^^^^^^

Add the matching log lines, the cause, and the fix to the GitHub issue for the failure, with account IDs,
bucket names and user names removed.

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
