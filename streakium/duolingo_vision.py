from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess

from streakium.runtime_paths import get_duolingo_model_dir

VISION_INPUT_SIZE = 48
VISION_CONFIDENCE_THRESHOLD = 0.65
VISION_LABELS = [
    "empty",
    "white_pawn",
    "white_knight",
    "white_bishop",
    "white_rook",
    "white_queen",
    "white_king",
    "black_pawn",
    "black_knight",
    "black_bishop",
    "black_rook",
    "black_queen",
    "black_king",
]
VISION_LABEL_TO_SYMBOL = {
    "white_pawn": "P",
    "white_knight": "N",
    "white_bishop": "B",
    "white_rook": "R",
    "white_queen": "Q",
    "white_king": "K",
    "black_pawn": "p",
    "black_knight": "n",
    "black_bishop": "b",
    "black_rook": "r",
    "black_queen": "q",
    "black_king": "k",
}


class VisionModelUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class VisionPrediction:
    piece_map: dict[str, str]


class DuolingoVisionModel:
    def __init__(self, model_dir: Path | str | None = None):
        self.model_dir = Path(model_dir) if model_dir is not None else get_duolingo_model_dir()
        self.model_path = self.model_dir / "duolingo_chess.tflite"
        self.labels_path = self.model_dir / "labels.json"
        if not self.model_path.exists():
            raise VisionModelUnavailable(f"Duolingo vision model was not found: {self.model_path}")
        self.labels = load_labels(self.labels_path)
        if self.labels != VISION_LABELS:
            raise VisionModelUnavailable("Duolingo vision labels do not match the expected order.")
        try:
            import numpy as np
            from tflite_runtime.interpreter import Interpreter
        except Exception as exc:
            raise VisionModelUnavailable(
                "tflite_runtime is not installed. Install python-tflite-runtime in Termux."
            ) from exc
        self.np = np
        self.interpreter = Interpreter(model_path=str(self.model_path), num_threads=2)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()[0]
        self.output_details = self.interpreter.get_output_details()[0]
        self._validate_input()

    def _validate_input(self) -> None:
        shape = list(self.input_details.get("shape", []))
        if len(shape) != 4 or shape[1] != VISION_INPUT_SIZE or shape[2] != VISION_INPUT_SIZE or shape[3] != 3:
            raise VisionModelUnavailable(f"Unexpected Duolingo vision input shape: {shape}")

    def predict(
        self,
        payload: dict[str, Any],
        threshold: float = VISION_CONFIDENCE_THRESHOLD,
    ) -> VisionPrediction | None:
        squares, batch = decode_tile_payload(payload, self.np)
        if not squares or batch.shape[0] != 64:
            return None
        input_dtype = self.input_details["dtype"]
        if input_dtype == self.np.float32:
            model_input = batch.astype(self.np.float32) / 255.0
        else:
            model_input = batch.astype(input_dtype)
        if tuple(self.input_details["shape"]) != tuple(model_input.shape):
            self.interpreter.resize_tensor_input(
                self.input_details["index"],
                model_input.shape,
                strict=False,
            )
            self.interpreter.allocate_tensors()
            self.input_details = self.interpreter.get_input_details()[0]
            self.output_details = self.interpreter.get_output_details()[0]
        self.interpreter.set_tensor(self.input_details["index"], model_input)
        self.interpreter.invoke()
        probabilities = self.interpreter.get_tensor(self.output_details["index"])
        if probabilities.dtype != self.np.float32:
            scale, zero_point = self.output_details.get("quantization", (0.0, 0))
            if scale:
                probabilities = (probabilities.astype(self.np.float32) - float(zero_point)) * float(scale)
            else:
                probabilities = probabilities.astype(self.np.float32)
        if probabilities.ndim != 2 or probabilities.shape[1] != len(self.labels):
            return None
        label_indexes = probabilities.argmax(axis=1)
        confidences = probabilities.max(axis=1)
        labels = [self.labels[int(index)] for index in label_indexes]
        confidence_values = [float(value) for value in confidences.tolist()]
        return VisionPrediction(
            piece_map=labels_to_piece_map(labels, confidence_values, squares, threshold),
        )


def load_labels(path: Path) -> list[str]:
    if not path.exists():
        return VISION_LABELS[:]
    value = json.loads(path.read_text())
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise VisionModelUnavailable(f"Invalid Duolingo vision labels file: {path}")
    return value


def load_vision_model(model_dir: Path | str | None = None) -> DuolingoVisionModel | None:
    try:
        return DuolingoVisionModel(model_dir)
    except VisionModelUnavailable:
        return None


def labels_to_piece_map(
    labels: list[str],
    confidences: list[float],
    squares: list[str],
    threshold: float = VISION_CONFIDENCE_THRESHOLD,
) -> dict[str, str]:
    result = {}
    for square, label, confidence in zip(squares, labels, confidences):
        if square not in chess.SQUARE_NAMES:
            continue
        if label == "empty" or confidence < threshold:
            continue
        symbol = VISION_LABEL_TO_SYMBOL.get(label)
        if symbol:
            result[square] = symbol
    return result


def decode_tile_payload(payload: dict[str, Any], np: Any) -> tuple[list[str], Any]:
    if not isinstance(payload, dict):
        return [], np.empty((0, VISION_INPUT_SIZE, VISION_INPUT_SIZE, 3), dtype=np.uint8)
    squares = payload.get("squares")
    packed_tiles = payload.get("packedTiles")
    if isinstance(squares, list) and isinstance(packed_tiles, str) and len(squares) == 64:
        raw = base64.b64decode(packed_tiles)
        expected = 64 * VISION_INPUT_SIZE * VISION_INPUT_SIZE * 3
        if len(raw) != expected:
            return [], np.empty((0, VISION_INPUT_SIZE, VISION_INPUT_SIZE, 3), dtype=np.uint8)
        batch = np.frombuffer(raw, dtype=np.uint8).reshape(
            (64, VISION_INPUT_SIZE, VISION_INPUT_SIZE, 3)
        )
        return [str(square) for square in squares], batch
    return [], np.empty((0, VISION_INPUT_SIZE, VISION_INPUT_SIZE, 3), dtype=np.uint8)
