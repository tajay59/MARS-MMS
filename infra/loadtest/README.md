# Load test

Checks NFR-2 (reads under one second at the 95th percentile) with 50 users, 20 videos uploaded at
once and an hour's soak (plan decision W20-11, TRD §17). Locust drives the gateway as the seed
users, exactly as a browser does.

| File | What |
|---|---|
| `locustfile.py` | The mix: clients browse and comment (half the users), staff read dashboards and ask for summary reports, technicians sync 20 operations about every minute |
| `uploads.py` | `LOAD_UPLOADERS` (default 20) phones each uploading a video in 8 MiB presigned parts to the files host, then waiting for the media worker's processing |
| `base.py`, `common.py` | The signed-in virtual user, and where the target is |
| `seed_volume.py` | Seeds 250 stations, 1,000 requests and 500 visits through the real API (five times the demo data) |
| `make_video.sh` | A real MP4 of a chosen size, made with the media image's ffmpeg |
| `check_thresholds.py` | The verdict (below). Tested in `infra/tests/test_loadtest_thresholds.py` |

## Run it on the local stack

```sh
cd infra/loadtest
export LOAD_CONNECT=127.0.0.1            # connect here, keep the site's name in the Host header
python seed_volume.py                    # a few minutes: the gateway allows 300 calls a minute per user
./make_video.sh 100                      # out/video.mp4, about 100 MiB
locust -f locustfile.py,uploads.py --headless -u 70 -r 2 -t 30m --csv out/run
python check_thresholds.py out/run --prometheus http://127.0.0.1:9090 --window 1800
```

`-u` is the mix (50) plus the uploaders (20). The ramp is slow on purpose: **the gateway allows ten
sign-ins a minute per address**, so 70 users take about seven minutes to arrive. Without
`LOAD_CONNECT`, `LOAD_URL` is used as it is (the default is `https://mms.localhost`). `LOAD_PASSWORD`
is the seed users' password (`AUTH_SEED_PASSWORD`, default the local one).

## The thresholds

| Check | Limit | Source |
|---|---|---|
| Every read (GET) | 95th percentile under 1 second | NFR-2 |
| Failures | under 1% of all requests | plan decision W20-11 |
| A summary report asked for | ready within 2 minutes | plan decision W20-11 |
| Outbox (Prometheus) | the oldest unpublished row never over 30 seconds | plan decision W20-11 |
| Dead-letter topics (Prometheus) | nothing arrives during the run | plan decision W20-11 |

The video uploads are **reported, not judged**: the plan sets no number for them. What to read
there is that every part went up (`PUT video part` failures 0), that `video processed` finished, and,
on the host, the media worker's memory and time while it did (`docker stats`, or the Grafana
dashboard "jobs"). The first full run writes the numbers down (as W11's timings were).

## Where to run the full test

On a host that can take it and has no real data: **the production host before go-live, wiped
afterwards.** Never on the shared staging server, which has other sites on it (decision W4-8). CI runs a
small version of this (five users for a minute) on every pull request so the script cannot rot; the
full one is `.github/workflows/loadtest.yml`, run by hand.

`seed_volume.py` is for throwaway stacks and **refuses any host that is not local** unless
`LOAD_ALLOW_HOST` names it. It adds rows each time it runs (stations are skipped by code, requests and
visits are not), so wipe the stack afterwards (`docker compose down -v`) or delete the data on the
host.

## What a run does not show

- A laptop is not the production host: numbers from one are lower bounds, and say so where they are written.
- One address makes every request, as one office would: the gateway's per-address limit (10 sign-ins
  a minute) shapes the ramp. Virtual users share six seed users, and the limit of 300 requests a minute
  is per user, so a seed user carrying many virtual users could meet it; the mix keeps a seed user near
  a quarter of it (a click every ten seconds). If a run shows 429s in the statistics, that is the limit
  working, and the cause is too few seed users for the load, not a fault of the system.
- The mix is made up from the PRD, not measured from people. Change the weights in `locustfile.py`
  when the pilot shows what people really do.
