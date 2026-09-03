#!/usr/bin/env bash
echo '=== dmesg java/signal records ==='
dmesg 2>/dev/null | grep -iE 'java|YarnChild|abort|segfault|fatal' | tail -40
echo '=== dmesg recent ==='
dmesg 2>/dev/null | tail -15
