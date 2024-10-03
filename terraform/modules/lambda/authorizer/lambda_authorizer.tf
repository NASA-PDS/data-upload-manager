# Terraform module for the Data Upload Manager (DUM) Lambda Authorizer

# Run npm install to ensure required modules are downloaded locally
resource "null_resource" "lambda_authorizer_npm_modules" {
  provisioner "local-exec" {
    command = <<-EOT
      cd ${path.root}/../src/pds/ingress/authorizer
      npm install
    EOT
  }
}

# Zip the lambda function contents
data "archive_file" "lambda_authorizer" {
  type        = "zip"
  source_dir  = "${path.root}/../src/pds/ingress/authorizer"
  output_path = "${path.module}/files/dum-lambda-auth.zip"

  depends_on = [null_resource.lambda_authorizer_npm_modules]
}

# Deploy the zip to S3, this bucket should have already been created by the
# Ingress Service Lambda Terraform script
data "aws_s3_bucket" "lambda_bucket" {
  bucket = var.lambda_s3_bucket_name
}

resource "aws_s3_object" "lambda_authorizer" {
  bucket = data.aws_s3_bucket.lambda_bucket.id

  key    = "dum-lambda-auth.zip"
  source = data.archive_file.lambda_authorizer.output_path

  etag   = data.archive_file.lambda_authorizer.output_md5

  depends_on = [data.archive_file.lambda_authorizer]
}

# Create the Lambda Authorizer function using the zip uploaded to S3
resource "aws_lambda_function" "lambda_authorizer" {
  function_name = var.lambda_authorizer_function_name
  description   = var.lambda_authorizer_function_description

  s3_bucket = data.aws_s3_bucket.lambda_bucket.id
  s3_key    = aws_s3_object.lambda_authorizer.key

  runtime = "nodejs18.x"
  handler = "index.handler"

  source_code_hash = data.archive_file.lambda_authorizer.output_base64sha256

  role = var.lambda_authorizer_iam_role_arn

  environment {
    variables = {
      COGNITO_USER_POOL_ID   = var.lambda_authorizer_cognito_pool_id
      COGNITO_CLIENT_ID_LIST = var.lambda_authorizer_cognito_client_id
      LOCALSTACK_CONTEXT     = var.lambda_authorizer_localstack_context
    }
  }
}

resource "aws_cloudwatch_log_group" "lambda_authorizer" {
  name = "/aws/lambda/${aws_lambda_function.lambda_authorizer.function_name}"

  retention_in_days = 30
}
