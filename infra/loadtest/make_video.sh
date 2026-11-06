#!/bin/bash
# A real MP4 of about the size asked for, to upload in the load test (W20 slice 6). It is made with
# the ffmpeg in the media image, so the media worker's checks and processing run on a genuine video,
# not on random bytes.
#
#   infra/loadtest/make_video.sh 100        # about 100 MiB at out/video.mp4
#   infra/loadtest/make_video.sh 20 out/small.mp4
set -euo pipefail
export MSYS_NO_PATHCONV=1

mib="${1:-100}"
target="${2:-out/video.mp4}"
image="${MMS_REGISTRY:-mms}/media:${MMS_TAG:-local}"
mkdir -p "$(dirname "$target")"
out="$(cd "$(dirname "$target")" && pwd)"

# About 6 Mbit/s: a phone's 720p clip. Noise keeps the encoder from compressing the picture to nothing.
seconds=$(( mib * 8 / 6 + 1 ))
docker run --rm --entrypoint ffmpeg -v "$out:/out" "$image" -y -loglevel error \
  -f lavfi -i "testsrc2=size=1280x720:rate=30,noise=alls=20:allf=t" -t "$seconds" \
  -c:v libx264 -preset ultrafast -b:v 6M -maxrate 6M -bufsize 12M -pix_fmt yuv420p -movflags +faststart \
  "/out/$(basename "$target")"
ls -l "$out/$(basename "$target")" | awk '{printf "%s: %.1f MiB\n", $NF, $5/1048576}'
