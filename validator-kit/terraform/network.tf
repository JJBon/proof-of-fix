# One small VPC with one public subnet and an internet gateway: the node gets a public IPv4 address only while it runs,
# accepts no inbound traffic, and reaches only the egress ports. No NAT gateway (about $33 a month idle).

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.tags, { Name = var.name })
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = merge(local.tags, { Name = var.name })
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.vpc_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags                    = merge(local.tags, { Name = "${var.name}-public" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = merge(local.tags, { Name = "${var.name}-public" })

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# No ingress rules at all: shell access is through SSM Session Manager.
resource "aws_security_group" "node" {
  name        = "${var.name}-node"
  description = "proof-of-fix validator node: no inbound, HTTPS out"
  vpc_id      = aws_vpc.main.id
  tags        = local.tags
}

resource "aws_vpc_security_group_egress_rule" "node" {
  for_each          = toset([for p in var.egress_ports : tostring(p)])
  security_group_id = aws_security_group.node.id
  description       = "egress tcp ${each.value}"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
  cidr_ipv4         = "0.0.0.0/0"
}
