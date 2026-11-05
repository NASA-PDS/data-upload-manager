terraform {
  required_version = ">= 1.2.0" # lifecycle preconditions
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.97.0"
    }

    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7.0"
    }

    random = {
      source = "hashicorp/random"
    }
  }
}
