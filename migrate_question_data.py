# -*- coding: utf-8 -*-
"""
题库数据迁移脚本。

此脚本用于将 data/library/ 目录下的现有JSON题库文件 (easy.json, hard.json, hybrid.json)
的数据结构迁移到符合最新 QuestionModel 定义的格式。
主要操作包括：
- 确保题目包含 body, correct_choices, incorrect_choices 字段。
- 添加/设置 question_type 为 "single_choice"。
- 添加/设置 num_correct_to_select 为 1。
- 保留可选的 ref 字段（如果存在）。
- 移除 QuestionModel 定义之外的其他字段。
"""
import json
from pathlib import Path
import sys

# 定义项目根目录，确保脚本可以从任何位置正确地找到数据文件
# Path(__file__) 是当前脚本的路径
# .resolve() 获取绝对路径
# .parent 获取父目录（即脚本所在的目录）
# 如果脚本就在项目根目录，那么 BASE_DIR 就是项目根目录
# 如果脚本在子目录，例如 scripts/migrate_question_data.py, 那么 BASE_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = Path(__file__).resolve().parent
LIBRARY_DIR = BASE_DIR / "data" / "library"
QUESTION_FILES = ["easy.json", "hard.json", "hybrid.json"]

# QuestionModel 定义中预期的核心字段 (用于筛选，确保不遗漏或添加多余字段)
# 注意：'correct_fillings' 对于单选题通常为 None 或不存在，脚本逻辑会确保这一点。
EXPECTED_FIELDS_BASE = {"body", "question_type", "correct_choices", "incorrect_choices", "num_correct_to_select"}
EXPECTED_FIELDS_OPTIONAL = {"ref", "correct_fillings"} # correct_fillings 将被明确设置为None或移除

def migrate_file(file_path: Path):
    """
    迁移单个JSON题库文件。

    Args:
        file_path (Path): 要迁移的题库文件的路径。
    """
    print(f"正在处理文件: {file_path.name} ...")
    if not file_path.exists():
        print(f"错误：文件 {file_path.name} 未找到于路径 {file_path}。")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            questions_data = json.load(f)
    except json.JSONDecodeError:
        print(f"错误：文件 {file_path.name} JSON格式错误。")
        return
    except Exception as e:
        print(f"错误：读取文件 {file_path.name} 时发生未知错误: {e}")
        return

    if not isinstance(questions_data, list):
        print(f"错误：文件 {file_path.name} 的顶层结构不是一个列表。跳过处理。")
        return

    migrated_questions = []
    processed_count = 0
    skipped_count = 0

    for i, q_orig in enumerate(questions_data):
        if not isinstance(q_orig, dict):
            print(f"警告：在 {file_path.name} 中发现非字典类型的题目数据（条目 {i+1}），已跳过。数据：{q_orig}")
            skipped_count += 1
            continue

        new_q = {}

        # 1. 保留必要的现有中文字段
        #    如果源文件中这些字段缺失，则使用默认值（空字符串/列表）以保证结构完整性
        new_q["body"] = q_orig.get("body", "")
        if not new_q["body"]:
             print(f"警告：在 {file_path.name} 的题目 {i+1} 中 'body' 字段为空或缺失。")

        correct_choices = q_orig.get("correct_choices")
        if correct_choices is None or not isinstance(correct_choices, list) or not correct_choices:
            print(f"警告：在 {file_path.name} 的题目 {i+1} 中 'correct_choices' 字段为空、缺失或格式不正确。将使用空列表。")
            new_q["correct_choices"] = []
        else:
            new_q["correct_choices"] = correct_choices

        incorrect_choices = q_orig.get("incorrect_choices")
        if incorrect_choices is None or not isinstance(incorrect_choices, list): # 允许空列表
             print(f"警告：在 {file_path.name} 的题目 {i+1} 中 'incorrect_choices' 字段缺失或格式不正确。将使用空列表。")
             new_q["incorrect_choices"] = []
        else:
            new_q["incorrect_choices"] = incorrect_choices

        # 2. 添加/设置 question_type
        new_q["question_type"] = "single_choice"

        # 3. 添加/设置 num_correct_to_select
        #    对于单选题，此值应为1。
        #    如果原始数据中有此字段且值不为1，则打印警告，但仍强制设为1。
        if "num_correct_to_select" in q_orig and q_orig["num_correct_to_select"] != 1:
            print(f"警告：在 {file_path.name} 的题目 {i+1} 中 'num_correct_to_select' 字段值为 {q_orig['num_correct_to_select']}，将强制修改为 1。")
        new_q["num_correct_to_select"] = 1

        # 4. 保留可选的 ref 字段 (如果存在且非空)
        if "ref" in q_orig and q_orig["ref"] is not None and str(q_orig["ref"]).strip():
            new_q["ref"] = str(q_orig["ref"])

        # 5. 处理 correct_fillings (对于单选题应为 None 或不包含)
        #    QuestionModel 将其定义为 Optional[List[str]]，因此设为 None 是合适的。
        #    或者，为了更干净，如果模型中该字段 default=None，则不添加此键。
        #    当前脚本选择不添加该键，除非模型要求（此处不要求）。
        # new_q["correct_fillings"] = None # 或者直接不包含此键

        # 6. 确保最终只包含模型中定义的字段
        #    这一步通过只选择性地从 new_q 拷贝到 final_q 来实现，
        #    或者在构建 new_q 时就只添加期望的字段。
        #    当前脚本在构建 new_q 时已遵循此原则。

        migrated_questions.append(new_q)
        processed_count += 1

    if skipped_count > 0:
        print(f"文件 {file_path.name} 中共有 {skipped_count} 个条目因格式问题被跳过。")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(migrated_questions, f, ensure_ascii=False, indent=4)
        print(f"文件 {file_path.name} 已成功迁移并写回。共处理 {processed_count} 道题目。")
    except IOError as e:
        print(f"错误：无法写回文件 {file_path.name}。错误详情: {e}")
    except Exception as e:
        print(f"错误：写回文件 {file_path.name} 时发生未知错误: {e}")

if __name__ == "__main__":
    # 检查脚本是否从项目根目录运行，以便LIBRARY_DIR正确
    expected_data_path = BASE_DIR / "data"
    if not expected_data_path.exists() or not expected_data_path.is_dir():
        print(f"错误：脚本似乎没有在预期的项目根目录下运行。")
        print(f"预期的 'data' 文件夹路径: {expected_data_path}")
        print(f"请确保从项目根目录执行此脚本，例如：python migrate_question_data.py")
        sys.exit(1)

    print("开始执行题库数据迁移脚本...")
    print(f"题库目录: {LIBRARY_DIR}")

    all_files_exist = True
    for qf_name in QUESTION_FILES:
        if not (LIBRARY_DIR / qf_name).exists():
            print(f"错误：必要文件 {qf_name} 在目录 {LIBRARY_DIR} 中未找到。")
            all_files_exist = False

    if not all_files_exist:
        print("部分题库文件缺失，脚本终止。")
        sys.exit(1)

    for qf_name in QUESTION_FILES:
        migrate_file(LIBRARY_DIR / qf_name)

    print("-----------------------------------------")
    print("题库数据迁移脚本执行完毕。")
    print("请注意：")
    print("1. 此脚本主要负责数据结构迁移，确保符合 QuestionModel 的基本要求。")
    print("2. 脚本假设题目内容（题干、选项、解释）已为中文。如果仍存在非中文内容，需要人工复核和翻译。")
    print(f"3. 已处理的文件位于: {LIBRARY_DIR}")
    print("4. 强烈建议在执行此脚本前备份您的 data/library 目录。")
    print("5. 如果之前执行覆写题库文件失败，此脚本的执行结果才是实际的迁移结果。")
    print("-----------------------------------------")
