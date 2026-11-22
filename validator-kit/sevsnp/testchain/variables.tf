variable "region" {
  description = "The SEV-SNP kit's region: the test chain sits in its VPC."
  type        = string
  default     = "us-east-2"
}

variable "name" {
  description = "A prefix for this module's resources."
  type        = string
  default     = "pof-snp-testchain"
}

variable "kit_name" {
  description = "The SEV-SNP kit's `name` (validator-kit/sevsnp/terraform): its VPC, subnet, security group and instance are found by the Name tags it gives them."
  type        = string
  default     = "pof-snp"
}

variable "instance_type" {
  description = "The test-chain host: anvil, the Radicle seed and six validators with their Radicle nodes and test sandboxes (the owner's decision, 2026-11-21)."
  type        = string
  default     = "c6a.xlarge"
}

variable "create_instance" {
  description = "false (the default): only what costs nothing (the security group and its rules, the role, the bucket, the budget). true: the instance and its auto-stop. Its first boot installs Docker and stops nothing else; scripts/rc-aws.sh run starts and stops it."
  type        = bool
  default     = false
}

variable "ami_id" {
  description = "An AMI to pin (Amazon Linux 2023, x86_64). Empty: the current AL2023 AMI from AWS's public SSM parameter at the apply, kept afterwards (ignore_changes); AL2023 locks its package repositories to that AMI's release, so the Docker and git it installs are that release's."
  type        = string
  default     = ""
}

variable "disk_gb" {
  description = "The encrypted gp3 root volume: the images (Foundry, the test image, Radicle's), the chain's state and the run's logs."
  type        = number
  default     = 40
}

variable "rpc_port" {
  description = "The chain's JSON-RPC port, published on the host's private address for the SEV-SNP host only."
  type        = number
  default     = 8545
}

variable "seed_port" {
  description = "The Radicle seed's port, published on the host's private address for the SEV-SNP host only (its Radicle node dials it)."
  type        = number
  default     = 8776
}

variable "autostop_hours" {
  description = "The hard stop: any instance carrying the kit's tag (this host and the SEV-SNP host) that has run this long since its last start is stopped by the auto-stop Lambda (checked every 10 minutes); this host also schedules its own shutdown this long after each boot."
  type        = number
  default     = 8

  validation {
    condition     = var.autostop_hours >= 1 && var.autostop_hours <= 24
    error_message = "autostop_hours is 1 to 24."
  }
}

variable "bucket_expire_days" {
  description = "The run's bucket (the commit's bundle, the images, the logs) deletes its objects after this many days."
  type        = number
  default     = 7
}

variable "budget_limit_usd" {
  description = "This module's monthly budget (the account's cost, as the kit's): alerts at 50 % and 80 % actual and 100 % forecast; at 100 % actual both instances stop."
  type        = number
  default     = 10
}

variable "budget_emails" {
  description = "Who gets the budget's alerts (the owner). Without one there are no alerts and no automatic stop by the budget (the auto-stop Lambda still runs)."
  type        = list(string)
  default     = []
}
