variable "name" {
  description = "Name prefix for every resource (one validator per prefix and account)."
  type        = string
  default     = "pof-validator"
}

variable "enabled" {
  description = "The kill switch: false disables the watcher's schedule and tells it to do nothing; the node instance stays stopped."
  type        = bool
  default     = true
}

# ---------- The chain ----------

variable "rpc_url" {
  description = "The chain's JSON-RPC URL (HTTPS), e.g. the demo devnet's endpoint (#104)."
  type        = string

  validation {
    condition     = startswith(var.rpc_url, "https://")
    error_message = "The RPC URL must be HTTPS: the chain's API key travels in a header."
  }
}

variable "rpc_api_key_secret_arn" {
  description = "Secrets Manager secret (in this account) holding your per-engineer API key for the chain. Empty: no key sent."
  type        = string
  default     = ""
}

variable "repo_token_secret_arn" {
  description = "Secrets Manager secret (in this account) holding a read-only token for the repository (GitHub: contents, issues and pull requests: read; Forgejo: read:repository and read:issue, from a user with Read on it). The node reads the pull requests and the bounty's issue with it, and fetches each claimed commit and its base. Empty: the repository must be public."
  type        = string
  default     = ""
}

variable "rpc_api_key_header" {
  description = "How the chain's API key is sent: \"Basic\" (the secret is \"<handle>:<key>\", sent as HTTP Basic: the demo chain's), \"Authorization\" (Bearer), or another header's name (the raw key)."
  type        = string
  default     = "Basic"
}

variable "chain_id" {
  description = "The chain's ID, from the deployment record (the demo devnet is 7193). The node refuses any other chain."
  type        = number
}

variable "exchange_url" {
  description = "The drawn judges' exchange relay (HTTPS, no user info), ORACLE_EXCHANGE_URL: e.g. the devnet's https://<host>/exchange. On the RPC's own host (same scheme, host and port) the node sends it the RPC's key, with no other secret; on another host it sends no key. Empty: the node has no way to meet judges on other machines, so it can't complete a check with them."
  type        = string
  default     = ""

  validation {
    condition     = var.exchange_url == "" || can(regex("^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~-]+)*$", var.exchange_url))
    error_message = "exchange_url must be an HTTPS URL such as https://devnet.example.com/exchange (no trailing slash, no user info, no query): the key travels in a header."
  }
}

variable "race_address" {
  description = "The Race contract the validator serves (RaceV2's address in the deployment record)."
  type        = string

  validation {
    condition     = can(regex("^0x[0-9a-fA-F]{40}$", var.race_address))
    error_message = "race_address must be a 0x-prefixed 20-byte address."
  }
}

variable "validator_address" {
  description = "Your validator's public address (from the key you put in the validator key secret; see the runbook). The watcher starts the node only for the submissions Verdicts.drawn names this key for."
  type        = string
  default     = ""
}

variable "merge_poll_minutes" {
  description = "While a bounty this seat judged the winner of waits for its pull request to merge (the chain can't see the merge), the watcher starts the node this often."
  type        = number
  default     = 30
}

variable "pending_poll_minutes" {
  description = "While a submission this seat is drawn for waits for its result, the watcher starts the node again this often, in case a run ended without finishing it (#166). Keep this times pending_max_starts within the node's 5000-block scan."
  type        = number
  default     = 30
}

variable "pending_max_starts" {
  description = "How many times one draw may start the stopped node before the watcher gives up on it."
  type        = number
  default     = 4
}

variable "repository" {
  description = "owner/name of the demo's repository on the forge (GitHub by default; see forge): the node reads its pull requests to open the sealed submissions."
  type        = string
  default     = ""
}

variable "forge" {
  description = "Where the repository lives: \"github\" (the default: github.com, the token as GITHUB_TOKEN) or \"forgejo\" (a Forgejo at forge_url: the node gets a repos.json naming it, ORACLE_REPOS, and the token as FORGEJO_TOKEN with repo_token_user)."
  type        = string
  default     = "github"

  validation {
    condition     = contains(["github", "forgejo"], var.forge)
    error_message = "forge must be \"github\" or \"forgejo\"."
  }
}

variable "forge_url" {
  description = "With forge = \"forgejo\": the Forgejo's base URL (HTTPS, no path to the repository), e.g. https://git.example.com. The node reads its API under /api/v1 and fetches <forge_url>/<repository>.git."
  type        = string
  default     = ""

  validation {
    condition     = var.forge_url == "" || can(regex("^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~-]+)*$", var.forge_url))
    error_message = "forge_url must be an HTTPS base URL such as https://git.example.com (no trailing slash, no user info, no query): the repository token travels in a header."
  }
}

variable "repo_token_user" {
  description = "With forge = \"forgejo\" and repo_token_secret_arn: the Forgejo user the token belongs to (e.g. pof-validator-bot). The node sends it with the token when it fetches a commit over git (HTTP Basic: user and token), as FORGEJO_USER. Not a secret."
  type        = string
  default     = ""

  validation {
    condition     = can(regex("^[A-Za-z0-9._-]*$", var.repo_token_user))
    error_message = "repo_token_user may hold letters, digits and . _ - only (a Forgejo user name)."
  }
}

# ---------- The node ----------

variable "node_image" {
  description = "The official oracle node image, pinned by digest (registry/repo@sha256:...). Every operator runs the same digest. In a private ECR registry, the node logs in and its role may read that repository alone."
  type        = string

  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.node_image))
    error_message = "node_image must be pinned by digest: <registry>/<repository>@sha256:<64 hex>."
  }
}

variable "node_command" {
  description = "Arguments to the node's entry point for one on-demand run. It must exit when there is no work left (see the runbook's follow-ups)."
  type        = list(string)
  default     = ["run", "--until-idle", "600"]
}

variable "max_run_minutes" {
  description = "Hard limit on one run: the instance powers off after this even if the node hasn't exited."
  type        = number
  default     = 55
}

variable "instance_type" {
  description = "The node instance (Graviton). It runs only while checking. Nitro Enclaves (attestation, later) need a larger type such as c6g.xlarge."
  type        = string
  default     = "t4g.small"
}

variable "volume_gb" {
  description = "Root volume size: the node image, the test image and the fix's checkout."
  type        = number
  default     = 20
}

# ---------- The model ----------

variable "model_provider" {
  description = "How the node reaches its model, directly (no gateway, #118): \"bedrock\" calls Amazon Bedrock's Converse API in this account with the instance role; \"api\" calls a provider's API (model_api_provider) with a key from model_api_key_secret_arn. Any provider works (ADR 0003): Bedrock is just the AWS adapter."
  type        = string
  default     = "bedrock"

  validation {
    condition     = contains(["bedrock", "api"], var.model_provider)
    error_message = "model_provider must be \"bedrock\" or \"api\"."
  }
}

variable "model_id" {
  description = "The model the node's judge calls: with bedrock, a model ID or inference profile ID (or ARN) from bedrock_model_arns; with api, the provider's model name. Empty: the deterministic fake judge, for devnet runs only (no model call; not a counted judge)."
  type        = string
  default     = ""

  validation {
    condition     = can(regex("^[A-Za-z0-9._:/@+-]*$", var.model_id))
    error_message = "model_id may hold letters, digits and . _ : / @ + - only."
  }
}

variable "bedrock_model_arns" {
  description = "With bedrock: the only foundation-model or inference-profile ARNs the node may invoke (least privilege). The node gets the same list (their IDs and ARNs) as its allowlist, ORACLE_MODEL_ALLOW. An inference profile also needs the foundation-model ARNs it routes to."
  type        = list(string)
  default     = []
}

variable "model_api_provider" {
  description = "With api: \"anthropic\" (Messages API), \"openai\" (Chat Completions; with model_api_url any OpenAI-compatible server, such as a self-hosted vLLM) or \"gemini\" (generateContent)."
  type        = string
  default     = "anthropic"

  validation {
    condition     = contains(["anthropic", "openai", "gemini"], var.model_api_provider)
    error_message = "model_api_provider must be \"anthropic\", \"openai\" or \"gemini\"."
  }
}

variable "model_api_url" {
  description = "With api: the provider's base URL (HTTPS). Empty: the provider's public endpoint."
  type        = string
  default     = ""

  validation {
    condition     = var.model_api_url == "" || startswith(var.model_api_url, "https://")
    error_message = "model_api_url must be HTTPS: the proof that a prompt got an answer rests on TLS ending in the node."
  }
}

variable "model_api_key_secret_arn" {
  description = "With api: the Secrets Manager secret holding the provider's API key (sent only as the provider's header, never logged)."
  type        = string
  default     = ""
}

variable "max_output_tokens" {
  description = "Spending guard: the most tokens the model may answer with, per verdict (ORACLE_MAX_TOKENS)."
  type        = number
  default     = 4000
}

variable "max_model_calls" {
  description = "Spending guard: the most model calls in one run of the node, retries included (ORACLE_MAX_CALLS); then it refuses further calls."
  type        = number
  default     = 20
}

variable "max_run_tokens" {
  description = "Spending guard: the most tokens, in plus out, in one run of the node (ORACLE_MAX_RUN_TOKENS); a call whose worst case doesn't fit isn't made."
  type        = number
  default     = 500000
}

# ---------- Network, logs, money ----------

variable "vpc_cidr" {
  description = "CIDR of the validator's own small VPC (one public subnet, no inbound, no NAT gateway)."
  type        = string
  default     = "10.77.0.0/24"
}

variable "egress_ports" {
  description = "TCP ports the node may reach (HTTPS for the chain, the model and the image registry)."
  type        = list(number)
  default     = [443]
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the watcher and the node."
  type        = number
  default     = 14
}

variable "max_starts_per_day" {
  description = "The operator's fuse: the most times the watcher starts the node in a UTC day. With the limits per run, it bounds a day's spending. Past it, a draw whose round ends first is missed. 0: no limit."
  type        = number
  default     = 12

  validation {
    condition     = var.max_starts_per_day >= 0
    error_message = "max_starts_per_day can't be negative."
  }
}

variable "budget_stop" {
  description = "At 100 % of budget_limit_usd, an AWS Budgets action denies the node's model calls and the watcher's start, until you reverse it. Needs budget_limit_usd above 0 and at least one of budget_emails. AWS's cost data arrives hours late, so this is the backstop; max_starts_per_day is the fast fuse."
  type        = bool
  default     = true
}

variable "budget_limit_usd" {
  description = "Monthly AWS budget for this account; alerts at 80 % actual and 100 % forecast. 0: no budget."
  type        = number
  default     = 20
}

variable "budget_emails" {
  description = "Who gets the budget alerts."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Extra tags on every resource."
  type        = map(string)
  default     = {}
}
