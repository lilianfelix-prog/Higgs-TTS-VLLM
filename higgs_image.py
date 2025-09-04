import subprocess
import time
from pathlib import Path
import requests
import modal

dockerfile_path = Path(__file__).parent / "Dockerfile"
voice_presets_path = Path(__file__).parent / "my_voices"
VLLM_PORT = 8000
HEALTH_POLL_TIME = 60  # times the sleep time per polling  
FAST_BOOT = True

image = modal.Image.from_registry(
    "bosonai/higgs-audio-vllm:latest",
    setup_dockerfile_commands=["RUN apt-get update && apt-get install -y python3 python3-pip && \
    ln -s /usr/bin/python3 /usr/bin/python", 'ENTRYPOINT []' ]
).pip_install("fastapi[standard]").add_local_dir(voice_presets_path, "/app/voice_presets/", copy=True)
# .env()
app = modal.App("higgs-audio-server")
hf_cache_volume = modal.Volume.from_name("hf-cache", create_if_missing=True)
vllm_cache_volume = modal.Volume.from_name("vllm-cache", create_if_missing=True)

@app.cls(
    image=image,
    gpu="a10g",
    scaledown_window=300,  # how long should we stay up with no requests?
    timeout=500,  # how long should we wait for container start?
    volumes={
        "/root/.cache/huggingface": hf_cache_volume,
        "/root/.cache/vllm": vllm_cache_volume
    }
)

class VllmServer:
    @modal.enter()
    def start_server(self):
        server_command = [
            "python3", "-m", "vllm.entrypoints.bosonai.api_server",
            "--served-model-name", "higgs-audio-v2-generation-3B-base",
            "--model", "bosonai/higgs-audio-v2-generation-3B-base",
            "--audio-tokenizer-type", "bosonai/higgs-audio-v2-tokenizer",
            "--limit-mm-per-prompt", "audio=50",
            "--max-model-len", "8192",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--gpu-memory-utilization", "0.90",
            "--disable-mm-preprocessor-cache",
            "--voice-presets-dir", "/app/voice_presets/",
        ]

        server_command += ["--enforce-eager" if FAST_BOOT else "--no-enforce-eager"]

        print("🚀 Starting Higgs Audio server...")
        # Launch the command as a subprocess
        import threading, subprocess
        self.server_process = subprocess.Popen(
            server_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
            )
        
        def log_stream():
            for line in self.proc.stdout:
                print("[vllm]", line.strip())
        threading.Thread(target=log_stream, daemon=True).start()
        
    @modal.exit()
    def stop(self):
        print("Shutting down server process...")
        self.server_process.terminate()


@app.cls(
    image=image,
)
@modal.concurrent(max_inputs=15)

# used Higgs vllm docker run exemple
class HiggsAudioApi:
        
    @modal.fastapi_endpoint(label="generate", method="POST")
    def generate(self, request: dict):
        # forwards requests to running vllm
        import requests
        from fastapi.responses import StreamingResponse, JSONResponse
        
        # The server is running on port 8000 inside the same container
        target_url = "http://127.0.0.1:8000/v1/audio/speech"
        health_url = "http://127.0.0.1:8000/health"

        try:
            # Check health before forwarding
            r = requests.get(health_url, timeout=5)
            if r.status_code != 200:
                return JSONResponse({"error": "vLLM not healthy"}, status_code=503)

            response = requests.post(target_url, json=request, stream=True)
            response.raise_for_status()
            
            def generate_audio_stream():
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        yield chunk    # note to self; never used this before, it pause function (save func state: local var, instruction pointer) to return val

            # Return a streaming response with the correct content type
            # will later catch output octet stream with ffmpeg
            return StreamingResponse(
                generate_audio_stream(),
                headers={"Content-Type": "application/octet-stream"}
            )

        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        
    @modal.exit()
    def stop_server(self):
        print("Shutting down server process...")
        self.server_process.terminate()


