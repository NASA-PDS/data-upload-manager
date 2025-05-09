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

# Deploy the zips to S3
resource "aws_s3_bucket" "lambda_bucket" {
  bucket = var.lambda_s3_bucket_name
}

resource "aws_s3_object" "lambda_ingress_service" {
  bucket = aws_s3_bucket.lambda_bucket.id

  key    = "dum-ingress-service.zip"
  source = data.archive_file.lambda_ingress_service.output_path

  etag   = data.archive_file.lambda_ingress_service.output_md5
}

resource "aws_s3_object" "lambda_status_service" {
  bucket = aws_s3_bucket.lambda_bucket.id

  key    = "dum-status-service.zip"
  source = data.archive_file.lambda_status_service.output_path

  etag   = data.archive_file.lambda_status_service.output_md5
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

resource "aws_s3_object" "lambda_ingress_service_pyyaml_layer" {
  bucket = aws_s3_bucket.lambda_bucket.id

  key    = "layer-PyYAML.zip"
  source = "${path.module}/files/pyyaml/layer-PyYAML.zip"

  depends_on = [null_resource.lambda_ingress_service_pyyaml_layer]
}

resource "aws_s3_object" "lambda_ingress_service_yamale_layer" {
  bucket = aws_s3_bucket.lambda_bucket.id

  key    = "layer-Yamale.zip"
  source = "${path.module}/files/yamale/layer-Yamale.zip"

  depends_on = [null_resource.lambda_ingress_service_yamale_layer]
}

resource "aws_lambda_layer_version" "lambda_ingress_service_pyyaml_layer" {
  s3_bucket           = aws_s3_bucket.lambda_bucket.id
  s3_key              = aws_s3_object.lambda_ingress_service_pyyaml_layer.key
  layer_name          = "PyYAML"
  compatible_runtimes = ["python3.9","python3.10","python3.11","python3.12","python3.13"]
}

resource "aws_lambda_layer_version" "lambda_ingress_service_yamale_layer" {
  s3_bucket           = aws_s3_bucket.lambda_bucket.id
  s3_key              = aws_s3_object.lambda_ingress_service_yamale_layer.key
  layer_name          = "Yamale"
  compatible_runtimes = ["python3.9","python3.10","python3.11","python3.12","python3.13"]
}

# Create the Ingress Lambda functions using the zips uploaded to S3
resource "aws_lambda_function" "lambda_ingress_service" {
  function_name = var.lambda_ingress_service_function_name
  description   = var.lambda_ingress_service_function_description

  s3_bucket = aws_s3_bucket.lambda_bucket.id
  s3_key    = aws_s3_object.lambda_ingress_service.key

  runtime = "python3.10"
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

  s3_bucket = aws_s3_bucket.lambda_bucket.id
  s3_key    = aws_s3_object.lambda_status_service.key

  runtime = "python3.10"
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
resource "aws_s3_bucket" "staging_buckets" {
    count      = length(var.lambda_ingress_service_default_buckets)
    bucket     = "${var.lambda_ingress_service_default_buckets[count.index].name}-${var.venue}"
}
