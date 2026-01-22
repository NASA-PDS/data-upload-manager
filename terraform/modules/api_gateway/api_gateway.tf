# Terraform module for the Data Upload Manager (DUM) API Gateway

# Needed to construct the correct API Gateway -> SQS integration URI
# (arn:aws:apigateway:${region}:sqs:path/${accountId}/${queueName})
data "aws_caller_identity" "current" {}

# CloudWatch IAM role data source removed as we're not configuring API Gateway account

resource "aws_api_gateway_rest_api" "nucleus_dum_api" {
  name        = var.rest_api_name
  description = var.rest_api_description

  endpoint_configuration {
    types = [var.api_gateway_endpoint_type]
  }

  # Add minimal resource policy for private API Gateway - required for deployment
  policy = var.api_gateway_endpoint_type == "PRIVATE" ? jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = "*",
        Action = "execute-api:Invoke",
        Resource = "arn:aws:execute-api:${var.region}:${data.aws_caller_identity.current.account_id}:*/*",
        Condition = {
          StringEquals = {
            "aws:SourceVpc" = var.api_gateway_policy_source_vpc
          }
        }
      }
    ]
  }) : null

  lifecycle {
    # Prevent errors when updating the API definition
    create_before_destroy = true
  }

  body = templatefile(
    "${path.module}/templates/data-upload-manager-oas30-apigateway.yaml.tftpl",
    {
      apiGatewayLambdaRole                = var.api_gateway_lambda_role_arn,
      apiGatewaySourceVpc                 = var.api_gateway_policy_source_vpc,
      awsRegion                           = var.region,
      awsAccountId                        = data.aws_caller_identity.current.account_id,
      createStreamResourceMappingTemplate = jsonencode(file("${path.module}/templates/createstream-resource-mapping-template.json"))
      lambdaAuthorizerARN                 = var.lambda_authorizer_function_arn,
      lambdaAuthorizerFunctionName        = var.lambda_authorizer_function_name,
      lambdaServiceARN                    = var.lambda_ingress_service_function_arn,
      logResourceMappingTemplate          = jsonencode(file("${path.module}/templates/log-resource-mapping-template.json"))
      statusResourceMappingTemplate       = jsonencode(file("${path.module}/templates/status-resource-mapping-template.json"))

      # Keep existing input for backward-compatibility (template can still reference it if needed)
      statusQueueARN = var.status_queue_arn
    }
  )
}

resource "aws_api_gateway_deployment" "nucleus_dum_api_deployments" {
  count = length(var.api_deployment_stages)

  rest_api_id  = aws_api_gateway_rest_api.nucleus_dum_api.id
  description  = "Deployment for ${var.api_deployment_stages[count.index]} stage"

  triggers = {
    redeployment = sha1(yamlencode(aws_api_gateway_rest_api.nucleus_dum_api.body))
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Create API Gateway stage explicitly
resource "aws_api_gateway_stage" "stages" {
  count = length(var.api_deployment_stages)

  rest_api_id          = aws_api_gateway_rest_api.nucleus_dum_api.id
  stage_name           = var.api_deployment_stages[count.index]
  deployment_id        = aws_api_gateway_deployment.nucleus_dum_api_deployments[count.index].id
  xray_tracing_enabled = true

  lifecycle {
    create_before_destroy = true
  }
}

# Skip API Gateway account configuration as it's a global resource
# and only needs to be set up once per AWS account
# If you need to set up CloudWatch logging, configure this manually in the AWS console
# or use a separate Terraform configuration for global resources

resource "aws_api_gateway_method_settings" "nucleus_dum_api_deployment_settings" {
  count = length(var.api_deployment_stages)

  rest_api_id = aws_api_gateway_rest_api.nucleus_dum_api.id
  stage_name  = aws_api_gateway_stage.stages[count.index].stage_name

  # Depend on the stage resource to ensure it exists first
  depends_on  = [aws_api_gateway_stage.stages]
  method_path = "*/*" # Apply settings to all methods in deployment

  settings {
    # Disable CloudWatch logging since we're not configuring API Gateway account
    logging_level      = "OFF"
    metrics_enabled    = false
    data_trace_enabled = false
  }
}
