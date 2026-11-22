# One small VPC with one public subnet: inbound TCP 8776 (Radicle's peer port) only, no SSH, no NAT.

data "aws_ec2_instance_type_offerings" "here" {
  location_type = "availability-zone"
  filter {
    name   = "instance-type"
    values = [var.instance_type]
  }
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = var.name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = var.name }
}

# No address on launch: the seed's one public IPv4 is the Elastic IP (main.tf), so its external address is fixed
# before the instance boots. The install waits for it (seed/radicle/install.sh).
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.vpc_cidr
  availability_zone       = sort(data.aws_ec2_instance_type_offerings.here.locations)[0]
  map_public_ip_on_launch = false
  tags                    = { Name = "${var.name}-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.name}-public" }

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "seed" {
  name        = "${var.name}-seed"
  description = "proof-of-fix Radicle seed: inbound TCP 8776 only (no SSH); out to peers, HTTPS and DNS"
  vpc_id      = aws_vpc.main.id
}

# The only inbound rule: other Radicle nodes reach the seed on its peer port. Access to the host is Session Manager
# (outbound HTTPS from its agent), or nothing (ssm_access = false).
resource "aws_vpc_security_group_ingress_rule" "radicle" {
  security_group_id = aws_security_group.seed.id
  description       = "Radicle peers"
  ip_protocol       = "tcp"
  from_port         = 8776
  to_port           = 8776
  cidr_ipv4         = "0.0.0.0/0"
}

# Out: the peers it dials (8776), HTTPS (the pinned Radicle release, Amazon Linux's packages, Session Manager).
resource "aws_vpc_security_group_egress_rule" "seed" {
  for_each          = toset([for p in var.egress_ports : tostring(p)])
  security_group_id = aws_security_group.seed.id
  description       = "egress tcp ${each.value}"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
  cidr_ipv4         = "0.0.0.0/0"
}

# DNS (the VPC resolver) is inside the VPC; NTP and the instance metadata are link-local and need no rule.
resource "aws_vpc_security_group_egress_rule" "dns" {
  for_each          = toset(["udp", "tcp"])
  security_group_id = aws_security_group.seed.id
  description       = "DNS to the VPC resolver (${each.value})"
  ip_protocol       = each.value
  from_port         = 53
  to_port           = 53
  cidr_ipv4         = var.vpc_cidr
}
