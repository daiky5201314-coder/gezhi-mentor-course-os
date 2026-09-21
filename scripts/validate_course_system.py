#!/usr/bin/env python3
"""Lightweight validator for the GEZHI 60-course and 164-point text bases."""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
COURSE_FILE = ROOT / "references" / "course-system-60.md"
MAP_FILE = ROOT / "references" / "knowledge-map-164.md"

EXPECTED_CHAPTER_COUNTS = {
    "认知篇": 4,
    "院校篇": 8,
    "专业篇": 12,
    "测评篇": 5,
    "政策篇": 8,
    "途径篇": 7,
    "实操篇": 9,
    "交付篇": 7,
}
REQUIRED_FIELDS = ("核心问题", "原知识点", "核心内容", "课程产出", "课程类型", "去重职责")


def parse_courses(text: str):
    chapter_marks = [
        (m.start(), int(m.group(1)), m.group(2).strip())
        for m in re.finditer(r"^# (\d{2})｜(.+篇)\s*$", text, re.M)
    ]
    matches = list(re.finditer(r"^## 第(\d{2})课｜(.+)\s*$", text, re.M))
    courses = {}
    for index, match in enumerate(matches):
        number = int(match.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end():end]
        chapter = next(
            (name for pos, _, name in reversed(chapter_marks) if pos < match.start()),
            "",
        )
        fields = {}
        for field in REQUIRED_FIELDS:
            found = re.search(
                rf"^- \*\*{re.escape(field)}：\*\*\s*(.+?)\s*$",
                block,
                re.M,
            )
            fields[field] = found.group(1).strip() if found else ""
        courses[number] = {
            "title": match.group(2).strip(),
            "chapter": chapter,
            "fields": fields,
        }
    return courses


def parse_mapping(text: str):
    rows = []
    for line in text.splitlines():
        if not re.match(r"^\|\s*\d+\s*\|", line):
            continue
        cells = [cell.strip().replace(r"\|", "|") for cell in line.strip().strip("|").split("|")]
        if len(cells) != 10:
            raise ValueError(f"映射行列数不是10：{line[:100]}")
        rows.append(
            {
                "original_index": int(cells[0]),
                "original_chapter": cells[1],
                "code": cells[2],
                "original_title": cells[3],
                "original_content": cells[4],
                "original_output": cells[5],
                "new_course": int(cells[6]),
                "new_chapter": cells[7],
                "new_title": cells[8],
                "ownership": cells[9],
            }
        )
    return rows


def validate():
    errors = []
    course_text = COURSE_FILE.read_text(encoding="utf-8")
    map_text = MAP_FILE.read_text(encoding="utf-8")
    courses = parse_courses(course_text)
    mapping = parse_mapping(map_text)

    expected_numbers = list(range(1, 61))
    if sorted(courses) != expected_numbers:
        errors.append(f"课程编号应为01—60，实际为：{sorted(courses)}")

    chapter_counts = Counter(item["chapter"] for item in courses.values())
    if dict(chapter_counts) != EXPECTED_CHAPTER_COUNTS:
        errors.append(f"八篇课数不符：{dict(chapter_counts)}")

    for number, course in courses.items():
        missing = [field for field, value in course["fields"].items() if not value]
        if missing:
            errors.append(f"第{number:02d}课缺少字段：{', '.join(missing)}")

    if len(mapping) != 164:
        errors.append(f"知识点映射应为164条，实际为{len(mapping)}条")

    original_indexes = [row["original_index"] for row in mapping]
    if sorted(original_indexes) != list(range(1, 165)):
        errors.append("原知识点序号不是连续的1—164")

    codes = [row["code"] for row in mapping]
    duplicate_codes = sorted(code for code, count in Counter(codes).items() if count > 1)
    if duplicate_codes:
        errors.append(f"存在重复原知识点代码：{duplicate_codes}")

    course_codes = defaultdict(list)
    for number, course in courses.items():
        course_codes[number] = re.findall(r"\b[A-Z]{2}-\d{2}\b", course["fields"]["原知识点"])
    flattened_codes = [code for number in expected_numbers for code in course_codes[number]]
    duplicates_in_course_map = sorted(
        code for code, count in Counter(flattened_codes).items() if count > 1
    )
    if duplicates_in_course_map:
        errors.append(f"60课总览重复引用知识点代码：{duplicates_in_course_map}")

    if set(flattened_codes) != set(codes):
        missing = sorted(set(codes) - set(flattened_codes))
        extra = sorted(set(flattened_codes) - set(codes))
        errors.append(f"60课代码与164映射不一致；缺少={missing}；多出={extra}")

    for row in mapping:
        number = row["new_course"]
        course = courses.get(number)
        if course is None:
            errors.append(f"{row['code']} 指向不存在的第{number:02d}课")
            continue
        if row["code"] not in course_codes[number]:
            errors.append(f"{row['code']} 未出现在第{number:02d}课原知识点字段")
        if row["new_title"] != course["title"]:
            errors.append(
                f"{row['code']} 的新课程名称不一致：映射={row['new_title']}；总览={course['title']}"
            )
        if row["new_chapter"] != course["chapter"]:
            errors.append(
                f"{row['code']} 的新篇章不一致：映射={row['new_chapter']}；总览={course['chapter']}"
            )
        if row["ownership"] != "唯一主讲":
            errors.append(f"{row['code']} 归属方式不是“唯一主讲”：{row['ownership']}")

    return errors, courses, mapping, chapter_counts


def main() -> int:
    try:
        errors, courses, mapping, chapter_counts = validate()
    except Exception as exc:
        print(f"FAIL: 无法完成验证：{exc}")
        return 1

    if errors:
        print("FAIL: 课程底座验证未通过")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PASS: GEZHI课程底座验证通过")
    print(f"- 课程：{len(courses)}门，编号01—60连续")
    print("- 八篇课数：" + "，".join(f"{name}{chapter_counts[name]}课" for name in EXPECTED_CHAPTER_COUNTS))
    print(f"- 原知识点：{len(mapping)}条，代码唯一且全部有主讲归属")
    print("- 60课总览与164知识点映射：课程编号、名称、篇章和代码一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
