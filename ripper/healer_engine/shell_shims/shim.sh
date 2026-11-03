#!/usr/bin/env bash
# Autonomous Self-Healing CLI Shim for Bash / Zsh
# Hooks PROMPT_COMMAND / precmd to detect failures and alert the healer bus.

ripper_postexec_hook() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo -e "\033[33m[Autonomous Healer] Command failed ($exit_code). Alerting background bus...\033[0m"
        local pipe="/tmp/ripper_watchdog.sock"
        if [ -S "$pipe" ]; then
            local payload="{\"timestamp\":\"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\",\"source\":\"Bash_Shim\",\"level\":\"ERROR\",\"message\":\"Command exited with code $exit_code\"}"
            echo "$payload" | nc -U -w 1 "$pipe" >/dev/null 2>&1 || true
        fi
    fi
}

if [ -n "$BASH_VERSION" ]; then
    PROMPT_COMMAND="ripper_postexec_hook; $PROMPT_COMMAND"
elif [ -n "$ZSH_VERSION" ]; then
    autoload -Uz add-zsh-hook
    add-zsh-hook precmd ripper_postexec_hook
fi
