output "vscode_url" {
    value = "http://${aws_instance.x86_box.public_dns}:8080"
    description = "vscode URL"
}
