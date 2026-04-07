output "vscode" {
  value = "http://${aws_instance.gpu_box.public_ip}:9090"
}

output "eks_cluster_name" {
  value = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  value = aws_eks_cluster.main.endpoint
}

output "karpenter_role_arn" {
  value = aws_iam_role.karpenter_controller.arn
}
