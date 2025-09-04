# replace with returned url drom modal
MODAL_URL="https://felenclilian2018--generate.modal.run"
WARMUP_URL="https://felenclilian2018--warmup.modal.run"
TIME=$(date +"%T")
file="speech_from_modal_$TIME"

warmup_response=$(curl -s -w "%{http_code}" -o /dev/null "$WARMUP_URL")

if [ "$warmup_response" = "200" ]; then
    echo "Server is ready"
else
    echo "Server is cold, warming up..."
    sleep 10
fi

http_status=$(curl -X POST "$MODAL_URL" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "higgs-audio-v2-generation-3B-base",
            "voice": "peter_griffin",
            "input": "Your VRAM becomes a mess of allocated and free blocks, like a game of Tetris gone wrong. A new request might arrive that needs 2GB, and you might have 3GB of free VRAM in total, but it s scattered in small, non-contiguous chunks. You can t fit the new request, so it has to wait.",
            "response_format": "pcm"
        }' \
        -w "%{http_code}" \
        -s \
        --output - | \
        tee >(tail -c 3 > /tmp/http_status) | \
        head -c -3 | \
        ffmpeg -f s16le -ar 24000 -ac 1 -i - "$file.wav" 2>/dev/null)

  # trim audio cmd exemple: fmpeg -ss 25.28 -i griffin.wav -to 13.59 -c copy test_griffin.wav

  # SoX/ffmpeg pipeline for audio manipulation
  # vosk for speech to text