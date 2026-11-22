# One small VPC with one public subnet in a zone that offers the instance type: no inbound, HTTPS and Radicle's 8776 out,
# no NAT (as v2's). No inbound for Radicle either: the validator's node dials the seed, and patches, issues and the
# delegates' signed refs travel both ways over that connection (tests/integration/kit_radicle.py, scenario O).

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

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.vpc_cidr
  availability_zone       = sort(data.aws_ec2_instance_type_offerings.here.locations)[0]
  map_public_ip_on_launch = true
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

# Its description is the first apply's ("HTTPS out"): changing it would replace the group under the stopped instance. The
# egress rules below are what it allows: egress_ports (443 and 8776).
resource "aws_security_group" "node" {
  name        = "${var.name}-node"
  description = "proof-of-fix SEV-SNP validator: no inbound, HTTPS out"
  vpc_id      = aws_vpc.main.id
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

# DNS (the VPC resolver) is UDP/TCP 53 inside the VPC; NTP is Amazon's link-local service. Neither needs a rule here.
resource "aws_vpc_security_group_egress_rule" "dns" {
  for_each          = toset(["udp", "tcp"])
  security_group_id = aws_security_group.node.id
  description       = "DNS to the VPC resolver (${each.value})"
  ip_protocol       = each.value
  from_port         = 53
  to_port           = 53
  cidr_ipv4         = var.vpc_cidr
}
