
output "lambda_ingress_service_function_arn" {
   value = aws_lambda_function.lambda_ingress_service.arn
 }

output "lambda_ingress_service_function_name" {
  value = aws_lambda_function.lambda_ingress_service.function_name
}

output "lambda_status_service_function_arn" {
  value = aws_lambda_function.lambda_status_service.arn
}

output "lambda_status_service_function_name" {
  value = aws_lambda_function.lambda_status_service.function_name
}
