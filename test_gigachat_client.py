import asyncio
from app.agents.log_parser import LogParser
from app.agents.error_classifier import ErrorClassifier
from app.agents.prompt_builder import PromptBuilder
from app.agents.gigachat_client import GigaChatClient

async def main():
    with open('test_data/sample.log', 'r', encoding='utf-8') as f:
        log_content = f.read()

    # Парсим и классифицируем логи
    entries = LogParser.parse_log(log_content)
    grouped_entries = LogParser.group_by_normalized_message(entries)
    classified_errors = ErrorClassifier.classify_errors(grouped_entries)

    # Формируем промт
    prompt = PromptBuilder.build_prompt(classified_errors)

    # Запрос к GigaChat
    gigachat = GigaChatClient()
    response = await gigachat.get_completion(prompt)

    print("Ответ от GigaChat:\n")
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
