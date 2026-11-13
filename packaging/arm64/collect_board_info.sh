#!/bin/sh
set -eu

print_section()
{
    printf '\n===== %s =====\n' "$1"
}

print_section "时间与主机"
date '+local_time=%Y-%m-%d %H:%M:%S %z'
date -u '+utc_time=%Y-%m-%dT%H:%M:%SZ'
uname -a
uname -m
hostname

print_section "开发板型号"
if [ -r /proc/device-tree/model ]; then
    tr -d '\000' < /proc/device-tree/model
    printf '\n'
else
    echo "device_tree_model=unavailable"
fi

print_section "操作系统"
if [ -r /etc/os-release ]; then
    cat /etc/os-release
else
    echo "os_release=unavailable"
fi

print_section "CPU"
if command -v lscpu >/dev/null 2>&1; then
    lscpu
else
    cat /proc/cpuinfo
fi

print_section "内存"
free -h

print_section "存储"
df -h .

print_section "CPU 频率策略"
for cpu_dir in /sys/devices/system/cpu/cpu[0-9]*; do
    cpu_name=${cpu_dir##*/}
    governor_file="$cpu_dir/cpufreq/scaling_governor"
    min_file="$cpu_dir/cpufreq/scaling_min_freq"
    max_file="$cpu_dir/cpufreq/scaling_max_freq"
    cur_file="$cpu_dir/cpufreq/scaling_cur_freq"
    printf '%s' "$cpu_name"
    for field in "$governor_file" "$min_file" "$max_file" "$cur_file"; do
        if [ -r "$field" ]; then
            printf ' %s=%s' "${field##*/}" "$(cat "$field")"
        fi
    done
    printf '\n'
done

print_section "温度"
found_thermal=0
for zone_dir in /sys/class/thermal/thermal_zone*; do
    [ -d "$zone_dir" ] || continue
    found_thermal=1
    zone_name=${zone_dir##*/}
    zone_type=unavailable
    zone_temp=unavailable
    if [ -r "$zone_dir/type" ]; then
        zone_type=$(cat "$zone_dir/type")
    fi
    if [ -r "$zone_dir/temp" ]; then
        zone_temp=$(cat "$zone_dir/temp")
    fi
    printf '%s type=%s temp_millidegree_c=%s\n' \
        "$zone_name" "$zone_type" "$zone_temp"
done
if [ "$found_thermal" -eq 0 ]; then
    echo "thermal_zone=unavailable"
fi

print_section "网络接口"
if command -v ip >/dev/null 2>&1; then
    ip -brief address
else
    echo "ip_command=unavailable"
fi
