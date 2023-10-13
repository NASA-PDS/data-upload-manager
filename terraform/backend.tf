terraform {
  backend "s3" {
    bucket = "pds-infra"
    key    = "dev/dum_infra.tfstate"
    region = "us-west-2"
  }
}
