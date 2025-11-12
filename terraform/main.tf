# Main Terraform module for automated deployment of the PDS Data Upload Manager (DUM)

provider "aws" {
  region                   = var.region
}

module "nucleus_dum_ingress_service_lambda" {
  source = "./modules/lambda/service"

  project                                = var.project
  cicd                                   = var.cicd
  venue                                  = var.venue
  lambda_s3_bucket_name                  = var.lambda_s3_bucket_name
  lambda_ingress_service_iam_role_arn    = var.lambda_ingress_service_iam_role_arn
  lambda_ingress_localstack_context      = var.localstack_context
  lambda_ingress_service_default_buckets = var.lambda_ingress_service_default_buckets
}

module "nucleus_dum_status_queue" {
  source = "./modules/sqs"
}

resource "aws_lambda_event_source_mapping" "lambda_status_service_sqs_trigger" {
  event_source_arn = module.nucleus_dum_status_queue.nucleus_dum_sqs_arn
  function_name    = module.nucleus_dum_ingress_service_lambda.lambda_status_service_function_name

  function_response_types = ["ReportBatchItemFailures"]

  depends_on = [module.nucleus_dum_ingress_service_lambda, module.nucleus_dum_status_queue]
}

module "nucleus_dum_cognito" {
  source = "./modules/cognito"

  nucleus_dum_cognito_initial_users = var.nucleus_dum_cognito_initial_users
}

module "nucleus_dum_lambda_authorizer" {
  source = "./modules/lambda/authorizer"

  lambda_s3_bucket_name                = var.lambda_s3_bucket_name
  lambda_authorizer_iam_role_arn       = var.lambda_authorizer_iam_role_arn
  lambda_authorizer_cognito_pool_id    = module.nucleus_dum_cognito.nucleus_dum_cognito_user_pool_id
  lambda_authorizer_cognito_client_id  = module.nucleus_dum_cognito.nucleus_dum_cognito_user_pool_client_id
  lambda_authorizer_localstack_context = var.localstack_context

  depends_on = [module.nucleus_dum_ingress_service_lambda, module.nucleus_dum_cognito]
}

module "nucleus_dum_api" {
  source = "./modules/api_gateway"

  cloudwatch_iam_role_name             = var.cloudwatch_iam_role_name
  api_gateway_endpoint_type            = var.api_gateway_endpoint_type
  api_gateway_lambda_role_arn          = var.api_gateway_lambda_role_arn
  api_gateway_policy_source_vpc        = var.api_gateway_policy_source_vpc
  lambda_authorizer_function_arn       = module.nucleus_dum_lambda_authorizer.lambda_authorizer_function_arn
  lambda_authorizer_function_name      = module.nucleus_dum_lambda_authorizer.lambda_authorizer_function_name
  lambda_ingress_service_function_name = module.nucleus_dum_ingress_service_lambda.lambda_ingress_service_function_name
  lambda_ingress_service_function_arn  = module.nucleus_dum_ingress_service_lambda.lambda_ingress_service_function_arn
  status_queue_arn                     = module.nucleus_dum_status_queue.nucleus_dum_sqs_arn

  depends_on = [module.nucleus_dum_lambda_authorizer,
                module.nucleus_dum_ingress_service_lambda,
                module.nucleus_dum_status_queue]
}

resource "aws_cloudwatch_log_group" "ingress_client_cloudwatch_log_group" {
  name = var.nucleus_dum_client_cloudwatch_log_group

  retention_in_days = 30
}

resource "aws_lambda_permission" "nucleus_dum_api_lambda_authorizer_permission" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = module.nucleus_dum_lambda_authorizer.lambda_authorizer_function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${module.nucleus_dum_api.nucleus_dum_api_execution_arn}/*"

  depends_on = [module.nucleus_dum_lambda_authorizer, module.nucleus_dum_api]
}

resource "aws_lambda_permission" "nucleus_dum_api_lambda_ingress_service_permission" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = module.nucleus_dum_ingress_service_lambda.lambda_ingress_service_function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${module.nucleus_dum_api.nucleus_dum_api_execution_arn}/*"

  depends_on = [module.nucleus_dum_ingress_service_lambda, module.nucleus_dum_api]
}
