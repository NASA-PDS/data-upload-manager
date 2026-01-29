
output "nucleus_dum_api_execution_arn" {
  value = aws_api_gateway_rest_api.nucleus_dum_api.execution_arn
}

output "nucleus_dum_api_id" {
  value = aws_api_gateway_rest_api.nucleus_dum_api.id
}

output "nucleus_dum_api_stages" {
  value = [var.api_deployment_stages]
}
