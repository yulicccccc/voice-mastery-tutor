#!/bin/zsh
set -euo pipefail

service="voice-mastery-tutor-actions"
account="${USER:?USER is required}"
token="$(openssl rand -hex 32)"

security add-generic-password \
  -U \
  -a "$account" \
  -s "$service" \
  -w "$token" \
  >/dev/null

print -rn -- "$token" | pbcopy
unset token

print "已生成专用 Actions 密钥，安全保存到 macOS 钥匙串，并复制到剪贴板。"
print "密钥不会显示在终端。请只粘贴到私人 GPT 的 Action Authentication 中。"
