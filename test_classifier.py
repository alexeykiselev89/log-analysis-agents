from app.agents.log_parser import LogParser
from app.agents.error_classifier import ErrorClassifier

with open('test_data/sample.log', 'r', encoding='utf-8') as f:
    log_content = f.read()

entries = LogParser.parse_log(log_content)
grouped_entries = LogParser.group_by_normalized_message(entries)

classified_errors = ErrorClassifier.classify_errors(grouped_entries)

print("Classified Errors:")
for err in classified_errors:
    print(f"{err.frequency} occurrences | Level: {err.level} | Criticality: {err.criticality} | Message: {err.message}")
