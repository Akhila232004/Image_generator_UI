import torch
from diffusers import AutoPipelineForImage2Image
from PIL import Image


MODEL_ID = "stable-diffusion-v1-5/stable-diffusion-v1-5"

print("========================================")
print("Stable Diffusion 1.5 - RTX 2050 Test")
print("========================================")

print("Loading Stable Diffusion 1.5...")
print("CUDA available:", torch.cuda.is_available())

if not torch.cuda.is_available():
    raise RuntimeError("CUDA is not available.")

print("GPU:", torch.cuda.get_device_name(0))
print(
    "VRAM:",
    round(
        torch.cuda.get_device_properties(0).total_memory / 1024**3,
        2,
    ),
    "GB",
)

pipe = AutoPipelineForImage2Image.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,
    use_safetensors=True,
)

# Important for a 4 GB RTX 2050.
# This keeps most model components on CPU and moves them
# to the GPU only when needed.
pipe.enable_model_cpu_offload()

# VAE memory optimizations.
# These methods are available on the VAE in current Diffusers.
if hasattr(pipe, "vae"):

    if hasattr(pipe.vae, "enable_slicing"):
        pipe.vae.enable_slicing()
        print("VAE slicing: enabled")

    if hasattr(pipe.vae, "enable_tiling"):
        pipe.vae.enable_tiling()
        print("VAE tiling: enabled")

# Create a simple reference image.
reference = Image.new(
    "RGB",
    (512, 512),
    (230, 230, 230),
)

prompt = (
    "A professional modern technology training poster, "
    "clean corporate layout, software development theme, "
    "modern typography, professional educational design"
)

print()
print("Starting image generation...")
print("Resolution: 512 x 512")
print("Steps: 20")
print("Strength: 0.55")
print()

try:

    result = pipe(
        prompt=prompt,
        image=reference,
        strength=0.55,
        guidance_scale=7.0,
        num_inference_steps=20,
    ).images[0]

except torch.cuda.OutOfMemoryError:

    print()
    print("CUDA OUT OF MEMORY")
    print("Clearing CUDA cache...")

    torch.cuda.empty_cache()

    raise

output_path = "sd15_test_output.png"

result.save(output_path)

print()
print("========================================")
print("Generation completed successfully!")
print("Output:", output_path)
print("========================================")