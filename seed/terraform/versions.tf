terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
  }
}

# The account and its credentials come from the environment (AWS_PROFILE or the usual chain), never from these files:
# this folder is published as it is.
provider "aws" {
  region = var.region

  default_tags {
    tags = { "pof:component" = "radicle-seed", "pof:kit" = "seed" }
  }
}
