# proof-of-fix's Radicle seed (#251 design L14, decided by the owner on 2026-11-20): one small always-on Graviton
# instance running radicle-node with a selective policy, block by default and seed proof-of-fix's RID only. seed/README.md
# is the order of the steps: it is applied only after the Radicle publish (task 6.2), when the owner says to start it
# (task 6.3).
#
# create_instance = false (the default) makes only what costs nothing (the VPC, the security group, the role, the
# budget). true adds the instance, its encrypted data volume and its Elastic IP. The RID comes only from the publication
# record written at the publish (seed/publication.py's format), never from these files.

locals {
  # The pinned release: the same Radicle as the spike and the seed's test (spikes/radicle/Dockerfile, heartwood 1.10.3,
  # commit 7e1cb406bb935c3de008d2171e8961f57b4336ea), the aarch64 musl static build for Graviton. Its SHA-256 equals
  # the release's own .sha256 file (checked 2026-11-20); the host refuses the download unless it matches.
  radicle_version = "1.10.3"
  radicle_target  = "aarch64-unknown-linux-musl"
  radicle_sha256  = "822c1ea1da7dd3a2a7f98da6d93b95359b5b9b0e302b8535bea377a2441e596f"

  record = var.publication_record != "" ? jsondecode(file(var.publication_record)) : null
  rid    = local.record != null ? try(tostring(local.record.rid), "") : ""

  external_address = var.external_address != "" ? var.external_address : (
    var.create_instance ? "${aws_eip.seed[0].public_ip}:8776" : ""
  )
}

data "aws_ssm_parameter" "al2023_arm64" {
  count = var.create_instance ? 1 : 0
  name  = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

# ---------- The instance's role: Session Manager only, or nothing ----------

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "seed" {
  name               = "${var.name}-seed"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# A shell through Session Manager, with no SSH and no inbound port: the agent's registration and its channels, nothing
# else (narrower than AmazonSSMManagedInstanceCore). The seed itself reads no secret; the keeper's two are below.
data "aws_iam_policy_document" "ssm" {
  statement {
    sid       = "SessionManagerOnly"
    actions   = ["ssm:UpdateInstanceInformation", "ssmmessages:CreateControlChannel", "ssmmessages:CreateDataChannel", "ssmmessages:OpenControlChannel", "ssmmessages:OpenDataChannel"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ssm" {
  count  = var.ssm_access ? 1 : 0
  name   = "session-manager"
  role   = aws_iam_role.seed.id
  policy = data.aws_iam_policy_document.ssm.json
}

# The keeper (owner's approval, 2026-11-23): a keeper-only v3 node on this host (oracle/keeper.py, run as the
# pof-keeper systemd unit) reads its account's key and the chain's RPC URL from Secrets Manager with this role. Exactly
# the listed secrets, GetSecretValue only (both are under the account's default aws/secretsmanager key). Empty: none.
data "aws_iam_policy_document" "keeper" {
  count = length(var.keeper_secret_arns) > 0 ? 1 : 0
  statement {
    sid       = "KeeperSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.keeper_secret_arns
  }
}

resource "aws_iam_role_policy" "keeper" {
  count  = length(var.keeper_secret_arns) > 0 ? 1 : 0
  name   = "keeper-secrets"
  role   = aws_iam_role.seed.id
  policy = data.aws_iam_policy_document.keeper[0].json
}

resource "aws_iam_instance_profile" "seed" {
  name = "${var.name}-seed"
  role = aws_iam_role.seed.name
}

# ---------- The seed ----------

# The public IPv4, allocated before the instance so its address is in the node's config from the first boot.
resource "aws_eip" "seed" {
  count  = var.create_instance ? 1 : 0
  domain = "vpc"
  tags   = { Name = "${var.name}-seed" }
}

# The node's key and storage: a separate volume, so a replaced instance keeps the same Node ID and the repository.
resource "aws_ebs_volume" "data" {
  count             = var.create_instance ? 1 : 0
  availability_zone = aws_subnet.public.availability_zone
  type              = "gp3"
  size              = var.data_volume_gb
  encrypted         = true
  tags              = { Name = "${var.name}-data" }
}

resource "aws_instance" "seed" {
  count                  = var.create_instance ? 1 : 0
  ami                    = data.aws_ssm_parameter.al2023_arm64[0].value
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.seed.id]
  iam_instance_profile   = aws_iam_instance_profile.seed.name

  credit_specification {
    cpu_credits = "standard" # no surplus-credit charges: a busy hour is throttled, never billed
  }

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_gb
    encrypted   = true
  }

  user_data_replace_on_change = true # the key and storage are on the data volume, so a replacement keeps them
  user_data = templatefile("${path.module}/user-data.yaml.tftpl", {
    install_sh       = base64gzip(file("${path.module}/../radicle/install.sh"))
    seed_setup_sh    = base64gzip(file("${path.module}/../radicle/seed-setup.sh"))
    config_json      = base64gzip(file("${path.module}/../radicle/config.json"))
    unit             = base64gzip(file("${path.module}/../radicle/radicle-seed.service"))
    radicle_version  = local.radicle_version
    radicle_target   = local.radicle_target
    radicle_sha256   = local.radicle_sha256
    data_volume_id   = aws_ebs_volume.data[0].id
    rid              = local.rid
    alias            = var.alias
    external_address = local.external_address
  })

  tags = { Name = "${var.name}-seed" }

  lifecycle {
    ignore_changes = [ami] # a new Amazon Linux AMI shouldn't replace a running seed; bump deliberately

    precondition {
      condition     = local.record != null && try(local.record.format, "") == "pof-radicle-publication/1"
      error_message = "Set publication_record to the pof-radicle-publication/1 record written at the Radicle publish (task 6.2) before create_instance = true."
    }
    precondition {
      condition     = can(regex("^rad:z[1-9A-HJ-NP-Za-km-z]+$", local.rid))
      error_message = "The publication record's rid is not a Radicle RID (rad:z...)."
    }
    precondition {
      condition     = try(local.record.radicle, "") == local.radicle_version
      error_message = "The publication record names another Radicle release than the seed's pinned one (1.10.3): check the release (#92, task 6.2) and pin it here first."
    }
    precondition {
      condition     = can(regex("^[A-Za-z0-9.-]{1,253}:[0-9]{1,5}$", local.external_address))
      error_message = "external_address must be host:port."
    }
  }
}

resource "aws_volume_attachment" "data" {
  count       = var.create_instance ? 1 : 0
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data[0].id
  instance_id = aws_instance.seed[0].id
}

resource "aws_eip_association" "seed" {
  count         = var.create_instance ? 1 : 0
  allocation_id = aws_eip.seed[0].id
  instance_id   = aws_instance.seed[0].id
}
