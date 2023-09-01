# Main Terraform module for automated deployment of the PDS Data Upload Manager (DUM)
provider "aws" {
  region  = var.region
  profile = var.profile
  shared_credentials_files = [var.credential_file]
}

module "nucleus_dum_ingress_service_lambda" {
  source = "./modules/lambda/service"

  lambda_s3_bucket_name               = var.lambda_s3_bucket_name
  lambda_ingress_service_iam_role_arn = var.lambda_ingress_service_iam_role_arn
}

module "nucleus_dum_cognito" {
  source = "./modules/cognito"

  nucleus_dum_cognito_initial_users = var.nucleus_dum_cognito_initial_users
}
