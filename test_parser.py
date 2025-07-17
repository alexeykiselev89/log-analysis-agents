from app.agents.log_parser import LogParser

with open('test_data/sample.log', 'r', encoding='utf-8') as f:
    log_content = f.read()

entries = LogParser.parse_log(log_content)

print("Parsed entries:")
for entry in entries:
    print(entry)

print("\nGrouped entries:")
grouped = LogParser.group_by_normalized_message(entries)
for msg, group_entries in grouped.items():
    print(f"Message: {msg}, Frequency: {len(group_entries)}")

