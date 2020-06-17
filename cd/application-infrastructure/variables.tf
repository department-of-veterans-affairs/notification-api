variable "environment_prefix" {
  default = "dev"
}

variable "app_tag" {
  type = string
}

variable "database_name" {
  type    = string
  default = "notification_api"
}

data "aws_subnet" "public_az_a" {
  cidr_block = "10.0.0.128/26"
}

data "aws_subnet" "public_az_b" {
  cidr_block = "10.0.0.192/26"
}

data "aws_subnet" "private_az_a" {
  cidr_block = "10.0.0.64/26"
}

data "aws_subnet" "private_az_b" {
  cidr_block = "10.0.0.0/26"
}

data "terraform_remote_state" "application_db" {
  backend = "s3"

  config = {
    bucket = "terraform-notification-test"
    key    = "notification-api-dev-db.tfstate"
    region = "us-east-2"
  }
}

data "terraform_remote_state" "base_infrastructure" {
  backend = "s3"

  config = {
    bucket = "terraform-notification-test"
    key    = "notification-test.tfstate"
    region = "us-east-2"
  }
}

locals {
  default_tags = {
    Stack       = "application-infrastructure",
    Environment = var.environment_prefix,
    Team        = "va-notify"
    ManagedBy   = "Terraform"
  }
}

variable "workspace_iam_roles" {
  default = {
    default = "arn:aws:iam::437518843863:role/notification-deploy-role"
  }
}

variable "region" {
  default = "us-east-2"
}