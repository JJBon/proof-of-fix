variable "region" {
  description = "AWS Region. The owner's choice (2026-11-20) is us-east-2, beside the SEV-SNP kit; any Region with t4g works."
  type        = string
  default     = "us-east-2"
}

variable "name" {
  description = "Name prefix for every resource. Distinct from the validator kits' (pof-validator, pof-snp), which can live in the same account."
  type        = string
  default     = "pof-seed"
}

variable "create_instance" {
  description = "false (the default): only what costs nothing (VPC, security group, role, budget). true: the instance, its data volume and its Elastic IP; it installs Radicle and starts the seed on its first boot. Only after the Radicle publish (task 6.2) and the owner's word to start it (task 6.3)."
  type        = bool
  default     = false
}

variable "publication_record" {
  description = "Path to the publication record written at the Radicle publish (task 6.2; format pof-radicle-publication/1, seed/publication.py). The seed's one seeding policy is its rid. Required with create_instance = true."
  type        = string
  default     = ""
}

variable "instance_type" {
  description = "A Graviton (arm64) instance type. t4g.micro: 2 vCPUs (burstable), 1 GiB, $0.0084 an hour on demand in us-east-2. radicle-node peaked at 45 MiB in the seed's test (seed/README.md); t4g.nano (0.5 GiB, half the price) leaves little room beside Amazon Linux, its agent and git serving clones."
  type        = string
  default     = "t4g.micro"

  validation {
    condition     = can(regex("^[a-z]+[0-9]+g[a-z]*\\.[a-z0-9]+$", var.instance_type))
    error_message = "instance_type must be a Graviton (arm64) type such as t4g.micro: the pinned release is the aarch64 build."
  }
}

variable "root_volume_gb" {
  description = "The root volume (gp3, encrypted): Amazon Linux 2023 and the Radicle binaries. Its AMI's snapshot is 8 GiB."
  type        = number
  default     = 8
}

variable "data_volume_gb" {
  description = "The data volume (gp3, encrypted) at /var/lib/radicle: the node's key and storage. proof-of-fix's snapshot packs to about 5 MB; gp3 can be grown in place."
  type        = number
  default     = 2
}

variable "alias" {
  description = "The node's alias on the Radicle network."
  type        = string
  default     = "proof-of-fix-seed"

  validation {
    condition     = can(regex("^[A-Za-z0-9._-]{1,32}$", var.alias))
    error_message = "alias: 1-32 letters, digits, dots, dashes or underscores."
  }
}

variable "external_address" {
  description = "The address other nodes dial (the node's externalAddresses), host:port. Empty: the Elastic IP and 8776. A DNS name you control (pointing at the Elastic IP) also works."
  type        = string
  default     = ""

  validation {
    condition     = var.external_address == "" || can(regex("^[A-Za-z0-9.-]{1,253}:[0-9]{1,5}$", var.external_address))
    error_message = "external_address must be host:port."
  }
}

variable "ssm_access" {
  description = "A shell through Session Manager (no SSH, no inbound port). false: no access to the host at all; the seed is checked from outside (seed/README.md)."
  type        = bool
  default     = true
}

variable "vpc_cidr" {
  description = "The seed's VPC: one public subnet, inbound TCP 8776 only, no NAT."
  type        = string
  default     = "10.83.0.0/24"
}

variable "egress_ports" {
  description = "TCP ports the seed may reach: 8776 (the Radicle peers it dials) and 443 (the pinned release, Amazon Linux's packages, Session Manager). DNS to the VPC resolver is always allowed."
  type        = list(number)
  default     = [443, 8776]
}

variable "budget_limit_usd" {
  description = "The monthly AWS budget (USD), across the account like the SEV-SNP kit's: 80 % actual and 100 % forecast alert budget_emails. No automatic stop (budget.tf says why). The seed alone is about $10.60 a month (seed/README.md)."
  type        = number
  default     = 15
}

variable "budget_emails" {
  description = "Who gets the budget's alerts. Empty: the budget exists with no alert."
  type        = list(string)
  default     = []
}

variable "keeper_secret_arns" {
  description = "The keeper's secrets on this host (owner's approval 2026-11-23): its account's key and its own RPC URL (pof-seed/keeper-rpc-url, a key of its own, not the validator's), as Secrets Manager ARNs (with their random suffix). The role may read exactly these (GetSecretValue). Empty: no keeper policy."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for a in var.keeper_secret_arns : can(regex("^arn:aws:secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:[A-Za-z0-9/_+=.@-]+$", a))])
    error_message = "keeper_secret_arns: Secrets Manager secret ARNs only."
  }
}
