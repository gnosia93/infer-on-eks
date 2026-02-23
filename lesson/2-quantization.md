### FP8 연산 지원여부 체크 ###
FP8 하드웨어 가속(Tensor Core)은 NVIDIA Ada Lovelace(RTX 40 시리즈) 또는 Hopper(H100) 아키텍처부터 공식 지원한다.
```
import torch

# 1. 아키텍처 확인 (Compute Capability 8.9 이상 필요)
capability = torch.cuda.get_device_capability()
print(f"GPU Compute Capability: {capability}")

if capability >= (8, 9):
    print("✅ FP8 하드웨어 가속을 지원하는 GPU입니다! (RTX 40xx, H100 등)")
else:
    print("❌ FP8 가속은 어렵지만, 소프트웨어 에뮬레이션은 가능할 수 있습니다.")

# 2. 실제 FP8 데이터 타입 생성 테스트
try:
    x = torch.randn(2, 2).to(dtype=torch.float8_e4m3fn, device="cuda")
    print("✅ FP8(E4M3) 텐서 생성 성공!")
except Exception as e:
    print(f"❌ FP8 타입 생성 실패: {e}")
```

```
from autofp8 import AutoFP8ForCausalLM, BaseQuantizeConfig
from transformers import AutoTokenizer

model_id = "meta-llama/Meta-Llama-3-8B" # 원본 모델

# 1. 퀀타이제이션 설정 (E4M3 형식 사용)
# 캘리브레이션 데이터셋으로 'ultrachat200k' 등을 주로 사용합니다.
quantize_config = BaseQuantizeConfig(quant_method="fp8", activation_scheme="static")

# 2. 모델 로드 및 8비트 변환 (Calibration 포함)
# 이 과정에서 내부적으로 샘플 데이터를 흘려보내 스케일링 팩터를 구합니다.
model = AutoFP8ForCausalLM.from_pretrained(model_id, quantize_config)
tokenizer = AutoTokenizer.from_pretrained(model_id)

# 3. 8비트 모델 저장 (가중치 + 스케일링 팩터가 저장됨)
save_path = "./Llama-3-8B-FP8"
model.save_quantized(save_path)
print(f"✅ 모델이 {save_path}에 저장되었습니다.")

# 4. 추론 테스트 (vLLM 엔진 사용 시 극강의 속도)
from vllm import LLM, SamplingParams

llm = LLM(model=save_path) # 저장된 FP8 모델 로드
output = llm.generate(["퀀타이제이션의 장점은?"], SamplingParams(temperature=0.7))

print(f"결과: {output[0].outputs[0].text}")
```
* activation_scheme="static": 우리가 공부한 정적 캘리브레이션 방식입니다. 파일에 스케일 팩터를 박아넣습니다.
* AutoFP8: 내부적으로 NVIDIA Transformer Engine을 활용하여 H100 등에서 최적의 성능을 낼 수 있도록 변환해 줍니다.
* 저장된 파일: 저장 폴더를 열어보면 가중치 파일은 줄어들어 있고, quantize_config.json 등에 스케일 정보가 기록된 것을 확인하실 수 있습니다.



## 참고자료 ##

* [Optimizing LLMs for Performance and Accuracy with Post-Training Quantization](https://developer.nvidia.com/blog/optimizing-llms-for-performance-and-accuracy-with-post-training-quantization/)

