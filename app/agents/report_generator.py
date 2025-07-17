import pandas as pd
from typing import List
from app.agents.json_parser_validator import ProblemReport
import json
from datetime import datetime
import os

class ReportGenerator:
    @staticmethod
    def generate_json_report(problems: List[ProblemReport]) -> str:
        report = {
            "summary": f"Анализ логов от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "total_problems": len(problems),
            "problems": [problem.dict() for problem in problems]
        }
        return json.dumps(report, ensure_ascii=False, indent=4)

    @staticmethod
    def generate_csv_report(problems: List[ProblemReport], filepath: str) -> str:
        df = pd.DataFrame([problem.dict() for problem in problems])
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        return filepath

