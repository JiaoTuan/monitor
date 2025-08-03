echo 0 > /sys/kernel/tracing/tracing_on
echo 0 > /sys/kernel/tracing/events/enable

echo 8192 > /sys/kernel/tracing/buffer_size_kb
echo 1 > /sys/kernel/tracing/events/block/block_rq_issue/enable
echo 1 > /sys/kernel/tracing/events/block/block_rq_complete/enable

echo 1 > /sys/kernel/tracing/tracing_on

pasue

echo 0 > /sys/kernel/tracing/tracing_on
cat /sys/kernel/tracing/trace > .