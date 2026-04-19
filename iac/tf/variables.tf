variable "aws_region" {
  description = "AWS Region to deploy resources"
  type        = string
  default     = "ap-northeast-2"          # 원하는 리전으로 변경 (예: "us-east-1")
}

variable "cluster_name" {
  type        = string
  default     = "eks-agentic-ai"
}

variable "vpc_cidr_block" {
  description = "CIDR block for the main VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "gpu_type" {
  description = "EC2 Instance Type (x86) - used for bastion host"
  type        = string
#  default     = "g7e.4xlarge"
  default     = "c7i.2xlarge"
}

variable "system_node_instance_types" {
  description = "EKS system node Group Instance Type "
  type    = list(string)
  default = ["c7g.xlarge"]
}

variable "system_node_ami_type" {
  description = "시스템 노드 그룹의 AMI 타입"
  type        = string
  default     = "AL2023_ARM_64_STANDARD"

  validation {
    condition = contains([
      "AL2023_x86_64_STANDARD",            # 시스템 기본값, 하지만 이 워크샵에서는 default 에 ARM 으로 지정
      "AL2023_ARM_64_STANDARD",
      "AL2023_x86_64_NVIDIA",
      "AL2_x86_64",
      "AL2_x86_64_GPU",
      "AL2_ARM_64",
      "BOTTLEROCKET_x86_64",
      "BOTTLEROCKET_ARM_64",
    ], var.system_node_ami_type)
    error_message = "지원하지 않는 ami_type입니다. AL2023_ARM_64_STANDARD 같은 값을 써주세요."
  }
}



variable "key_name" {
  description = "AWS SSH Key Pair name for EC2 access"
  type        = string
  # TODO: 이 기본값을 사용자의 실제 AWS 키페어 이름으로 변경하세요.
  default     = "aws-kp-2" 
}

variable "vscode_password" {
  description = "VS Code Server password"
  type        = string
  sensitive   = false
  default     = "code!@#$"
  # default 없음 → apply 시 입력 프롬프트 뜸
}

# 공인 IP 확인
data "http" "my_ip" {
  url = "https://checkip.amazonaws.com"
}

variable "custom_allowed_ips" {
  description = "허용할 IP 리스트"
  type        = list(string)
  default     = []            # 필요한 경우 "10.0.0.0/8" 등을 추가
}

locals {
  # chomp로 개행 제거 후 /32 추가
  current_ip = "${chomp(data.http.my_ip.response_body)}/32"

  # 최종 리스트: 현재 내 IP + 변수로 받은 IP 리스트 합치기
  allowed_ip_cidrs = concat([local.current_ip], var.custom_allowed_ips)
}
