"""
Stage 1 — 업로드 검증기 (플랫폼 공통).

파일 업로드 시 도메인 처리 이전에 기본적인 파일 유효성을 검사합니다.
모든 검증기는 상태를 갖지 않으며 도메인에 무관합니다.

포함 검증기:
  - FileTypeValidator     : 허용 확장자 검사 (csv, xlsx, json 등)
  - FileSizeValidator     : 파일 크기 상한 검사
  - EmptyFileValidator    : 빈 파일 검출
  - DuplicateFileValidator: 동일 파일명 중복 업로드 검출

기대하는 context 키:
    files: list[dict]  — 각 dict에 'filename', 'path', 'size' 포함
    project_id: str
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from engine.validation.base import AutoFix, BaseValidator, ValidationResult


class EmptyFileValidator(BaseValidator):
    """Detects zero-byte or effectively empty files."""

    stage = 1
    name = "EmptyFileValidator"
    description = "빈 파일(0 byte) 감지"

    # Threshold: files smaller than this (bytes) are considered empty
    MIN_MEANINGFUL_SIZE = 10

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()
        files: list[dict] = context.get("files", [])

        for f in files:
            size = f.get("size", 0)
            filename = f.get("filename", "unknown")

            if size == 0:
                result.add_error(
                    code="UPLOAD_EMPTY_FILE",
                    message=f"'{filename}' 파일이 비어 있습니다 (0 byte).",
                    suggestion="파일 내용을 확인한 후 다시 업로드해 주세요.",
                    context={"filename": filename, "size": size},
                )
            elif size < self.MIN_MEANINGFUL_SIZE:
                result.add_warning(
                    code="UPLOAD_NEAR_EMPTY_FILE",
                    message=f"'{filename}' 파일이 매우 작습니다 ({size} bytes).",
                    suggestion="파일 내용이 올바른지 확인해 주세요.",
                    context={"filename": filename, "size": size},
                )

        return result


class DuplicateFileValidator(BaseValidator):
    """Detects duplicate filenames in a single upload batch."""

    stage = 1
    name = "DuplicateFileValidator"
    description = "중복 파일명 감지"

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()
        files: list[dict] = context.get("files", [])

        name_counts = Counter(f.get("filename", "") for f in files)

        for name, count in name_counts.items():
            if count > 1:
                result.add_warning(
                    code="UPLOAD_DUPLICATE_FILENAME",
                    message=f"'{name}' 파일이 {count}번 중복 업로드되었습니다.",
                    suggestion="동일한 파일을 여러 번 업로드한 것은 아닌지 확인해 주세요.",
                    auto_fix=AutoFix(
                        param="duplicate_file",
                        old_val=name,
                        new_val=None,
                        action="remove",
                        label=f"중복 '{name}' 제거",
                    ),
                    context={"filename": name, "count": count},
                )

        return result


class FileTypeValidator(BaseValidator):
    """Validates that uploaded file types are analysis-compatible.

    Checks beyond the basic extension whitelist (which is in the upload endpoint).
    Warns about file types that upload succeeds but analysis may not support well.
    """

    stage = 1
    name = "FileTypeValidator"
    description = "파일 유형 분석 호환성 검증"

    # Fully supported for tabular analysis
    TABULAR_EXTENSIONS = {".csv", ".xlsx", ".xls", ".tsv", ".json"}

    # Supported but require text extraction (no tabular analysis)
    TEXT_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".doc", ".hwp", ".hwpx"}

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()
        files: list[dict] = context.get("files", [])

        tabular_count = 0
        text_count = 0

        for f in files:
            filename = f.get("filename", "unknown")
            ext = Path(filename).suffix.lower()

            if ext in self.TABULAR_EXTENSIONS:
                tabular_count += 1
            elif ext in self.TEXT_EXTENSIONS:
                text_count += 1
                result.add_info(
                    code="UPLOAD_TEXT_FILE",
                    message=f"'{filename}'은 텍스트 파일입니다. 제약조건 추출에 활용됩니다.",
                    context={"filename": filename, "ext": ext},
                )

        if tabular_count == 0 and text_count > 0:
            result.add_warning(
                code="UPLOAD_NO_TABULAR_DATA",
                message="테이블형 데이터 파일(CSV, Excel 등)이 없습니다.",
                suggestion="최적화 분석을 위해 데이터 파일을 추가로 업로드해 주세요.",
            )

        if tabular_count == 0 and text_count == 0 and len(files) > 0:
            result.add_error(
                code="UPLOAD_NO_ANALYZABLE_FILES",
                message="분석 가능한 파일이 없습니다.",
                suggestion="CSV, Excel, 또는 텍스트 파일을 업로드해 주세요.",
            )

        return result


class FileSizeValidator(BaseValidator):
    """Warns about unusually large files that may slow analysis."""

    stage = 1
    name = "FileSizeValidator"
    description = "파일 크기 경고"

    # Threshold for warning (10 MB)
    WARN_SIZE_BYTES = 10 * 1024 * 1024

    def validate(self, context: dict) -> ValidationResult:
        result = self._make_result()
        files: list[dict] = context.get("files", [])

        total_size = 0
        for f in files:
            size = f.get("size", 0)
            filename = f.get("filename", "unknown")
            total_size += size

            if size > self.WARN_SIZE_BYTES:
                mb = round(size / (1024 * 1024), 1)
                result.add_warning(
                    code="UPLOAD_LARGE_FILE",
                    message=f"'{filename}' 파일이 {mb}MB로 큽니다. 분석 시간이 길어질 수 있습니다.",
                    context={"filename": filename, "size": size, "size_mb": mb},
                )

        if total_size > self.WARN_SIZE_BYTES * 5:
            total_mb = round(total_size / (1024 * 1024), 1)
            result.add_info(
                code="UPLOAD_TOTAL_SIZE_LARGE",
                message=f"전체 업로드 크기가 {total_mb}MB입니다.",
                context={"total_size": total_size, "total_size_mb": total_mb},
            )

        return result
