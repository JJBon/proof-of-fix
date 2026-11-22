# The release candidate's test chain (proof-of-fix#251 task 7.0; design L18 items 3, 4 and 6; the owner's decision of
# 2026-11-21): one temporary c6a.xlarge beside the SEV-SNP host, in the kit's VPC, running the chain (anvil) on
# production windows with the moved clock, the Radicle seed, and the six other validators of the release candidate's
# external set (tests/integration/external_v3.py), all as Docker containers from pinned images that
# scripts/rc-aws.sh uploads to this module's bucket. validator-kit/SEVSNP-PLAN.md, "The release candidate's run", is
# the order of the steps.
#
# create_instance = false (the default) makes only what costs nothing. true adds the instance (stopped after its
# first boot's setup by nobody but scripts/rc-aws.sh and the auto-stop) and the auto-stop Lambda. No SSH, no key pair,
# no inbound port from the internet: SSM only (Run Command for the run, port forwarding for this machine's view).

locals {
  ami = var.ami_id != "" ? var.ami_id : (var.create_instance ? data.aws_ssm_parameter.al2023[0].value : "")
  user_data = templatefile("${path.module}/user-data.yaml.tftpl", {
    rc_remote        = base64gzip(file("${path.module}/rc-remote.sh"))
    autostop_minutes = var.autostop_hours * 60
    daemon_json      = base64gzip(file("${path.module}/daemon.json"))
  })
}

data "aws_caller_identity" "current" {}

data "aws_ssm_parameter" "al2023" {
  count = var.create_instance && var.ami_id == "" ? 1 : 0
  name  = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# ---------- The run's bucket: the commit's bundle, the images, solc; nothing public, deleted after a week ----------

resource "aws_s3_bucket" "run" {
  bucket_prefix = "${var.name}-"
  force_destroy = true # temporary: `tofu destroy` empties it
}

resource "aws_s3_bucket_public_access_block" "run" {
  bucket                  = aws_s3_bucket.run.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "run" {
  bucket = aws_s3_bucket.run.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "run" {
  bucket = aws_s3_bucket.run.id
  rule {
    id     = "expire"
    status = "Enabled"
    filter {}
    expiration {
      days = var.bucket_expire_days
    }
  }
}

# ---------- The instance's role: SSM (Run Command and sessions) and its own bucket ----------

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "host" {
  name               = "${var.name}-host"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# AWS's managed policy for the SSM agent (registration, Run Command, Session Manager's channels); no other service.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "bucket" {
  statement {
    sid       = "ThisRunsBucketOnly"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.run.arn}/*"]
  }
  statement {
    sid       = "ListThisBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.run.arn]
  }
}

resource "aws_iam_role_policy" "bucket" {
  name   = "run-bucket"
  role   = aws_iam_role.host.id
  policy = data.aws_iam_policy_document.bucket.json
}

resource "aws_iam_instance_profile" "host" {
  name = "${var.name}-host"
  role = aws_iam_role.host.name
}

# ---------- The instance ----------

resource "aws_instance" "host" {
  count                                = var.create_instance ? 1 : 0
  ami                                  = local.ami
  instance_type                        = var.instance_type
  subnet_id                            = data.aws_subnet.kit.id
  vpc_security_group_ids               = [aws_security_group.testchain.id]
  iam_instance_profile                 = aws_iam_instance_profile.host.name
  associate_public_ip_address          = true   # outbound only (SSM, S3, the repository); the group admits nothing from the internet
  instance_initiated_shutdown_behavior = "stop" # its own shutdown timer stops it

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1          # the host's AWS CLI only; no container reads the role
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.disk_gb
    encrypted             = true
    delete_on_termination = true
  }

  user_data                   = local.user_data
  user_data_replace_on_change = false

  tags = { Name = "${var.name}-host" }

  lifecycle {
    ignore_changes = [ami] # a new AL2023 AMI doesn't replace a stopped host; pin ami_id to change it
  }
}
