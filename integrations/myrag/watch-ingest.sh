#!/usr/bin/env bash
# Watch MyRAG ingestion progress
# Usage: ./watch-ingest.sh [job_id] [interval_seconds]
#
# Examples:
#   ./watch-ingest.sh              # list all jobs
#   ./watch-ingest.sh abc12345     # watch specific job
#   ./watch-ingest.sh abc12345 2   # watch every 2 seconds

JOB_ID="${1:-}"
INTERVAL="${2:-3}"
MYRAG_URL="${MYRAG_URL:-http://localhost:8200}"

if [ -z "$JOB_ID" ]; then
    echo "All jobs:"
    curl -sf "$MYRAG_URL/api/ingest/jobs" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for j in data.get('jobs', []):
    pct = j['progress_pct']
    bar_len = 20
    filled = int(bar_len * pct / 100) if pct else 0
    bar = '█' * filled + '░' * (bar_len - filled)
    print(f'  {j[\"job_id\"]} | [{bar}] {j[\"uploaded_chunks\"]}/{j[\"total_chunks\"]} ({pct}%) | {j[\"status\"]} | {j[\"collection\"]} | {j[\"filename\"]}')
"
    exit 0
fi

echo "Watching job $JOB_ID on $MYRAG_URL (every ${INTERVAL}s)"
echo "Press Ctrl+C to stop"
echo ""

while true; do
    DATA=$(curl -sf "$MYRAG_URL/api/ingest/jobs/$JOB_ID" 2>/dev/null)
    if [ -z "$DATA" ]; then
        echo "$(date +%H:%M:%S) | Cannot reach MyRAG or job not found"
        sleep "$INTERVAL"
        continue
    fi

    python3 -c "
import sys, json
j = json.loads('''$DATA''')
total = j['total_chunks']
uploaded = j['uploaded_chunks']
failed = j['failed_chunks']
pct = j['progress_pct']
elapsed = j['elapsed_seconds']
status = j['status']

bar_len = 30
filled = int(bar_len * pct / 100) if pct else 0
bar = '█' * filled + '░' * (bar_len - filled)

eta = ''
if uploaded > 0 and pct < 100:
    rate = uploaded / elapsed if elapsed > 0 else 0
    remaining = (total - uploaded) / rate if rate > 0 else 0
    eta = f' | ETA: {int(remaining)}s'

fail_str = f' | ❌ {failed} failed' if failed > 0 else ''
print(f'$(date +%H:%M:%S) | [{bar}] {uploaded}/{total} ({pct}%) | {status} | {elapsed:.0f}s{eta}{fail_str}')

if status in ('done', 'done_with_errors', 'failed'):
    print(f'\\nFinished: {j[\"collection\"]} ({j[\"filename\"]}) — {uploaded} chunks, sensitivity={j[\"sensitivity\"]}')
    sys.exit(42)
" 2>/dev/null

    [ $? -eq 42 ] && break
    sleep "$INTERVAL"
done
