# -*- coding: utf-8 -*-
"""
数据导出工具模块 (Data Export Utilities Module)

此模块提供了将数据导出为CSV和XLSX格式的通用函数。
主要用于API端点，以流式响应的形式提供文件下载。
(This module provides utility functions for exporting data to CSV and XLSX formats.
 It's primarily intended for use in API endpoints to offer file downloads
 as streaming responses.)
"""

import csv
import io
from typing import Any, Dict, List

import openpyxl  # For XLSX export
from fastapi.responses import StreamingResponse


def data_to_csv(
    data_list: List[Dict[str, Any]], headers: List[str], filename: str = "export.csv"
) -> StreamingResponse:
    """
    将字典列表数据转换为CSV格式并通过StreamingResponse提供下载。
    (Converts a list of dictionaries to CSV format and provides it for download via StreamingResponse.)

    参数 (Args):
        data_list (List[Dict[str, Any]]): 要导出的数据，每个字典代表一行，键应与headers对应。
                                         (Data to export, each dict represents a row, keys should match headers.)
        headers (List[str]): CSV文件的表头列表。
                             (List of headers for the CSV file.)
        filename (str): 下载时建议的文件名。
                        (Suggested filename for the download.)

    返回 (Returns):
        StreamingResponse: FastAPI流式响应对象，包含CSV数据。
                           (FastAPI StreamingResponse object containing the CSV data.)
    """
    output = io.StringIO()
    # 使用 utf-8-sig 编码以确保Excel正确显示中文字符 (Use utf-8-sig for Excel to correctly display Chinese chars)
    # The StreamingResponse will handle encoding, but csv.writer needs unicode.

    writer = csv.writer(output)

    # 写入表头 (Write headers)
    writer.writerow(headers)

    # 写入数据行 (Write data rows)
    if data_list:
        for item in data_list:
            writer.writerow(
                [item.get(header, "") for header in headers]
            )  # Safely get values

    # StreamingResponse需要字节流，所以我们将StringIO的内容编码为UTF-8 (with BOM for Excel)
    # The content must be bytes for StreamingResponse if we specify charset in media_type or headers
    # However, StreamingResponse can also take an iterator of strings and encode it.
    # For simplicity with csv.writer producing strings, we'll let StreamingResponse handle it.

    # Reset stream position
    output.seek(0)

    # Create a string iterator for StreamingResponse
    # This avoids loading the whole CSV into memory as one giant string if data_list is huge.
    # However, csv.writer already wrote to an in-memory StringIO buffer.
    # For very large datasets, a different approach might be needed (e.g. generating CSV row by row as an iterator).
    # Given the current structure with StringIO, we'll read its content.

    response_content = output.getvalue()
    # output.close() # StringIO doesn't need explicit close for getvalue()

    return StreamingResponse(
        iter([response_content.encode("utf-8-sig")]),  # Encode to utf-8-sig for BOM
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Encoding": "utf-8-sig",  # Explicitly state encoding for clarity, though BOM handles it
        },
    )


def data_to_xlsx(
    data_list: List[Dict[str, Any]], headers: List[str], filename: str = "export.xlsx"
) -> StreamingResponse:
    """
    将字典列表数据转换为XLSX格式并通过StreamingResponse提供下载。
    (Converts a list of dictionaries to XLSX format and provides it for download via StreamingResponse.)

    参数 (Args):
        data_list (List[Dict[str, Any]]): 要导出的数据，每个字典代表一行。
                                         (Data to export, each dict represents a row.)
        headers (List[str]): XLSX文件的表头列表。
                             (List of headers for the XLSX file.)
        filename (str): 下载时建议的文件名。
                        (Suggested filename for the download.)

    返回 (Returns):
        StreamingResponse: FastAPI流式响应对象，包含XLSX数据。
                           (FastAPI StreamingResponse object containing the XLSX data.)
    """
    workbook = openpyxl.Workbook()
    sheet = workbook.active

    # 写入表头 (Write headers)
    sheet.append(headers)

    # 写入数据行 (Write data rows)
    if data_list:
        for item in data_list:
            row_values = [item.get(header) for header in headers]  # Safely get values
            sheet.append(row_values)

    # 将工作簿保存到内存中的字节流 (Save workbook to an in-memory byte stream)
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)  # Reset stream position to the beginning

    return StreamingResponse(
        output,  # BytesIO is directly iterable by StreamingResponse
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["data_to_csv", "data_to_xlsx"]
