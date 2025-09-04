### Modal Image for bosonai/higgs-audio-vllm from docker registry

├── Cache model weights in Volume
├── Cache vllm JIT artifacts in Volume
├── Faster container startup (no model loading)
├── Health check endpoint (also initialize vllm if cold)
├── Generate endpoint return audio stream
├── TODO: request queuing
└── TODO: model weights in image build

#### Usage:


#### Notes on vllm:
- vllm applies virtual memory and paging to the KV Cache. Like an OS, instead of a contiguous chunk for each KV cache, vllm divides the GPU's VRAM into small, fixed-size blocks. Each KV cache is given a block table (page table), simply mapping the logical position of a token in the KV cache to the physical block in VRAM.
1. New request -> vllm allocate blocks for prompt's KV cache (can be anywhere in memory), block talbe keeps track.
2. To read these block tables a custom PagedAttention CUDA kernel is needed, to fetch keys and values from VRAM.
Benefits: Since blocks are small and fixed-size, there's no internal waste. And since they can be placed anywhere, external fragmentation is virtually eliminated.