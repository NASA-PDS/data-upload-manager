terraform {
  required_version = ">= 1.0.11"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.58.0"
    }

    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4.0"
    }

    random = {
      source = "hashicorp/random"
    }
  }
}
