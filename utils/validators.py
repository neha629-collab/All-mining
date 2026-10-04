"""
Validators — input validation & safety
"""

import re

def is_valid_label(label: str) -> tuple[bool, str]:
    if not label:
        return False, "Label খালি রাখা যাবে না"
    if len(label) < 2:
        return False, "Label কমপক্ষে 2 অক্ষরের হতে হবে"
    if len(label) > 32:
        return False, "Label 32 অক্ষরের বেশি হতে পারবে না"
    if not re.match(r"^[a-zA-Z0-9_\-]+$", label):
        return False, "Label এ শুধু A-Z, 0-9, _, - ব্যবহার করুন (space নয়)"
    return True, ""

def is_valid_init_data(data: str) -> tuple[bool, str]:
    if not data:
        return False, "initData খালি"
    if len(data) < 50:
        return False, "initData খুব ছোট, পুরো URL দিন"
    if "user=" not in data or "hash=" not in data:
        return False, "initData তে user এবং hash থাকতে হবে"
    return True, ""

def sanitize_markdown(text: str) -> str:
    """Escape markdown special chars to prevent injection"""
    if not text:
        return ""
    # Escape _, *, `, [
    for ch in ["_", "*", "`", "["]:
        text = text.replace(ch, f"\\{ch}")
    return text
