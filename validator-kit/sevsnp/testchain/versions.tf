terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}

provider "aws" {
  region = var.region

  # pof:kit is the SEV-SNP kit's own tag: the auto-stop may stop only instances that carry it (autostop.tf)
  default_tags {
    tags = { "pof:component" = "validator-sevsnp-testchain", "pof:kit" = "validator-kit/sevsnp", "pof:temporary" = "task-7.0" }
  }
}
