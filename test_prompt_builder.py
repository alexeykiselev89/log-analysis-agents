from app.agents.log_parser import LogParser
from app.agents.error_classifier import ErrorClassifier
from app.agents.prompt_builder import PromptBuilder

with open('test_data/sample.log', 'r', encoding='utf-8') as f:
    log_content = f.read()

# Парсим и классифицируем логи
entries = LogParser.parse_log(log_content)
grouped_entries = LogParser.group_by_normalized_message(entries)
classified_errors = ErrorClassifier.classify_errors(grouped_entries)

# Формируем промт
prompt = PromptBuilder.build_prompt(classified_errors)

print("Сгенерированный промт для GigaChat:\n")
print(prompt)

