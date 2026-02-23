기본 설치된 CUDA 12.8용 PyTorch 대신, CUDA 13.0 환경에서 빌드된 PyTorch 2.9.1 버전을 설치한다. PyTorch와 CUDA 런타임 버전을 일치시켜야 드라이버 충돌이나 성능 저하 없이 GPU 연산을 수행할 수 있다.

고성능 병렬 계산을 위한 OpenMPI 개발 라이브러리를 설치한다.TensorRT-LLM은 대규모 모델을 여러 개의 GPU에 나누어 처리(모델 병렬화)할 때 GPU 간 통신이 필수적이다. 

메시지 큐 라이브러리인 ZeroMQ(ZMQ) 개발 패키지를 설치한다. disagg-serving' (Disaggregated Serving)을 위한 설정으로 
추론 과정 중 '입력값 처리(Prefill)'와 '토큰 생성(Decode)' 단계를 서로 다른 노드/GPU에서 분리해서 처리되는데, 이때 서로 다른 서버(노드) 간에 데이터를 빠르고 안정적으로 주고받기 위해 ZeroMQ라는 통신 엔진이 사용된다.

```bash 
pip3 install torch==2.9.1 torchvision --index-url https://download.pytorch.org/whl/cu130

sudo apt-get -y install libopenmpi-dev

# Optional step: Only required for disagg-serving
sudo apt-get -y install libzmq3-dev
```
