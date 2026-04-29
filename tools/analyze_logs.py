#!/usr/bin/env python3
import sys
import re
from datetime import datetime
from typing import List, Dict, Tuple

def parse_log_line(line: str) -> Tuple[datetime, Dict[str, str]]:
    """Parse log line, return timestamp and metrics dict"""
    # Extract timestamp, support multiple formats
    timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})([+-]\d{2}:\d{2})', line)
    if not timestamp_match:
        return None, {}

    # Handle date/time and timezone separately
    timestamp_str = timestamp_match.group(1)
    timezone_str = timestamp_match.group(2)

    # Parse date/time part
    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')

    # Extract metrics
    metrics = {}
    for metric in ['CpuCostNs', 'ScanBytes', 'MemCostBytes', 'QueryFEAllocatedMemory']:
        match = re.search(f'\\|{metric}=([^|]+)', line)
        if match:
            metrics[metric] = match.group(1)
        else:
            # If metric not found, set to 0
            metrics[metric] = '0'

    return timestamp, metrics

def process_file(filename: str, start_time: datetime, end_time: datetime) -> List[Tuple[Dict[str, int], str]]:
    """Process single log file, return matching log entries"""
    log_entries = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                timestamp, metrics = parse_log_line(line)
                if not timestamp:
                    continue

                # Check time range
                if start_time <= timestamp <= end_time:
                    # Convert metrics to integers for sorting
                    try:
                        metrics['CpuCostNs'] = int(metrics['CpuCostNs'])
                        metrics['ScanBytes'] = int(metrics['ScanBytes'])
                        metrics['MemCostBytes'] = int(metrics['MemCostBytes'])
                        log_entries.append((metrics, line.strip()))
                    except (ValueError, KeyError):
                        continue
    except FileNotFoundError:
        print(f"Error: File {filename} not found")
    except Exception as e:
        print(f"Error processing file {filename}: {str(e)}")

    return log_entries

def get_sort_key(metrics: Dict[str, int], sort_fields: List[str]) -> Tuple:
    """Generate sort key based on specified fields"""
    return tuple(-int(metrics.get(field, 0)) for field in sort_fields)

def main():
    if len(sys.argv) < 6:
        print("Usage: python3 analyze_logs.py <start_time> <end_time> <sort_fields> <top_n> <log_file1> [log_file2 ...]")
        print("Example: python3 analyze_logs.py '2025-04-15 00:00:00' '2025-04-15 01:00:00' 'CpuCostNs,ScanBytes,MemCostBytes' 3 fe.audit.log")
        print("Available sort fields: CpuCostNs, ScanBytes, MemCostBytes, QueryFEAllocatedMemory")
        sys.exit(1)

    start_time = datetime.strptime(sys.argv[1], '%Y-%m-%d %H:%M:%S')
    end_time = datetime.strptime(sys.argv[2], '%Y-%m-%d %H:%M:%S')
    sort_fields = [field.strip() for field in sys.argv[3].split(',')]

    try:
        top_n = int(sys.argv[4])
        if top_n <= 0:
            raise ValueError("top_n must be positive")
    except ValueError as e:
        print(f"Error: top_n must be positive integer: {e}")
        sys.exit(1)

    log_files = sys.argv[5:]

    # Validate sort fields
    valid_fields = {'CpuCostNs', 'ScanBytes', 'MemCostBytes', 'QueryFEAllocatedMemory'}
    invalid_fields = set(sort_fields) - valid_fields
    if invalid_fields:
        print(f"Error: Invalid sort fields: {', '.join(invalid_fields)}")
        print("Available sort fields: CpuCostNs, ScanBytes, MemCostBytes, QueryFEAllocatedMemory")
        sys.exit(1)

    # Store all log entries
    all_entries = []

    # Process each log file
    for log_file in log_files:
        entries = process_file(log_file, start_time, end_time)
        all_entries.extend(entries)

    # Sort by specified metrics
    sorted_entries = sorted(
        all_entries,
        key=lambda x: get_sort_key(x[0], sort_fields)
    )

    # Output top N records
    print(f"\nBetween {start_time} and {end_time}, sorted by {', '.join(sort_fields)}, top {top_n} records:")
    for i, (metrics, line) in enumerate(sorted_entries[:top_n], 1):
        print(f"\nRecord {i}:")
        print(f"Metrics: {', '.join(f'{field}={metrics[field]}' for field in sort_fields)}")
        print(line)

if __name__ == '__main__':
    main()