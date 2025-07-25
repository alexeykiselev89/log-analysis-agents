from typing import Dict, List
from app.models.log_entry import LogEntry

class PromptBuilder:
    @staticmethod
    def build_prompt(grouped: Dict[str, List[LogEntry]]) -> str:
        prompt_lines = [
            "Ты выступаешь в роли AI-эксперта по анализу логов приложений.",
            "",
            "Ниже представлен список ошибок из логов информационной системы.",
            "Твоя задача — для каждой ошибки:",
            "- определить критичность (низкая / средняя / высокая),",
            "- дать краткую причину возникновения ошибки,",
            "- дать конкретную рекомендацию — что инженер должен сделать, чтобы устранить проблему.",
            "",
            "Рекомендация должна быть **конкретной инструкцией к действию**, например:",
            "- завести задачу на разработку с указанием типа ошибки,",
            "- проверить настройки конкретного сервиса,",
            "- изменить конфигурацию, пересоздать данные, исправить код и т.п.",
            "",
            "Формат ответа — строго в JSON-массиве **без пояснений**, например:",
            "[",
            "  {",
            "    \"message\": \"<оригинальное сообщение>\",",
            "    \"frequency\": <число>,",
            "    \"criticality\": \"низкая | средняя | высокая\",",
            "    \"recommendation\": \"<что конкретно сделать>\"",
            "  },",
            "  ...",
            "]",
            "",
            "Вот список ошибок:"
        ]

        for norm_msg, entries in grouped.items():
            example_entry = entries[0]
            original = example_entry.message.strip()
            frequency = len(entries)
            class_name = example_entry.class_name
            level = example_entry.level

            if not original or original.lower() == "произошла ошибка":
                continue  # игнорируем бесполезные строки

            prompt_lines.append(
                f"- ({level}) {original}  [class: {class_name}, count: {frequency}]"
            )

        return "\n".join(prompt_lines)
