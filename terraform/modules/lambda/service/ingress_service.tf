# Terraform module for the Data Upload Manager (DUM) Lambda Ingress Service

# Instantiate bucket-map.yaml based on the selected venue
resource "local_file" "bucket_map" {
    content  = templatefile("${path.root}/../src/pds/ingress/service/config/bucket-map.yaml.tmpl", { venue = var.venue })
    filename = "${path.root}/../src/pds/ingress/service/config/bucket-map.yaml"
}

# Zip the lambda function contents
data "archive_file" "lambda_ingress_service" {
  type        = "zip"
  source_dir  = "${path.root}/../src/pds/ingress/service"
  output_path = "${path.module}/files/dum-ingress-service.zip"
  excludes    = ["${path.root}/../src/pds/ingress/service/config/bucket-map.yaml.tmpl",
                 "${path.root}/../src/pds/ingress/service/pds_status_app.py"]

  depends_on = [local_file.bucket_map]
}

data "archive_file" "lambda_status_service" {
  type        = "zip"
  source_dir  = "${path.root}/../src/pds/ingress/service"
  output_path = "${path.module}/files/dum-status-service.zip"
  excludes    = ["${path.root}/../src/pds/ingress/service/config/bucket-map.yaml.tmpl",
                 "${path.root}/../src/pds/ingress/service/pds_ingress_app.py"]
}

data "aws_caller_identity" "current" {}

# Deploy the zips to S3
module "lambda_bucket" {
  source        = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/bucket"  # pragma: allowlist secret
  bucket_name   = var.lambda_s3_bucket_name
  partition     = var.lambda_s3_bucket_partition
  bucket_policy = <<POLICY
  {
     "Version": "2012-10-17",
     "Statement": [
         {
             "Sid": "AllowOnlyMCPTenantOperator",
             "Effect": "Allow",
             "Principal": {
               "AWS": [
                 "arn:${var.lambda_s3_bucket_partition}:iam::${data.aws_caller_identity.current.account_id}:role/mcp-tenantOperator"
               ]
             },
             "Action": "s3:*",
             "Resource": [
                 "arn:${var.lambda_s3_bucket_partition}:s3:::${var.lambda_s3_bucket_name}/*",
                 "arn:${var.lambda_s3_bucket_partition}:s3:::${var.lambda_s3_bucket_name}"
             ]
         },
         {
             "Sid": "AllowSSLRequestsOnly",
             "Effect": "Deny",
             "Principal": "*",
             "Action": "s3:*",
             "Resource": [
                "arn:${var.lambda_s3_bucket_partition}:s3:::${var.lambda_s3_bucket_name}",
                "arn:${var.lambda_s3_bucket_partition}:s3:::${var.lambda_s3_bucket_name}/*"
              ],
              "Condition": {
                "Bool": {
                   "aws:SecureTransport": "false"
                 }
             }
         }
     ]
  }
  POLICY
  enable_blocks = true
  enable_policy = true

  required_tags = {
    project = var.project
    cicd    = var.cicd
  }
}

module "lambda_ingress_service_s3_object" {
  source      = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/object"  # pragma: allowlist secret
  bucket      = module.lambda_bucket.bucket_id
  key         = "dum-lambda-auth.zip"
  source_path = data.archive_file.lambda_ingress_service.output_path
}

module "lambda_status_service_s3_object" {
  source      = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/object"  # pragma: allowlist secret
  bucket      = module.lambda_bucket.bucket_id
  key         = "dum-status-service.zip"
  source_path = data.archive_file.lambda_status_service.output_path
}

# Create the Yaml package layers needed by the Ingress Service Lambda to parse
# and validate the bucket map, then deploy the zips to S3
# Note that the creation of the zip files are included here to ensure the
# directory structure matches what AWS expects
resource "null_resource" "lambda_ingress_service_pyyaml_layer" {
  provisioner "local-exec" {
    command = <<-EOT
      python3 -m venv ${path.module}/files/pyyaml
      source ${path.module}/files/pyyaml/bin/activate
      pip install pyyaml -t ${path.module}/files/pyyaml/python
      deactivate
      cd ${path.module}/files/pyyaml
      zip -r layer-PyYAML.zip ./python/
    EOT
  }
}

resource "null_resource" "lambda_ingress_service_yamale_layer" {
  provisioner "local-exec" {
    command = <<-EOT
      python3 -m venv ${path.module}/files/yamale
      source ${path.module}/files/yamale/bin/activate
      pip install yamale -t ${path.module}/files/yamale/python
      deactivate
      cd ${path.module}/files/yamale
      zip -r layer-Yamale.zip ./python/
    EOT
  }
}

module "lambda_ingress_service_pyyaml_layer_s3_object" {
  source      = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/object"  # pragma: allowlist secret
  bucket      = module.lambda_bucket.bucket_id
  key         = "layer-PyYAML.zip"
  source_path = "${path.module}/files/pyyaml/layer-PyYAML.zip"

  depends_on = [null_resource.lambda_ingress_service_pyyaml_layer]
}

module "lambda_ingress_service_yamale_layer_s3_object" {
  source      = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/object"  # pragma: allowlist secret
  bucket      = module.lambda_bucket.bucket_id
  key         = "layer-Yamale.zip"
  source_path = "${path.module}/files/yamale/layer-Yamale.zip"

  depends_on = [null_resource.lambda_ingress_service_yamale_layer]
}

resource "aws_lambda_layer_version" "lambda_ingress_service_pyyaml_layer" {
  s3_bucket           = module.lambda_bucket.bucket_id
  s3_key              = "layer-PyYAML.zip"
  layer_name          = "PyYAML"
  compatible_runtimes = ["python3.9","python3.10","python3.11","python3.12","python3.13"]
}

resource "aws_lambda_layer_version" "lambda_ingress_service_yamale_layer" {
  s3_bucket           = module.lambda_bucket.bucket_id
  s3_key              = "layer-Yamale.zip"
  layer_name          = "Yamale"
  compatible_runtimes = ["python3.9","python3.10","python3.11","python3.12","python3.13]
}

# Create the Ingress Lambda functions using the zips uploaded to S3
resource "aws_lambda_function" "lambda_ingress_service" {
  function_name = var.lambda_ingress_service_function_name
  description   = var.lambda_ingress_service_function_description

  s3_bucket = module.lambda_bucket.bucket_id
  s3_key    = module.lambda_ingress_service_s3_object.s3_object_key

  runtime = "python3.13"
  handler = "pds_ingress_app.lambda_handler"

  source_code_hash = data.archive_file.lambda_ingress_service.output_base64sha256

  role = var.lambda_ingress_service_iam_role_arn

  layers = [aws_lambda_layer_version.lambda_ingress_service_pyyaml_layer.arn,
            aws_lambda_layer_version.lambda_ingress_service_yamale_layer.arn]

  environment {
    variables = {
      BUCKET_MAP_FILE            = "bucket-map.yaml",
      BUCKET_MAP_LOCATION        = "config",
      BUCKET_MAP_SCHEMA_FILE     = "bucket-map.schema",
      BUCKET_MAP_SCHEMA_LOCATION = "config",
      LOG_LEVEL                  = "INFO",
      VERSION_LOCATION           = "config",
      VERSION_FILE               = "VERSION.txt"
      ENDPOINT_URL               = var.lambda_ingress_localstack_context ? "http://localhost.localstack.cloud:4566" : ""
    }
  }

  # Timeout value set to match current upper limit of API Gateway integration response timeout
  timeout = 60
}

resource "aws_lambda_function" "lambda_status_service" {
  function_name = var.lambda_status_service_function_name
  description   = var.lambda_status_service_function_description

  s3_bucket = module.lambda_bucket.bucket_id
  s3_key    = module.lambda_status_service_s3_object.s3_object_key

  runtime = "python3.13"
  handler = "pds_status_app.lambda_handler"

  source_code_hash = data.archive_file.lambda_status_service.output_base64sha256

  role = var.lambda_ingress_service_iam_role_arn

  layers = [aws_lambda_layer_version.lambda_ingress_service_pyyaml_layer.arn,
            aws_lambda_layer_version.lambda_ingress_service_yamale_layer.arn]

  environment {
    variables = {
      BUCKET_MAP_FILE            = "bucket-map.yaml",
      BUCKET_MAP_LOCATION        = "config",
      BUCKET_MAP_SCHEMA_FILE     = "bucket-map.schema",
      BUCKET_MAP_SCHEMA_LOCATION = "config",
      LOG_LEVEL                  = "INFO",
      VERSION_LOCATION           = "config",
      VERSION_FILE               = "VERSION.txt"
      ENDPOINT_URL               = var.lambda_ingress_localstack_context ? "http://localhost.localstack.cloud:4566" : ""
      SMTP_CONFIG_SSM_KEY_PATH   = "/pds/dum/smtp/"
    }
  }

  # Timeout value set to match current upper limit of API Gateway integration response timeout
  timeout = 60
}

resource "aws_cloudwatch_log_group" "lambda_ingress_service" {
  name = "/aws/lambda/${aws_lambda_function.lambda_ingress_service.function_name}"

  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "lambda_status_service" {
  name = "/aws/lambda/${aws_lambda_function.lambda_status_service.function_name}"

  retention_in_days = 30
}

# Create the default staging buckets referenced by the bucket-map
module "staging_buckets" {
  source        = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/bucket"  # pragma: allowlist secret
  count         = length(var.lambda_ingress_service_default_buckets)
  bucket_name   = "${var.lambda_ingress_service_default_buckets[count.index].name}-${var.venue}"
  partition     = var.lambda_s3_bucket_partition
  bucket_policy = <<POLICY
  {
     "Version": "2012-10-17",
     "Statement": [
         {
             "Effect": "Allow",
             "Principal": {
                "AWS": [
                  "arn:${var.lambda_s3_bucket_partition}:iam::${data.aws_caller_identity.current.account_id}:role/mcp-tenantOperator"
               ]
             },
             "Action": "s3:*",
             "Resource": [
                 "arn:${var.lambda_s3_bucket_partition}:s3:::${var.lambda_ingress_service_default_buckets[count.index].name}-${var.venue}/*",
                 "arn:${var.lambda_s3_bucket_partition}:s3:::${var.lambda_ingress_service_default_buckets[count.index].name}-${var.venue}"
             ]
         },
         {
             "Sid": "AllowSSLRequestsOnly",
             "Effect": "Deny",
             "Principal": "*",
             "Action": "s3:*",
             "Resource": [
                "arn:${var.lambda_s3_bucket_partition}:s3:::${var.lambda_ingress_service_default_buckets[count.index].name}-${var.venue}/*",
                "arn:${var.lambda_s3_bucket_partition}:s3:::${var.lambda_ingress_service_default_buckets[count.index].name}-${var.venue}"
              ],
              "Condition": {
                "Bool": {
                   "aws:SecureTransport": "false"
                 }
             }
         }
     ]
  }
  POLICY
  enable_blocks = true
  enable_policy = true

  required_tags = {
    project = var.project
    cicd    = var.cicd
  }
}
