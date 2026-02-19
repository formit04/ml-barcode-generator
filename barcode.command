#!/bin/zsh
set -e

PROJECT_DIR="/Users/marcinformela/claude_project/barcode"
SESSION_NAME="barcode"

cd "$PROJECT_DIR"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux attach-session -t "$SESSION_NAME"
else
    tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_DIR"
    tmux send-keys -t "$SESSION_NAME" "claude --dangerously-skip-permissions" Enter
    tmux attach-session -t "$SESSION_NAME"
fi
