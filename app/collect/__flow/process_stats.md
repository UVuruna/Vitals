# Process Stats — Flow

**About:** [description](../__about/process_stats.md)

## One tick: extract → history → rolling average

```mermaid
flowchart TB
    A[collector calls _extract_cpu_top or _extract_mem_top] --> B{mode?}
    B -- CPU --> C{_first_cpu_tick?}
    C -- yes --> D[total_usage = 0.0 — no prev-tick delta yet, total_cpu is bogus — clear the flag]
    C -- no --> E[total_usage = total_cpu; append now,total_cpu to peak buffer; drop entries past retention cutoff]
    B -- Memory --> F[total_usage = psutil virtual_memory.used; append to peak buffer; drop entries past cutoff]
    D --> G[heapq.nlargest by CPU_IDX or RSS_IDX -> top-N ProcessInfo list]
    E --> G
    F --> G
    G --> H[collector calls update_history all_processes]
    H --> I{name already recorded?}
    I -- yes, current value higher --> J[replace the record]
    I -- no, history has room --> K[add a new record]
    I -- no room --> L{beats the lowest current record?}
    L -- yes --> M[evict the lowest, add the new one]
    L -- no --> N[dropped — not in the top history_max_size]
    G --> O[collector calls update_rolling_average aggregated]
    O --> P[RollingWindow.add — see Rolling Window flow]
```

Pseudocode (language-neutral):

    FUNCTION extract_top(aggregated, total, limit):
        IF mode == CPU AND this is the first tick since CPU mode was enabled:
            total_usage = 0                        // total_cpu has no previous-tick baseline yet — discard it
            clear the first-tick flag
        ELSE:
            total_usage = total
            append (now, total) to the peak buffer
            drop peak-buffer entries older than retention_seconds

        top = the `limit` highest-ranked entries from aggregated
              (ranked by CPU_IDX for CPU mode, RSS_IDX for Memory mode)
        RETURN top as ProcessInfo records

    FUNCTION update_history(processes):
        drop history records older than retention_seconds
        FOR EACH process IN processes WHERE value > 0:
            IF process.name already in history:
                IF process.value > recorded value -> overwrite the record
            ELSE IF history has room (< history_max_size):
                add a new record
            ELSE:
                find the lowest-value record currently held
                IF process.value beats it -> evict it, add the new record

    FUNCTION update_rolling_average(aggregated):
        build a per-name snapshot (CPU: cpu%, threads, count, 0 —
                                    Memory: rss, 0, count, vms)
        RollingWindow.add(now, snapshot)

The `_first_cpu_tick` guard exists because `total_cpu` on the very first
bulk-collect tick is `cpu_threads * 100 - 0` — no previous tick means no CPU
delta, so the Idle-process math in
[System Query](../__about/system_query.md) produces a value that looks like
100% total CPU on every core. Skipping ONE tick's total (not the whole
extract) avoids a false peak-history entry without discarding the process
list itself.
