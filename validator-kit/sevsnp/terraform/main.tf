# One proof-of-fix validator host on AMD SEV-SNP (#253; #251 L18 item 3, L21): the measured checker disk as a UEFI AMI
# with NitroTPM, an m6a/c6a/r6a instance launched with SEV-SNP, a data volume, the node's signing key in your Secrets
# Manager, and a budget that stops the instance. validator-kit/SEVSNP-PLAN.md is the order of the steps.
#
# What the instance runs is fixed by the disk, not by this module: the disk reads the user data below as KEY=VALUE data
# (there is no cloud-init), attests each boot on the serial console, runs the node in attested mode, and powers off.
# No SSH, no SSM agent, no inbound port: the console output is the operator's view (`aws ec2 get-console-output`). The
# host's Radicle node is outbound only too: it dials the seed (radicle_seed) on 8776, and the seed relays both ways.

locals {
  manifest     = var.manifest_path != "" ? jsondecode(file(var.manifest_path)) : null
  roothash     = local.manifest != null ? local.manifest.roothash : ""
  image_digest = local.manifest != null ? local.manifest.image_digest : ""

  # The user data: data the disk's pof-config.sh filters (it refuses the settings the disk fixes, and secrets' values).
  node_lines = length(var.node_config) == 0 ? [] : concat(
    [for k in sort(keys(var.node_config)) : "${k}=${var.node_config[k]}"],
    ["ORACLE_PRIVATE_KEY_SECRET_ARN=${aws_secretsmanager_secret.validator_key.arn}", "AWS_REGION=${var.region}"],
  )
  host_lines = concat(
    var.attest_nonce != "" ? ["POF_ATTEST_NONCE=${var.attest_nonce}"] : [],
    ["POF_POWER_OFF=${var.power_off ? "yes" : "no"}", "POF_NODE_COMMAND=${var.node_command}"],
    var.radicle_seed != "" ? ["POF_RADICLE_SEED=${var.radicle_seed}"] : [],
  )
  user_data = join("\n", concat(["# proof-of-fix SEV-SNP validator: data, read by the measured disk's pof-config.sh"],
  local.host_lines, local.node_lines, [""]))
}

data "aws_caller_identity" "current" {}

# ---------- The validator's signing key ----------

# Created empty: you generate the key and put it here (the plan), so it never passes through Terraform or its state.
# The node reads it at start-up (oracle/awssecret.py), in memory only.
resource "aws_secretsmanager_secret" "validator_key" {
  name                    = "${var.name}/signing-key"
  description             = "proof-of-fix SEV-SNP validator signing key (hex secp256k1); written by the operator, never by Terraform"
  recovery_window_in_days = 7
}

# ---------- The measured disk as an AMI ----------

resource "aws_ami" "checker" {
  count               = var.snapshot_id != "" ? 1 : 0
  name                = "${var.name}-checker-${substr(local.roothash != "" ? local.roothash : var.snapshot_id, 0, 16)}"
  description         = "proof-of-fix measured checker disk (roothash ${local.roothash != "" ? local.roothash : "unknown"})"
  architecture        = "x86_64"
  boot_mode           = "uefi" # SEV-SNP needs UEFI; the UKI is the ESP's \EFI\BOOT\BOOTX64.EFI
  tpm_support         = "v2.0" # NitroTPM: measured boot of the UKI into PCR4, its attestation document
  imds_support        = "v2.0" # IMDSv2 only
  ena_support         = true
  virtualization_type = "hvm"
  root_device_name    = "/dev/xvda"

  ebs_block_device {
    device_name           = "/dev/xvda"
    snapshot_id           = var.snapshot_id
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = { Name = "${var.name}-checker", "pof:roothash" = local.roothash, "pof:image-digest" = local.image_digest }
}

# ---------- The instance's role: its own secrets and the chosen models only ----------

data "aws_iam_policy_document" "assume" {
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
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "node" {
  statement {
    sid       = "ReadOwnSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = concat([aws_secretsmanager_secret.validator_key.arn], var.extra_secret_arns)
  }

  dynamic "statement" {
    for_each = length(var.bedrock_model_arns) > 0 ? [1] : []
    content {
      sid       = "InvokeChosenModelsOnly"
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
}

# ---------- The instance ----------

resource "aws_instance" "node" {
  count                                = var.create_instance ? 1 : 0
  ami                                  = aws_ami.checker[0].id
  instance_type                        = var.instance_type
  subnet_id                            = local.subnet_id
  vpc_security_group_ids               = [aws_security_group.node.id]
  iam_instance_profile                 = aws_iam_instance_profile.node.name
  instance_initiated_shutdown_behavior = "stop" # the node's power-off stops it; start it again to run again

  cpu_options {
    amd_sev_snp = "enabled" # set at launch only; it can't be turned off later (the doc above)
  }

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2          # the node's container reads the role's credentials (Secrets Manager, Bedrock)
  }

  ebs_block_device {
    device_name           = "/dev/sdf"
    volume_type           = "gp3"
    volume_size           = var.data_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  user_data                   = local.user_data
  user_data_replace_on_change = false

  # default_tags don't reach the volumes: with var.tags set they're tagged at launch too (the data volume holds the
  # Radicle key). Empty (the default) leaves them untagged, as before, so an existing instance plans no change.
  volume_tags = length(var.tags) > 0 ? merge(var.tags, { Name = "${var.name}-node" }) : null

  tags = { Name = "${var.name}-node", "pof:roothash" = local.roothash }

  lifecycle {
    precondition {
      condition     = var.snapshot_id != ""
      error_message = "Set snapshot_id (the measured disk's snapshot) before create_instance = true."
    }
  }
}
