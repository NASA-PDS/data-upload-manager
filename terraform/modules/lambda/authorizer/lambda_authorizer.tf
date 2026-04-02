# Terraform module for the Data Upload Manager (DUM) Lambda Authorizer

locals {
  authorizer_src_dir   = abspath("${path.root}/../src/pds/ingress/authorizer")
  authorizer_zip_path  = abspath("${path.module}/files/dum-lambda-auth.zip")
  authorizer_build_dir = abspath("${path.module}/files/build-authorizer")
}

# Build the Lambda authorizer package in a clean Docker-based Node 18 environment
resource "null_resource" "lambda_authorizer_build" {
  triggers = {
    source_hash = sha256(join("", [for f in fileset(local.authorizer_src_dir, "*") : filesha256("${local.authorizer_src_dir}/${f}")]))
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      rm -rf "${local.authorizer_build_dir}" "${local.authorizer_zip_path}"
      mkdir -p "${local.authorizer_build_dir}"

      cp -r "${local.authorizer_src_dir}/." "${local.authorizer_build_dir}/"

      # Install dependencies using Docker Node 18
      docker run --rm \
        -u $(id -u):$(id -g) \
        -v "${local.authorizer_build_dir}:/app" \
        -w /app \
        --env HOME=/tmp \
        node:18-slim \
        sh -c "npm ci --omit=dev"

      # Create deterministic zip
      cd "${local.authorizer_build_dir}" && zip -X -r "${local.authorizer_zip_path}" .
    EOT
  }
}

data "aws_s3_bucket" "lambda_bucket" {
  bucket = var.lambda_s3_bucket_name
}

module "lambda_authorizer_s3_object" {
  source      = "git@github.com:NASA-PDS/pds-tf-modules.git//terraform/modules/s3/object"
  bucket      = data.aws_s3_bucket.lambda_bucket.id
  key         = "dum-lambda-auth.zip"
  source_path = local.authorizer_zip_path
  depends_on  = [null_resource.lambda_authorizer_build]
}

resource "aws_lambda_function" "lambda_authorizer" {
  function_name = var.lambda_authorizer_function_name
  description   = var.lambda_authorizer_function_description
  s3_bucket     = data.aws_s3_bucket.lambda_bucket.id
  s3_key        = module.lambda_authorizer_s3_object.s3_object_key
  runtime       = "nodejs18.x"
  handler       = "index.handler"
  source_code_hash = null_resource.lambda_authorizer_build.triggers.source_hash
  role          = var.lambda_authorizer_iam_role_arn

  environment {
    variables = {
      COGNITO_USER_POOL_ID   = var.lambda_authorizer_cognito_pool_id
      COGNITO_CLIENT_ID_LIST = var.lambda_authorizer_cognito_client_id
      LOCALSTACK_CONTEXT     = var.lambda_authorizer_localstack_context
    }
  }

  depends_on = [module.lambda_authorizer_s3_object]
}

resource "aws_cloudwatch_log_group" "lambda_authorizer" {
  name              = "/aws/lambda/${var.lambda_authorizer_function_name}"
  retention_in_days = 30
}
