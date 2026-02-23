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

### 허깅페이스 ###
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


```
from autofp8 import AutoFP8ForCausalLM, BaseQuantizeConfig
from transformers import AutoTokenizer

model_id = "meta-llama/Meta-Llama-3-8B"

# 1. 설정 (정적 양자화)
quantize_config = BaseQuantizeConfig(quant_method="fp8", activation_scheme="static")

# 2. 모델 및 토크나이저 로드
model = AutoFP8ForCausalLM.from_pretrained(model_id, quantize_config)
tokenizer = AutoTokenizer.from_pretrained(model_id)

# 3. 캘리브레이션 데이터셋 준비 (직접 만들기)
# 실제로는 CNN/DailyMail이나 WikiText 같은 데이터를 로드해서 사용합니다.
calibration_data = [
    "퀀타이제이션은 모델의 크기를 줄이고 속도를 높이는 기술입니다.",
    "Llama-3 모델은 대규모 언어 모델로서 매우 뛰어난 성능을 보여줍니다.",
    "FP8 연산은 최신 NVIDIA GPU에서 강력한 가속 성능을 제공합니다.",
    # ... 보통 128~512개의 샘플 문장을 넣습니다.
]

# 문장들을 토큰화하여 모델이 읽을 수 있는 형태로 변환
examples = []
for text in calibration_data:
    # 모델의 최대 길이에 맞춰 자르거나 조절합니다.
    tokenized = tokenizer(text, truncation=True, max_length=512, return_tensors="pt")
    examples.append(tokenized)

# 4. 퀀타이제이션 실행 (이때 데이터셋이 들어갑니다!)
# 'examples' 파라미터가 바로 우리가 공부한 캘리브레이션 데이터입니다.
model.quantize(examples=examples)

# 5. 저장
model.save_quantized("./Llama-3-8B-FP8-Local")
```



## 참고자료 ##

* [Optimizing LLMs for Performance and Accuracy with Post-Training Quantization](https://developer.nvidia.com/blog/optimizing-llms-for-performance-and-accuracy-with-post-training-quantization/)

