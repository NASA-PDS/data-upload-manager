# Terraform module for the Data Upload Manager (DUM) Lambda Ingress Service

locals {
  ingress_src_dir = abspath("${path.root}/../src/pds/ingress/service")
  build_dir       = abspath("${path.module}/files")
}

# Instantiate bucket-map.yaml in the build directory to avoid fileset inconsistency
resource "local_file" "bucket_map" {
  content  = templatefile("${local.ingress_src_dir}/config/bucket-map.yaml.tmpl", { venue = var.venue })
  filename = "${local.build_dir}/bucket-map.yaml"
}

# Build and Zip the Lambda functions using local-exec to ensure ordering
resource "null_resource" "lambda_build_process" {
  triggers = {
    source_hash = sha256(join("", [for f in fileset(local.ingress_src_dir, "**") : filesha256("${local.ingress_src_dir}/${f}")]))
    map_id      = local_file.bucket_map.id
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      mkdir -p "${local.build_dir}"

      # 1. Zip Ingress Service
      TMP_INGRESS="${local.build_dir}/tmp_ingress"
      rm -rf "$TMP_INGRESS" && mkdir -p "$TMP_INGRESS"
      cp -r "${local.ingress_src_dir}/." "$TMP_INGRESS/"
      cp "${local.build_dir}/bucket-map.yaml" "$TMP_INGRESS/config/bucket-map.yaml"
      rm -f "$TMP_INGRESS/config/bucket-map.yaml.tmpl" "$TMP_INGRESS/pds_status_app.py"
      cd "$TMP_INGRESS" && zip -X -r "${local.build_dir}/dum-ingress-service.zip" .

      # 2. Zip Status Service
      TMP_STATUS="${local.build_dir}/tmp_status"
      rm -rf "$TMP_STATUS" && mkdir -p "$TMP_STATUS"
      cp -r "${local.ingress_src_dir}/." "$TMP_STATUS/"
      cp "${local.build_dir}/bucket-map.yaml" "$TMP_STATUS/config/bucket-map.yaml"
      rm -f "$TMP_STATUS/config/bucket-map.yaml.tmpl" "$TMP_STATUS/pds_ingress_app.py"
      cd "$TMP_STATUS" && zip -X -r "${local.build_dir}/dum-status-service.zip" .

      # 3. Zip Metadata Sync Service
      TMP_SYNC="${local.build_dir}/tmp_sync"
      rm -rf "$TMP_SYNC" && mkdir -p "$TMP_SYNC"
      cp -r "${local.ingress_src_dir}/." "$TMP_SYNC/"
      rm -rf "$TMP_SYNC/config" "$TMP_SYNC/util" "$TMP_SYNC/pds_status_app.py" "$TMP_SYNC/pds_ingress_app.py"
      cd "$TMP_SYNC" && zip -X -r "${local.build_dir}/metadata-sync-service.zip" .

      # 4. Build PyYAML Layer via Docker using Python 3.13
      rm -rf "${local.build_dir}/pyyaml" && mkdir -p "${local.build_dir}/pyyaml/python"
      docker run --rm -v "${local.build_dir}/pyyaml:/app" -w /app python:3.13-slim pip install pyyaml -t /app/python
      cd "${local.build_dir}/pyyaml" && zip -X -r "${local.build_dir}/layer-PyYAML.zip" ./python/

      # 5. Build Yamale Layer via Docker using Python 3.13
      rm -rf "${local.build_dir}/yamale" && mkdir -p "${local.build_dir}/yamale/python"
      docker run --rm -v "${local.build_dir}/yamale:/app" -w /app python:3.13-slim pip install yamale -t /app/python
      cd "${local.build_dir}/yamale" && zip -X -r "${local.build_dir}/layer-Yamale.zip" ./python/

      rm -rf "$TMP_INGRESS" "$TMP_STATUS" "$TMP_SYNC" "${local.build_dir}/pyyaml" "${local.build_dir}/yamale"
    EOT
  }

  depends_on = [local_file.bucket_map]
}

data "aws_caller_identity" "current" {}

# Deploy the zips to S3
module "lambda_bucket" {
  source        = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/bucket"
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
  source      = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/object"
  bucket      = module.lambda_bucket.bucket_id
  key         = "dum-ingress-service.zip"
  source_path = "${local.build_dir}/dum-ingress-service.zip"
  depends_on  = [null_resource.lambda_build_process]
}

module "lambda_status_service_s3_object" {
  source      = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/object"
  bucket      = module.lambda_bucket.bucket_id
  key         = "dum-status-service.zip"
  source_path = "${local.build_dir}/dum-status-service.zip"
  depends_on  = [null_resource.lambda_build_process]
}

module "metadata_sync_service_s3_object" {
  source      = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/object"
  bucket      = module.lambda_bucket.bucket_id
  key         = "metadata-sync-service.zip"
  source_path = "${local.build_dir}/metadata-sync-service.zip"
  depends_on  = [null_resource.lambda_build_process]
}

module "lambda_ingress_service_pyyaml_layer_s3_object" {
  source      = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/object"
  bucket      = module.lambda_bucket.bucket_id
  key         = "layer-PyYAML.zip"
  source_path = "${local.build_dir}/layer-PyYAML.zip"
  depends_on  = [null_resource.lambda_build_process]
}

module "lambda_ingress_service_yamale_layer_s3_object" {
  source      = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/object"
  bucket      = module.lambda_bucket.bucket_id
  key         = "layer-Yamale.zip"
  source_path = "${local.build_dir}/layer-Yamale.zip"
  depends_on  = [null_resource.lambda_build_process]
}

resource "aws_lambda_layer_version" "lambda_ingress_service_pyyaml_layer" {
  s3_bucket           = module.lambda_bucket.bucket_id
  s3_key              = module.lambda_ingress_service_pyyaml_layer_s3_object.s3_object_key
  layer_name          = "PyYAML"
  compatible_runtimes = ["python3.13"]
  count               = var.skip_lambda_layers ? 0 : 1
  lifecycle {
    ignore_changes = [source_code_hash]
  }
}

resource "aws_lambda_layer_version" "lambda_ingress_service_yamale_layer" {
  s3_bucket           = module.lambda_bucket.bucket_id
  s3_key              = module.lambda_ingress_service_yamale_layer_s3_object.s3_object_key
  layer_name          = "Yamale"
  compatible_runtimes = ["python3.13"]
  count               = var.skip_lambda_layers ? 0 : 1
  lifecycle {
    ignore_changes = [source_code_hash]
  }
}

# Create the Ingress Lambda functions
resource "aws_lambda_function" "lambda_ingress_service" {
  function_name = var.lambda_ingress_service_function_name
  description   = var.lambda_ingress_service_function_description
  s3_bucket     = module.lambda_bucket.bucket_id
  s3_key        = module.lambda_ingress_service_s3_object.s3_object_key
  runtime       = "python3.13"
  handler       = "pds_ingress_app.lambda_handler"

  source_code_hash = null_resource.lambda_build_process.triggers.source_hash
  role             = var.lambda_ingress_service_iam_role_arn

  layers = var.skip_lambda_layers ? [] : [
    aws_lambda_layer_version.lambda_ingress_service_pyyaml_layer[0].arn,
    aws_lambda_layer_version.lambda_ingress_service_yamale_layer[0].arn
  ]

  environment {
    variables = {
      BUCKET_MAP_FILE            = "bucket-map.yaml"
      BUCKET_MAP_LOCATION        = "config"
      BUCKET_MAP_SCHEMA_FILE     = "bucket-map.schema"
      BUCKET_MAP_SCHEMA_LOCATION = "config"
      LOG_LEVEL                  = "INFO"
      VERSION_LOCATION           = "config"
      VERSION_FILE               = "VERSION.txt"
      ENDPOINT_URL               = var.lambda_ingress_localstack_context ? "http://localhost.localstack.cloud:4566" : ""
      EXPECTED_BUCKET_OWNER      = var.expected_bucket_owner
    }
  }

  timeout     = 60
  memory_size = 4096
}

resource "aws_lambda_function" "lambda_status_service" {
  function_name = var.lambda_status_service_function_name
  description   = var.lambda_status_service_function_description
  s3_bucket     = module.lambda_bucket.bucket_id
  s3_key        = module.lambda_status_service_s3_object.s3_object_key
  runtime       = "python3.13"
  handler       = "pds_status_app.lambda_handler"

  source_code_hash = null_resource.lambda_build_process.triggers.source_hash
  role             = var.lambda_ingress_service_iam_role_arn

  layers = var.skip_lambda_layers ? [] : [
    aws_lambda_layer_version.lambda_ingress_service_pyyaml_layer[0].arn,
    aws_lambda_layer_version.lambda_ingress_service_yamale_layer[0].arn
  ]

  environment {
    variables = {
      BUCKET_MAP_FILE            = "bucket-map.yaml"
      BUCKET_MAP_LOCATION        = "config"
      BUCKET_MAP_SCHEMA_FILE     = "bucket-map.schema"
      BUCKET_MAP_SCHEMA_LOCATION = "config"
      LOG_LEVEL                  = "INFO"
      VERSION_LOCATION           = "config"
      VERSION_FILE               = "VERSION.txt"
      ENDPOINT_URL               = var.lambda_ingress_localstack_context ? "http://localhost.localstack.cloud:4566" : ""
      SMTP_CONFIG_SSM_KEY_PATH   = "/pds/dum/smtp/"
      EXPECTED_BUCKET_OWNER      = var.expected_bucket_owner
    }
  }

  timeout     = 60
  memory_size = 4096
}

resource "aws_lambda_function" "metadata_sync_service" {
  function_name = var.lambda_metadata_sync_service_function_name
  description   = var.lambda_metadata_sync_service_function_description
  s3_bucket     = module.lambda_bucket.bucket_id
  s3_key        = module.metadata_sync_service_s3_object.s3_object_key
  runtime       = "python3.13"
  handler       = "sync_s3_metadata.lambda_handler"

  source_code_hash = null_resource.lambda_build_process.triggers.source_hash
  role             = var.lambda_ingress_service_iam_role_arn

  environment {
    variables = {
      LOG_LEVEL             = "INFO"
      EXPECTED_BUCKET_OWNER = var.expected_bucket_owner
    }
  }

  timeout     = 900
  memory_size = 4096
}

resource "aws_cloudwatch_log_group" "lambda_ingress_service" {
  name              = "/aws/lambda/${aws_lambda_function.lambda_ingress_service.function_name}"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "lambda_status_service" {
  name              = "/aws/lambda/${aws_lambda_function.lambda_status_service.function_name}"
  retention_in_days = 30
}

module "staging_buckets" {
  source        = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/bucket"
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
