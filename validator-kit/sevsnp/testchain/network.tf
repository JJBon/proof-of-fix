# The test chain sits in the SEV-SNP kit's VPC and public subnet (validator-kit/sevsnp/terraform/network.tf), found by
# the Name tags the kit gives them; this module creates no network of its own, so it applies and destroys on its own
# without touching the kit's state. One exception, named: an egress rule on the kit's security group, to this host's
# group only, on the RPC port (the kit's own rules allow 443 and 8776 out; the RPC port isn't among them).
#
# Nothing listens to the internet: the host has a public IPv4 address only so it can reach SSM, S3 and its package
# repository without a NAT gateway (as the kit's host does), and its group admits the SEV-SNP host's group alone, on
# the chain's RPC port and the seed's. This machine reaches it through SSM port forwarding only.

data "aws_vpc" "kit" {
  tags = { Name = var.kit_name }
}

data "aws_subnet" "kit" {
  vpc_id = data.aws_vpc.kit.id
  tags   = { Name = "${var.kit_name}-public" }
}

data "aws_security_group" "kit_node" {
  vpc_id = data.aws_vpc.kit.id
  name   = "${var.kit_name}-node"
}

resource "aws_security_group" "testchain" {
  name        = "${var.name}-host"
  description = "proof-of-fix test chain (task 7.0): RPC and Radicle from the SEV-SNP host only"
  vpc_id      = data.aws_vpc.kit.id
}

resource "aws_vpc_security_group_ingress_rule" "from_sevsnp" {
  for_each                     = { rpc = var.rpc_port, seed = var.seed_port }
  security_group_id            = aws_security_group.testchain.id
  description                  = "${each.key} from the SEV-SNP host's group only"
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
  referenced_security_group_id = data.aws_security_group.kit_node.id
}

# HTTPS out: SSM's endpoints, S3 (the run's bucket), the AL2023 package repository at the first boot.
resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.testchain.id
  description       = "HTTPS out: SSM, S3, the AL2023 repository"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# DNS (the VPC resolver); NTP is Amazon's link-local service and needs no rule.
resource "aws_vpc_security_group_egress_rule" "dns" {
  for_each          = toset(["udp", "tcp"])
  security_group_id = aws_security_group.testchain.id
  description       = "DNS to the VPC resolver (${each.value})"
  ip_protocol       = each.value
  from_port         = 53
  to_port           = 53
  cidr_ipv4         = data.aws_vpc.kit.cidr_block
}

# The SEV-SNP host's node reaches the chain: out on the RPC port, to this host's group only.
resource "aws_vpc_security_group_egress_rule" "sevsnp_to_rpc" {
  security_group_id            = data.aws_security_group.kit_node.id
  description                  = "proof-of-fix test chain RPC (task 7.0, the testchain module)"
  ip_protocol                  = "tcp"
  from_port                    = var.rpc_port
  to_port                      = var.rpc_port
  referenced_security_group_id = aws_security_group.testchain.id
}
