# replace with returned url drom modal
MODAL_URL="https://felenclilian2018--generate.modal.run"

curl -X POST "$MODAL_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "higgs-audio-v2-generation-3B-base",
    "voice": "peter_griffin",
    "input": "LeBron James is the greatest basketball player of all time.",
    "response_format": "pcm"
  }' \
  --output - | ffmpeg -f s16le -ar 24000 -ac 1 -i - speech_from_modal.wav

  # trim audio cmd exemple: fmpeg -ss 25.28 -i griffin.wav -to 13.59 -c copy test_griffin.wav

  # SoX/ffmpeg pipeline for audio manipulation
  # vosk for speech to text