import subprocess
import time
from pathlib import Path
import requests
import modal

dockerfile_path = Path(__file__).parent / "Dockerfile"
voice_presets_path = Path(__file__).parent / "my_voices"
VLLM_PORT = 8000
HEALTH_POLL_TIME = 60  # times the sleep time per polling  
FAST_BOOT = False # if true, will not use cuda graph, fast boot slower generation 

# The server is running on port 8000 inside the same container
generate_url = "http://127.0.0.1:8000/v1/audio/speech"
health_url = "http://127.0.0.1:8000/health"

# Had to overwrite the ENTRYPOINT in the "bosonai/higgs-audio-vllm:latest" dockerfile,
# in order to set "docker run" flags (server_command).
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
    scaledown_window=500,  # stays up 5 min with no requests
    timeout=500,  # 8 min max to start server
    # caches weights from models / JIT compilation from vllm
    volumes={
        "/root/.cache/huggingface": hf_cache_volume,
        "/root/.cache/vllm": vllm_cache_volume
    },
    max_containers=1
)

class VllmServer:
    server_process: subprocess.Popen | None = None
    server_ready: bool = False

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
            "--gpu-memory-utilization", "0.80",
            "--disable-mm-preprocessor-cache",
            "--voice-presets-dir", "/app/voice_presets/",
        ]

        # server_command += ["--enforce-eager" if FAST_BOOT else "--no-enforce-eager"]

        print("Starting Higgs Audio server...")
        # Launch the command as a subprocess
        import threading, subprocess
        self.server_process = subprocess.Popen(
            server_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
            )
        
        def log_stream():
            for line in self.server_process.stdout:
                print("[vllm]", line.strip())
        threading.Thread(target=log_stream, daemon=True).start()
        
        # poll health until vllm ready
        for _ in range(90):
            try:
                r = requests.get(health_url)
                if r.status_code == 200:
                    print("vLLM ready")
                    self.server_ready = True
                    return "Server started and healthy"
            except Exception:
                pass
            time.sleep(5)

        return "Server launch attempted, but health not confirmed"
    
    @modal.exit()
    def stop(self):
        print("Shutting down server process...")
        self.server_process.terminate()

    # @modal.fastapi_endpoint(label="health", method="GET")
    # def health(self):
    #     import threading
    #     def log_stream():
    #         for line in self.server_process.stdout:
    #             print("[vllm]", line.strip())
    #     threading.Thread(target=log_stream, daemon=True).start()

    #     for _ in range(60):
    #         if self.server_ready:
    #             return "Server is healthy"
    #         else:
    #             time.sleep(5)
                
    #     return "Server launch attempted, but health not confirmed"

    @modal.fastapi_endpoint(label="warmup", method="GET")
    def warmup(self):
        # Check health before forwarding
        # if its stoped the request will initiate it "start_server()"
        from fastapi.responses import JSONResponse
        
        try:
            for attempt in range(90):  
                try:
                    r = requests.get(health_url, timeout=10)
                    if r.status_code == 200:
                        return JSONResponse({"status": "ready", "warmup_time_seconds": attempt * 5})
                except Exception:
                    pass
                time.sleep(5)
            
            return JSONResponse({"status": "timeout"}, status_code=503)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


    @modal.fastapi_endpoint(label="generate", method="POST")
    def generate(self, request: dict):
        # forwards requests to running vllm
        import requests
        from fastapi.responses import StreamingResponse, JSONResponse
        
        try:
            response = requests.post(generate_url, json=request, stream=True)
            response.raise_for_status()
            
            def generate_audio_stream():
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        yield chunk    

            # Return a streaming response with the correct content type
            # will later catch output octet stream with ffmpeg in the sh script
            return StreamingResponse(
                generate_audio_stream(),
                headers={"Content-Type": "application/octet-stream"}
            )

        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
  