output "vscode" {
  value = "http://${aws_instance.gpu.public_ip}:8080"
}
