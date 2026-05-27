#!/bin/bash
# ── Josh AI Sales Agent — One-Click Start ─────────────────────────
cd "$(dirname "$0")"

GUNICORN=~/Library/Python/3.9/bin/gunicorn
CLOUDFLARED=~/cloudflared

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║      Josh — AI Sales Agent  🎙️  Starting...      ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Kill old instances
pkill -f "voice_agent\|gunicorn.*voice_agent" 2>/dev/null
pkill -f cloudflared 2>/dev/null
lsof -ti :5000 | xargs kill -9 2>/dev/null
sleep 2

# ── Start production server ───────────────────────────────────────
echo "▶ Starting Josh server..."
$GUNICORN --worker-class eventlet \
          -w 1 \
          --bind 0.0.0.0:5000 \
          --timeout 120 \
          --keep-alive 5 \
          --log-level warning \
          --access-logfile /tmp/josh_access.log \
          --error-logfile /tmp/josh_error.log \
          voice_agent:app &
SERVER_PID=$!

# Wait up to 15s for server to be ready
for i in $(seq 1 15); do
  sleep 1
  if curl -s http://localhost:5000/ > /dev/null 2>&1; then
    echo "✓ Server ready"
    break
  fi
  if [ $i -eq 15 ]; then
    echo "✗ Server didn't start. Check /tmp/josh_error.log"
    cat /tmp/josh_error.log 2>/dev/null | tail -10
    exit 1
  fi
done

# ── Start Cloudflare tunnel ───────────────────────────────────────
echo "▶ Starting tunnel..."
$CLOUDFLARED tunnel --url http://localhost:5000 --no-autoupdate > /tmp/josh_tunnel.log 2>&1 &

# Wait for tunnel URL
TUNNEL_URL=""
for i in $(seq 1 15); do
  sleep 1
  TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/josh_tunnel.log | head -1)
  if [ -n "$TUNNEL_URL" ]; then break; fi
done

if [ -n "$TUNNEL_URL" ]; then
  echo "✓ Tunnel: $TUNNEL_URL"
  # Update .env with new URL
  sed -i '' "s|PUBLIC_URL=.*|PUBLIC_URL=$TUNNEL_URL|" .env
else
  echo "⚠ Tunnel unavailable — dashboard still works on localhost"
  TUNNEL_URL="(not available)"
fi

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  ✅  Josh is ready!                              ║"
echo "║                                                  ║"
echo "║  Open: http://localhost:5000                     ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Press Ctrl+C to stop Josh."
echo ""

open http://localhost:5000

# ── Keep alive — auto-restart if server crashes ───────────────────
while true; do
  sleep 5
  if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "⚠ Server crashed — restarting..."
    $GUNICORN --worker-class eventlet \
              -w 1 \
              --bind 0.0.0.0:5000 \
              --timeout 120 \
              --keep-alive 5 \
              --log-level warning \
              --access-logfile /tmp/josh_access.log \
              --error-logfile /tmp/josh_error.log \
              voice_agent:app &
    SERVER_PID=$!
    echo "✓ Restarted (PID $SERVER_PID)"
  fi
done
