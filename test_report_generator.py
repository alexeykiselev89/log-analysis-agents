import asyncio
from app.agents.log_parser import LogParser
from app.agents.error_classifier import ErrorClassifier
from app.agents.prompt_builder import PromptBuilder
from app.agents.gigachat_client import GigaChatClient
from app.agents.json_parser_validator import JSONParserValidator
from app.agents.report_generator import ReportGenerator

async def main():
    with open('test_data/sample.log', 'r', encoding='utf-8') as f:
        log_content = f.read()

    entries = LogParser.parse_log(log_content)
    grouped_entries = LogParser.group_by_normalized_message(entries)
    classified_errors = ErrorClassifier.classify_errors(grouped_entries)

    prompt = PromptBuilder.build_prompt(classified_errors)

    gigachat = GigaChatClient()
    response = await gigachat.get_completion(prompt)

    validated_report = JSONParserValidator.parse_and_validate(response)

    json_report = ReportGenerator.generate_json_report(validated_report)
    print("JSON-отчёт:\n", json_report)

    csv_filepath = 'reports/problems_report.csv'
    ReportGenerator.generate_csv_report(validated_report, csv_filepath)
    print(f"\nCSV-отчёт сохранён по пути: {csv_filepath}")

if __name__ == "__main__":
    asyncio.run(main())
