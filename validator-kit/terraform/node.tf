# The node instance: stopped while idle, started by the watcher, powered off by itself when the run ends.

locals {
  # The judge (#118): the node calls its model directly, no gateway. No model_id: the fake judge (devnet only).
  direct_provider = var.model_provider == "bedrock" ? "bedrock" : var.model_api_provider
  oracle_judge    = var.model_id == "" ? "fake" : "direct:${local.direct_provider}:${var.model_id}"
  # The node's allowlist mirrors the IAM policy: each listed ARN, and its model or inference profile ID.
  bedrock_model_ids = [for arn in var.bedrock_model_arns : regex("[^/]+$", arn)]
  model_allow       = var.model_provider == "bedrock" ? join(",", distinct(concat(local.bedrock_model_ids, var.bedrock_model_arns))) : var.model_id
  # Bedrock: the node's container reads the instance role's credentials from IMDSv2 itself, one hop further than the
  # host (Docker's bridge), so the hop limit is 2. Only the node's container has a network; the sandbox's containers
  # have none, so the fix's code can't reach the metadata service either way.
  imds_hop_limit = var.model_provider == "bedrock" && var.model_id != "" ? 2 : 1
  # A node image in a private ECR registry (<account>.dkr.ecr.<region>.amazonaws.com/<repository>@sha256:...): the run
  # logs in before pulling, and the role may read that one repository. Any other registry: no login, no permission.
  ecr_image      = regexall("^(([0-9]{12})\\.dkr\\.ecr\\.([a-z0-9-]+)\\.amazonaws\\.com)/([^@]+)@", var.node_image)
  ecr_registry   = length(local.ecr_image) > 0 ? local.ecr_image[0][0] : ""
  ecr_region     = length(local.ecr_image) > 0 ? local.ecr_image[0][2] : ""
  ecr_repository = length(local.ecr_image) > 0 ? "arn:aws:ecr:${local.ecr_image[0][2]}:${local.ecr_image[0][1]}:repository/${local.ecr_image[0][3]}" : ""
  # A Forgejo target: bot/forge.py's repos.json naming the repository's host and base URL (no credentials).
  forge_repos_json = jsonencode({ repos = { (var.repository) = { host = "forgejo", api = var.forge_url } } })
}

data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

data "aws_iam_policy_document" "node_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "${var.name}-node"
  assume_role_policy = data.aws_iam_policy_document.node_assume.json
  tags               = local.tags
}

# Shell through Session Manager (no SSH, no inbound port).
resource "aws_iam_role_policy_attachment" "node_ssm" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "node" {
  statement {
    sid       = "ReadOwnSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = local.secret_arns
  }

  statement {
    sid       = "NodeLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.node.arn}:*"]
  }

  dynamic "statement" {
    for_each = local.ecr_registry != "" ? [1] : []
    content {
      sid       = "EcrLogin"
      actions   = ["ecr:GetAuthorizationToken"] # has no resource-level permission
      resources = ["*"]
    }
  }

  dynamic "statement" {
    for_each = local.ecr_registry != "" ? [1] : []
    content {
      sid       = "PullNodeImageOnly"
      actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
      resources = [local.ecr_repository]
    }
  }

  dynamic "statement" {
    for_each = var.model_provider == "bedrock" && length(var.bedrock_model_arns) > 0 ? [1] : []
    content {
      sid = "InvokeChosenModelsOnly"
      # The node calls Converse (#118), which IAM authorizes as bedrock:InvokeModel; nothing else, these ARNs only.
      actions   = ["bedrock:InvokeModel", "bedrock:Converse"]
      resources = var.bedrock_model_arns
    }
  }
}

resource "aws_iam_role_policy" "node" {
  name   = "node"
  role   = aws_iam_role.node.id
  policy = data.aws_iam_policy_document.node.json
}

resource "aws_iam_instance_profile" "node" {
  name = "${var.name}-node"
  role = aws_iam_role.node.name
  tags = local.tags
}

resource "aws_instance" "node" {
  ami                                  = data.aws_ssm_parameter.al2023_arm64.value
  instance_type                        = var.instance_type
  subnet_id                            = aws_subnet.public.id
  vpc_security_group_ids               = [aws_security_group.node.id]
  iam_instance_profile                 = aws_iam_instance_profile.node.name
  instance_initiated_shutdown_behavior = "stop" # the node's power-off stops it, so the watcher can start it again

  metadata_options {
    http_tokens                 = "required"           # IMDSv2 only
    http_put_response_hop_limit = local.imds_hop_limit # 1: no container reaches it; 2 with Bedrock: the node's does
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.volume_gb
    encrypted   = true
  }

  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/node-user-data.sh.tftpl", {
    region                 = data.aws_region.current.region
    node_image             = var.node_image
    ecr_registry           = local.ecr_registry
    ecr_region             = local.ecr_region
    node_command           = join(" ", [for a in var.node_command : format("%q", a)])
    max_run_minutes        = var.max_run_minutes
    log_group              = aws_cloudwatch_log_group.node.name
    rpc_url                = var.rpc_url
    rpc_api_key_secret_arn = var.rpc_api_key_secret_arn
    rpc_api_key_header     = var.rpc_api_key_header
    exchange_url           = var.exchange_url
    repo_token_secret_arn  = var.repo_token_secret_arn
    race_address           = var.race_address
    chain_id               = var.chain_id
    repository             = var.repository
    forge                  = var.forge
    forge_repos_json       = var.forge == "forgejo" ? local.forge_repos_json : ""
    repo_token_user        = var.forge == "forgejo" ? var.repo_token_user : ""
    validator_key_secret   = aws_secretsmanager_secret.validator_key.arn
    oracle_judge           = local.oracle_judge
    model_allow            = local.model_allow
    model_api_url          = var.model_provider == "api" ? var.model_api_url : ""
    model_api_secret_arn   = var.model_provider == "api" ? var.model_api_key_secret_arn : ""
    max_output_tokens      = var.max_output_tokens
    max_model_calls        = var.max_model_calls
    max_run_tokens         = var.max_run_tokens
  })

  tags = merge(local.tags, { Name = "${var.name}-node" })

  lifecycle {
    ignore_changes = [ami] # a new Amazon Linux AMI shouldn't replace a stopped node; bump deliberately

    precondition {
      condition     = var.model_provider != "bedrock" || var.model_id == "" || contains(split(",", local.model_allow), var.model_id)
      error_message = "model_id must be one of bedrock_model_arns (its ARN, or the model or inference profile ID at its end): the IAM policy allows only those."
    }
    precondition {
      condition     = var.model_provider != "api" || var.model_id == "" || var.model_api_key_secret_arn != "" || (var.model_api_provider == "openai" && var.model_api_url != "")
      error_message = "With model_provider = \"api\", set model_api_key_secret_arn (only an OpenAI-compatible server at model_api_url may need no key)."
    }
    precondition {
      condition     = var.forge != "forgejo" || (var.forge_url != "" && var.repository != "")
      error_message = "With forge = \"forgejo\", set forge_url (the Forgejo's HTTPS base URL) and repository (owner/name on it)."
    }
    precondition {
      condition     = var.forge != "forgejo" || var.repo_token_secret_arn == "" || var.repo_token_user != ""
      error_message = "With forge = \"forgejo\" and repo_token_secret_arn, set repo_token_user: the Forgejo user the token belongs to (git sends it with the token)."
    }
  }
}

# No aws_ec2_instance_state here: the first boot powers itself off when the install is done, and forcing a stop from
# apply cut the install short, leaving a node with no service (#150). Only the watcher starts it after that.
