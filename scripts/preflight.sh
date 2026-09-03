#!/usr/bin/env bash
#
# Run this on a fresh VPS BEFORE setting anything up.
#
#     bash <(curl -fsSL https://raw.githubusercontent.com/shishkins/gym_assistant/main/scripts/preflight.sh)
#
# Checks the three things that are expensive to discover late: whether the
# CPU can actually run modern Python wheels, whether the machine has the
# resources that were paid for, and where it is.
#
# Written after a provider handed us a VM with a generic QEMU CPU - no
# SSE4.2, no POPCNT - on which NumPy refuses to import at all, and therefore
# the bot could not start. Everything else had already been set up by then.
set -uo pipefail

fail=0
warn=0

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail + 1)); }
soft() { printf '  \033[33m!\033[0m %s\n' "$1"; warn=$((warn + 1)); }

echo
echo "=== Процессор ==="
echo "  $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //')"
echo "  ядер: $(nproc)"
echo

# x86-64-v2 is the baseline NumPy 2.x is built for. Every physical CPU since
# about 2009 has it; a VM missing it means the host is masking the flags.
for flag in popcnt ssse3 sse4_1 sse4_2; do
    if grep -qm1 " $flag" /proc/cpuinfo; then
        ok "$flag"
    else
        bad "$flag — нет. NumPy 2.x не импортируется, бот не стартует"
    fi
done

# Not needed today; needed by faster-whisper in iteration 6.
if grep -qm1 ' avx2' /proc/cpuinfo; then
    ok "avx2 — голосовой ввод потянет"
else
    soft "avx2 — нет. Локальное распознавание речи будет очень медленным или не заведётся"
fi

echo
echo "=== Ресурсы ==="
mem_mb=$(($(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024))
disk_gb=$(df -BG --output=size / | tail -1 | tr -dc '0-9')
echo "  память: ${mem_mb} МБ"
echo "  диск:   ${disk_gb} ГБ"
[ "$mem_mb" -ge 3500 ] || bad "мало памяти для итерации 6 (нужно от 4 ГБ)"
[ "$disk_gb" -ge 20 ] || bad "мало места на диске"
echo "  Сверьте с тем, за что заплачено."

echo
echo "=== Расположение ==="
country=$(curl -s --max-time 10 https://ipinfo.io/country 2>/dev/null | tr -d '\r\n')
if [ -z "$country" ]; then
    soft "не удалось определить (нет сети или ipinfo недоступен)"
elif [ "$country" = "RU" ]; then
    bad "RU — Anthropic API отсюда не работает, итерация 5 невозможна"
else
    ok "$country"
fi

echo
if [ "$fail" -gt 0 ]; then
    echo "ИТОГ: $fail блокирующих проблем. Этот сервер не подходит — верните его."
    exit 1
fi
if [ "$warn" -gt 0 ]; then
    echo "ИТОГ: годится, но с оговорками ($warn)."
    exit 0
fi
echo "ИТОГ: всё в порядке, можно разворачивать."
