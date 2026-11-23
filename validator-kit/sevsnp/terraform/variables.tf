variable "region" {
  description = "AWS Region. SEV-SNP on shared tenancy is offered only in US East (Ohio) and Europe (Ireland) (https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/sev-snp.html); elsewhere only on Dedicated Hosts."
  type        = string
  default     = "us-east-2"

  validation {
    condition     = contains(["us-east-2", "eu-west-1"], var.region)
    error_message = "SEV-SNP on shared tenancy runs only in us-east-2 or eu-west-1."
  }
}

variable "name" {
  description = "Name prefix for every resource. Distinct from v2's kit (pof-validator), which can live in the same account."
  type        = string
  default     = "pof-snp"
}

variable "instance_type" {
  description = "An AMD instance type with SEV-SNP: m6a.large-8xlarge, c6a.large-16xlarge, r6a.large-4xlarge (the doc above). c6a.large: 2 vCPUs, 4 GiB, $0.0765 an hour on demand in us-east-2, plus SEV-SNP's 10 %."
  type        = string
  default     = "c6a.large"

  validation {
    condition     = can(regex("^(m6a\\.(large|[248]?xlarge)|c6a\\.(large|[2-9]?xlarge|1[26]xlarge)|r6a\\.(large|[24]?xlarge))$", var.instance_type))
    error_message = "instance_type must be an m6a, c6a or r6a size that supports SEV-SNP."
  }
}

variable "snapshot_id" {
  description = "The measured disk's EBS snapshot (scripts/checker-disk.sh's disk.raw, uploaded with coldsnap: the plan). Empty: no AMI and no instance yet."
  type        = string
  default     = ""
}

variable "manifest_path" {
  description = "The disk's manifest.json from the same build (scripts/checker-disk.sh --out): its root hash and image digest are tagged on the AMI and printed, so the AMI names what it boots."
  type        = string
  default     = ""
}

variable "create_instance" {
  description = "false (the default): everything but the instance. true: launch it. Its first boot attests itself (the console shows the SEV-SNP report and the NitroTPM document), runs the node if node_config is set, and powers off: stopped, as v2's node, until someone starts it."
  type        = bool
  default     = false
}

variable "data_volume_gb" {
  description = "The data volume (gp3): the node's persistent state and the scratch wiped at each boot (Docker's store, the fixes' checkouts)."
  type        = number
  default     = 20
}

variable "attest_nonce" {
  description = "The verifier's nonce (hex), bound into the SEV-SNP report's data and the NitroTPM document's nonce. Empty: the boot's ID."
  type        = string
  default     = ""

  validation {
    condition     = can(regex("^([0-9a-f]{2}){0,64}$", var.attest_nonce))
    error_message = "attest_nonce is lowercase hex, at most 64 bytes."
  }
}

variable "power_off" {
  description = "Power off after the run (the default, as v2's node). false keeps the instance up for a first test: stop it yourself."
  type        = bool
  default     = true
}

variable "node_command" {
  description = "The node's command on each boot (POF_NODE_COMMAND): run, info, register ..., leave, post-table."
  type        = string
  default     = "run --until-idle 600"
}

variable "node_config" {
  description = "The node's ORACLE_* settings, as data in the user data (never run): e.g. ORACLE_VERSION, ORACLE_RPC, ORACLE_RACE, ORACLE_REPO, ORACLE_FAMILY, ORACLE_JUDGE, ORACLE_MODEL_ALLOW, ORACLE_IMAGE, ORACLE_SPEND_*, ORACLE_FROM_BLOCK (the deployment record's block: no event scan starts before it) and ORACLE_LOG_RANGE (the most blocks one eth_getLogs asks for, default 5000; lower for a strict provider). Secrets only by ARN (ORACLE_PRIVATE_KEY_SECRET_ARN, RPC_API_KEY_SECRET_ARN, MODEL_API_KEY_SECRET_ARN); the signing key's is set from this module's secret. Empty: the boot only attests."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([for k, v in var.node_config : can(regex("^(ORACLE_[A-Z0-9_]+|AWS_REGION|RPC_API_KEY_SECRET_ARN|MODEL_API_KEY_SECRET_ARN)$", k)) && !contains(
    ["ORACLE_ATTESTED_IMAGES", "ORACLE_SANDBOX", "ORACLE_KEYS", "ORACLE_SNP_DEVICE", "ORACLE_SRC_ROOT", "ORACLE_ROUNDS", "ORACLE_RECEIPTS", "ORACLE_SPEND_LEDGER", "ORACLE_PRIVATE_KEY", "ORACLE_RADICLE_EXEC", "ORACLE_RADICLE_REPO"], k) && can(regex("^[[:print:]]*$", v))])
    error_message = "node_config takes ORACLE_* settings (not the ones the measured disk fixes, and no secret's value: secrets go by ARN)."
  }
}

variable "radicle_seed" {
  description = "The Radicle seed this host's node dials (POF_RADICLE_SEED): \"<its Node ID>@<host>:8776\", the project's seed (seed/README.md, `rad self --nid` there, and its address). The node is outbound only: it listens on no port, and this kit opens none. Needed with node_config's ORACLE_RADICLE_RID (model (a): ORACLE_FIX_SOURCE and ORACLE_MERGE_VIA = \"radicle\")."
  type        = string
  default     = ""

  validation {
    condition     = var.radicle_seed == "" || can(regex("^z6Mk[1-9A-HJ-NP-Za-km-z]{40,50}@[A-Za-z0-9.-]{1,253}:[0-9]{1,5}$", var.radicle_seed))
    error_message = "radicle_seed is <Node ID>@<host>:<port>, e.g. z6Mk…@seed.example.org:8776."
  }
}

variable "bedrock_model_arns" {
  description = "Bedrock model or inference-profile ARNs the node may call (least privilege, as v2's kit). Empty: none."
  type        = list(string)
  default     = []
}

variable "extra_secret_arns" {
  description = "Other Secrets Manager secrets the node reads by ARN (the chain's API key, a model API key)."
  type        = list(string)
  default     = []
}

variable "vpc_cidr" {
  description = "The kit's VPC: one public subnet, no inbound, no NAT."
  type        = string
  default     = "10.82.0.0/24"
}

variable "egress_ports" {
  description = "TCP ports the node may reach: HTTPS (the chain, the model, Secrets Manager) and 8776, Radicle's peer port (this host's Radicle node dials the seed; nothing dials in). HTTP for IMDS is link-local and needs no rule."
  type        = list(number)
  default     = [443, 8776]
}

variable "budget_limit_usd" {
  description = "This kit's monthly AWS budget (USD), across the account: 80 % actual and 100 % forecast alert budget_emails; at 100 % actual, AWS Budgets stops the instance (budget_stop). The model's spend is capped by the node itself (ORACLE_SPEND_*)."
  type        = number
  default     = 15
}

variable "budget_emails" {
  description = "Who gets the budget's alerts. Empty: the budget exists with no alert and no stop."
  type        = list(string)
  default     = []
}

variable "budget_stop" {
  description = "At 100 % of budget_limit_usd (actual), AWS Budgets stops the instance (an SSM STOP_EC2_INSTANCES action, applied automatically)."
  type        = bool
  default     = true
}

# ---------- The v3 watcher (watcher.tf) ----------

variable "watcher_enabled" {
  description = "The watcher's kill switch and schedule: false (the default) creates it disabled (with the instance), so nothing starts the instance; true runs it every minute."
  type        = bool
  default     = false
}

variable "validator_address" {
  description = "The validator's signing key's address (0x…): the watcher starts the instance only for this key's seats on Panels. Required with watcher_enabled."
  type        = string
  default     = ""
}

variable "race_address" {
  description = "RaceV3's address (the watcher reads Panels from its contracts()). Empty: node_config's ORACLE_RACE."
  type        = string
  default     = ""
}

variable "watcher_rpc_url" {
  description = "The chain's JSON-RPC URL for the watcher, when it holds no key. Empty: node_config's ORACLE_RPC. For an RPC whose key is in its URL, use rpc_url_secret_arn instead."
  type        = string
  default     = ""
}

variable "rpc_url_secret_arn" {
  description = "A Secrets Manager secret holding the chain's whole RPC URL (a keyed endpoint), read by the watcher once per run and never logged. Takes the place of watcher_rpc_url."
  type        = string
  default     = ""
}

variable "rpc_api_key_secret_arn" {
  description = "A Secrets Manager secret holding a chain API key sent in a header (v2's form; rpc_api_key_header says how). Empty: node_config's RPC_API_KEY_SECRET_ARN, if any."
  type        = string
  default     = ""
}

variable "rpc_api_key_header" {
  description = "How the watcher sends rpc_api_key_secret_arn's key: \"Basic\" (a \"<handle>:<key>\" secret, the demo chain's), \"Authorization\" (Bearer) or another header's name."
  type        = string
  default     = "Basic"
}

variable "max_starts_per_day" {
  description = "The watcher's fuse: the most times it starts the instance in a UTC day (0: no limit). Each start runs the node at least its idle time (10 minutes) and a drawn seat holds it up through the seal and reveal windows (up to about 3 hours with production windows)."
  type        = number
  default     = 12
}

variable "watcher_retry_minutes" {
  description = "How often a seat still due starts the stopped instance again (the node crashed or stopped at its chain-outage limit)."
  type        = number
  default     = 10
}

variable "seat_max_starts" {
  description = "The most times one seat (per phase: seal, reveal) starts the instance before the watcher gives up on it."
  type        = number
  default     = 3
}

variable "reveal_lead_seconds" {
  description = "How long before a sealed seat's reveal window opens the watcher starts a stopped instance (a cold start to a ready node takes about a minute: SEVSNP-PLAN.md)."
  type        = number
  default     = 180
}

variable "ready_seconds" {
  description = "A cold start's time to a node that can seal (about 60 s measured on 2026-11-20, plus margin): a seal start with less time left is logged as late."
  type        = number
  default     = 120
}

variable "unpause_check" {
  description = "\"daily\": while the node's on-chain capacity is 0 (its spending pause) the watcher starts it once a UTC day, so the node can restore its capacity at a new period; \"off\": the operator does."
  type        = string
  default     = "daily"

  validation {
    condition     = contains(["daily", "off"], var.unpause_check)
    error_message = "unpause_check is daily or off."
  }
}

variable "watcher_lookback_blocks" {
  description = "The watcher's first run looks back this many blocks for seats (1200: 4 hours of Sepolia's 12-second blocks, past a production seal and reveal window)."
  type        = number
  default     = 1200
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the watcher."
  type        = number
  default     = 30
}
