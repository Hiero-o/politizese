
import json
import math
import uuid

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_METRICS_DIR = (
    PROJECT_ROOT
    / "data"
    / "metrics"
    / "semantic_index"
)


class SemanticIndexMetrics:
    """
    Coleta métricas de chamadas ao LLM, seções e execuções.

    Os registros são gravados imediatamente em JSONL.
    Isso permite preservar os dados mesmo quando uma execução
    é interrompida antes de sua conclusão.
    """

    def __init__(
        self,
        metrics_dir: Path = DEFAULT_METRICS_DIR,
    ) -> None:

        self.metrics_dir = Path(metrics_dir)

        self.metrics_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.run_id = uuid.uuid4().hex

        self.calls_path = self.metrics_dir / "llm_calls.jsonl"
        self.sections_path = self.metrics_dir / "sections.jsonl"
        self.runs_path = self.metrics_dir / "runs.jsonl"

        self.started_at = datetime.now(
            timezone.utc
        ).isoformat()

        self.started_perf = perf_counter()

        self.calls: list[dict[str, Any]] = []
        self.sections: list[dict[str, Any]] = []

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _append_jsonl(
        path: Path,
        record: dict[str, Any],
    ) -> None:

        with path.open(
            "a",
            encoding="utf-8",
        ) as file:

            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )

            file.flush()

    @staticmethod
    def _number(value: Any) -> float | None:

        if isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            return float(value)

        return None

    @staticmethod
    def _nanoseconds_to_seconds(
        value: Any,
    ) -> float | None:

        number = SemanticIndexMetrics._number(value)

        if number is None:
            return None

        return number / 1_000_000_000

    @staticmethod
    def _tokens_per_second(
        tokens: Any,
        duration_seconds: float | None,
    ) -> float | None:

        token_count = SemanticIndexMetrics._number(tokens)

        if (
            token_count is None
            or duration_seconds is None
            or duration_seconds <= 0
        ):
            return None

        return token_count / duration_seconds

    def record_llm_call(
        self,
        *,
        operation: str,
        context: dict[str, Any],
        raw_response: Any = None,
        error: Exception | None = None,
        wall_time_seconds: float,
        prompt_characters: int,
    ) -> None:
        """
        Registra uma chamada ao modelo.

        raw_response deve ser a mensagem AIMessage original
        retornada pelo ChatOllama, antes da conversão Pydantic.
        """

        metadata = (
            getattr(raw_response, "response_metadata", None)
            or {}
        )

        usage = (
            getattr(raw_response, "usage_metadata", None)
            or {}
        )

        prompt_tokens = metadata.get(
            "prompt_eval_count",
            usage.get("input_tokens"),
        )

        output_tokens = metadata.get(
            "eval_count",
            usage.get("output_tokens"),
        )

        total_tokens = usage.get("total_tokens")

        if (
            total_tokens is None
            and prompt_tokens is not None
            and output_tokens is not None
        ):
            total_tokens = (
                prompt_tokens + output_tokens
            )

        load_seconds = self._nanoseconds_to_seconds(
            metadata.get("load_duration")
        )

        prompt_eval_seconds = self._nanoseconds_to_seconds(
            metadata.get("prompt_eval_duration")
        )

        generation_seconds = self._nanoseconds_to_seconds(
            metadata.get("eval_duration")
        )

        ollama_total_seconds = self._nanoseconds_to_seconds(
            metadata.get("total_duration")
        )

        response_content = getattr(
            raw_response,
            "content",
            None,
        )

        response_characters = (
            len(str(response_content))
            if response_content is not None
            else None
        )

        record = {
            "event_type": "llm_call",
            "run_id": self.run_id,
            "timestamp": self._timestamp(),

            "operation": operation,
            "context": context,

            "status": "error" if error else "success",

            "model": metadata.get("model"),
            "done_reason": metadata.get("done_reason"),

            "wall_time_seconds": round(
                wall_time_seconds,
                6,
            ),

            "ollama_total_duration_seconds": ollama_total_seconds,
            "model_load_seconds": load_seconds,
            "prompt_eval_seconds": prompt_eval_seconds,
            "generation_seconds": generation_seconds,

            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,

            "prompt_tokens_per_second": self._tokens_per_second(
                prompt_tokens,
                prompt_eval_seconds,
            ),

            "generation_tokens_per_second": self._tokens_per_second(
                output_tokens,
                generation_seconds,
            ),

            "prompt_characters": prompt_characters,
            "response_characters": response_characters,

            "error_type": (
                type(error).__name__
                if error else None
            ),

            "error_message": (
                str(error)[:2000]
                if error else None
            ),
        }

        self.calls.append(record)

        self._append_jsonl(
            self.calls_path,
            record,
        )

    def record_section(
        self,
        *,
        section_id: str,
        status: str,
        elapsed_seconds: float,
        unit_count: int,
        error: Exception | None = None,
    ) -> None:
        """Registra o tempo total de processamento de uma seção."""

        record = {
            "event_type": "section",
            "run_id": self.run_id,
            "timestamp": self._timestamp(),

            "section_id": section_id,
            "status": status,

            "elapsed_seconds": round(
                elapsed_seconds,
                6,
            ),

            "unit_count": unit_count,

            "error_type": (
                type(error).__name__
                if error else None
            ),

            "error_message": (
                str(error)[:2000]
                if error else None
            ),
        }

        self.sections.append(record)

        self._append_jsonl(
            self.sections_path,
            record,
        )

    @staticmethod
    def _percentile(
        values: list[float],
        percentile: float,
    ) -> float | None:

        if not values:
            return None

        ordered = sorted(values)

        index = max(
            0,
            math.ceil(percentile * len(ordered)) - 1,
        )

        return ordered[index]

    def finish(
        self,
        *,
        status: str,
        document_id: str,
        sections_total: int,
        sections_processed: int,
        sections_reused: int,
        failures: int,
        model_provider: str,
        model_name: str,
    ) -> dict[str, Any]:
        """Calcula e persiste o resumo da execução."""

        elapsed = perf_counter() - self.started_perf

        successful_calls = [
            call
            for call in self.calls
            if call["status"] == "success"
        ]

        failed_calls = [
            call
            for call in self.calls
            if call["status"] == "error"
        ]

        wall_times = [
            call["wall_time_seconds"]
            for call in self.calls
        ]

        prompt_tokens = [
            call["prompt_tokens"]
            for call in self.calls
            if isinstance(call["prompt_tokens"], (int, float))
        ]

        output_tokens = [
            call["output_tokens"]
            for call in self.calls
            if isinstance(call["output_tokens"], (int, float))
        ]

        generation_times = [
            call["generation_seconds"]
            for call in self.calls
            if isinstance(call["generation_seconds"], (int, float))
        ]

        prompt_times = [
            call["prompt_eval_seconds"]
            for call in self.calls
            if isinstance(call["prompt_eval_seconds"], (int, float))
        ]

        load_times = [
            call["model_load_seconds"]
            for call in self.calls
            if isinstance(call["model_load_seconds"], (int, float))
        ]

        total_prompt_tokens = sum(prompt_tokens)
        total_output_tokens = sum(output_tokens)

        total_generation_seconds = sum(generation_times)
        total_prompt_seconds = sum(prompt_times)

        summary = {
            "event_type": "run_summary",
            "run_id": self.run_id,

            "started_at": self.started_at,
            "finished_at": self._timestamp(),

            "status": status,

            "document_id": document_id,
            "model_provider": model_provider,
            "model_name": model_name,

            "sections_total": sections_total,
            "sections_processed": sections_processed,
            "sections_reused": sections_reused,
            "sections_failed": failures,

            "llm_calls_total": len(self.calls),
            "llm_calls_successful": len(successful_calls),
            "llm_calls_failed": len(failed_calls),

            "total_elapsed_seconds": round(elapsed, 3),

            "average_call_latency_seconds": (
                round(sum(wall_times) / len(wall_times), 3)
                if wall_times else None
            ),

            "median_call_latency_seconds": (
                self._percentile(wall_times, 0.50)
            ),

            "p95_call_latency_seconds": (
                self._percentile(wall_times, 0.95)
            ),

            "total_prompt_tokens": total_prompt_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": (
                total_prompt_tokens + total_output_tokens
            ),

            "total_model_load_seconds": round(
                sum(load_times),
                3,
            ),

            "prompt_tokens_per_second": self._tokens_per_second(
                total_prompt_tokens,
                total_prompt_seconds,
            ),

            "generation_tokens_per_second": self._tokens_per_second(
                total_output_tokens,
                total_generation_seconds,
            ),

            "sections_per_minute": (
                sections_processed / (elapsed / 60)
                if elapsed > 0 else None
            ),
        }

        self._append_jsonl(
            self.runs_path,
            summary,
        )

        return summary
