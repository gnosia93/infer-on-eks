#!/bin/bash
# userdata.sh
set -e                                     # 에러 나면, 즉시 중단
exec > /var/log/userdata.log 2>&1          # 프로세스 교체 없이, 현재 셸의 출력만 변경
echo "=== UserData Start ==="

# ============================================================
# 1. VS Code Server (code-server)
# ============================================================
sudo -u ubuntu -i <<'EC2_USER_SCRIPT'
echo "=== UserData Start 2 ==="
curl -fsSL https://code-server.dev/install.sh | sh && sudo systemctl enable --now code-server@ubuntu
echo "=== UserData Start 3 ==="
sleep 5
sed -i 's/127.0.0.1:8080/0.0.0.0:9090/g; s/^password: .*/password: code!@#c/g' /home/ubuntu/.config/code-server/config.yaml
EC2_USER_SCRIPT

# ============================================================
# 2. Python 환경
# ============================================================
sudo -u ubuntu -i bash -c '
source /home/ubuntu/anaconda3/bin/activate
conda create -n gpu-dev python=3.11 -y
conda activate gpu-dev

pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install jupyterlab ipykernel
python -m ipykernel install --user --name gpu-dev --display-name "gpu-dev"
pip install huggingface_hub
'

# ============================================================
# 3. VS Code 확장
# ============================================================
sudo -u ubuntu -i code-server \
  --install-extension ms-python.python \
  --install-extension ms-toolsai.jupyter \
  --install-extension ms-toolsai.jupyter-keymap \
  --install-extension ms-toolsai.jupyter-renderers

# ============================================================
# 4. VS Code 설정 (conda 환경 연결)
# ============================================================
sudo -u ubuntu -i bash -c '
mkdir -p /home/ubuntu/.local/share/code-server/User
cat > /home/ubuntu/.local/share/code-server/User/settings.json <<EOF
{
  "python.defaultInterpreterPath": "/home/ubuntu/anaconda3/envs/gpu-dev/bin/python",
  "jupyter.kernels.filter": [],
  "python.condaPath": "/home/ubuntu/anaconda3/bin/conda"
}
EOF
'

systemctl restart code-server@ubuntu
echo "=== UserData Complete ==="
