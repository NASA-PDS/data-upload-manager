# Terraform module for the Data Upload Manager (DUM) API Gateway

data "aws_iam_role" "cloudwatch_iam_role" {
  name = var.cloudwatch_iam_role_name
}

resource "aws_api_gateway_rest_api" "nucleus_dum_api" {
  name        = var.rest_api_name
  description = var.rest_api_description

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  body = templatefile(
    "${path.module}/templates/data-upload-manager-oas30-apigateway.yaml.tftpl",
    {
      apiGatewayLambdaRole                = var.api_gateway_lambda_role_arn,
      apiGatewaySourceVpc                 = var.api_gateway_policy_source_vpc,
      awsRegion                           = var.region,
      createStreamResourceMappingTemplate = jsonencode(file("${path.module}/templates/createstream-resource-mapping-template.json"))
      lambdaAuthorizerARN                 = var.lambda_authorizer_function_arn,
      lambdaAuthorizerFunctionName        = var.lambda_authorizer_function_name,
      lambdaServiceARN                    = var.lambda_ingress_service_function_arn,
      logResourceMappingTemplate          = jsonencode(file("${path.module}/templates/log-resource-mapping-template.json"))
    }
  )
}

resource "aws_lambda_permission" "nucleus_dum_api_lambda_authorizer_permission" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_authorizer_function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${aws_api_gateway_rest_api.nucleus_dum_api.execution_arn}/*"
}

resource "aws_lambda_permission" "nucleus_dum_api_lambda_ingress_service_permission" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_ingress_service_function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${aws_api_gateway_rest_api.nucleus_dum_api.execution_arn}/*"
}

resource "aws_api_gateway_deployment" "nucleus_dum_api_deployments" {
  count = length(var.api_deployment_stages)

  rest_api_id = aws_api_gateway_rest_api.nucleus_dum_api.id
  stage_name  = var.api_deployment_stages[count.index]

  triggers = {
    redeployment = sha1(yamlencode(aws_api_gateway_rest_api.nucleus_dum_api.body))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_account" "cloudwatch_role_arn_setting" {
  cloudwatch_role_arn = data.aws_iam_role.cloudwatch_iam_role.arn
}

resource "aws_api_gateway_method_settings" "nucleus_dum_api_deployment_settings" {
  count = length(var.api_deployment_stages)

  rest_api_id = aws_api_gateway_rest_api.nucleus_dum_api.id
  stage_name  = aws_api_gateway_deployment.nucleus_dum_api_deployments[count.index].stage_name
  method_path = "*/*"  # Apply settings to all methods in deployment

  settings {
    # These settings map to the "Errors and Info Logs" setting for API Gateway
    # Cloudwatch logging
    logging_level      = "INFO"
    metrics_enabled    = true
    data_trace_enabled = false
  }
}
