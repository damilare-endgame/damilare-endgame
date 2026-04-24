#!/usr/bin/env python3
"""Auto-detect and inject the best matching skill based on the user's prompt."""
import json
import sys
import os
import re
from pathlib import Path

SKILLS_DIR = Path(os.path.expanduser("~/.claude/skills"))
MIN_SCORE = 5

STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'this', 'that', 'these', 'those',
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us',
    'them', 'my', 'your', 'his', 'its', 'our', 'their', 'what', 'which',
    'who', 'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both',
    'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not',
    'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just', 'can',
    'want', 'need', 'please', 'help', 'get', 'make', 'into', 'also',
    'about', 'like', 'then', 'now', 'up', 'out', 'if', 'as',
}


def extract_description(content):
    if not content.startswith('---'):
        return ''
    end = content.find('\n---', 3)
    if end == -1:
        return ''
    fm = content[3:end]
    # Handle block scalar (description: |)
    block = re.search(r'description:\s*\|\s*\n((?:[ \t]+.+\n?)+)', fm)
    if block:
        return re.sub(r'\s+', ' ', block.group(1)).strip()
    # Handle inline description
    inline = re.search(r'description:\s*([^\n]+)', fm)
    if inline:
        return inline.group(1).strip().strip('"\'')
    return ''


def tokenize(text):
    words = re.sub(r'[^\w\s]', ' ', text.lower()).split()
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def split_compound(name):
    """Split hyphenated names AND unseparated compound words via known sub-tokens."""
    parts = [p for p in re.split(r'[-_]', name.lower()) if len(p) > 2]
    expanded = []
    for part in parts:
        expanded.append(part)
        # For long unseparated compounds (e.g. "promptforge"), extract ≥4-char
        # prefixes/suffixes that could be standalone words in the prompt.
        if len(part) >= 7 and '-' not in name and '_' not in name:
            for cut in range(4, len(part) - 3):
                prefix, suffix = part[:cut], part[cut:]
                if len(prefix) >= 4:
                    expanded.append(prefix)
                if len(suffix) >= 4:
                    expanded.append(suffix)
    return list(dict.fromkeys(expanded))  # deduplicate, preserve order


def score_skill(prompt_tokens, skill_name, description):
    score = 0
    name_parts = [p for p in re.split(r'[-_]', skill_name.lower()) if len(p) > 2]
    all_parts = split_compound(skill_name)

    if name_parts:
        matched = sum(1 for p in name_parts if p in prompt_tokens)
        if matched > 0:
            if matched == len(name_parts):
                # All separator-delimited parts match: strong signal
                score += 10
            else:
                score += 3 * matched
        elif len(name_parts) == 1:
            # Single compound word — credit sub-token matches (e.g. "forge" in "promptforge")
            sub_matches = sum(1 for p in all_parts if p != name_parts[0] and p in prompt_tokens)
            score += 2 * min(sub_matches, 3)

    if description:
        desc_tokens = tokenize(description)
        score += len(prompt_tokens & desc_tokens)

    return score


def extract_prompt(data):
    for key in ('prompt', 'user_message', 'message', 'text', 'content', 'input'):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # Fallback: use any long-enough string value
    for val in data.values():
        if isinstance(val, str) and len(val) > 15:
            return val.strip()
    return ''


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt = extract_prompt(data)
    if not prompt:
        sys.exit(0)

    prompt_tokens = tokenize(prompt)
    if not prompt_tokens:
        sys.exit(0)

    if not SKILLS_DIR.exists():
        sys.exit(0)

    best_skill = None
    best_score = 0
    second_score = 0
    best_content = None

    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / 'SKILL.md'
        if not skill_file.exists():
            continue
        try:
            content = skill_file.read_text(encoding='utf-8')
            desc = extract_description(content)
            score = score_skill(prompt_tokens, skill_dir.name, desc)
            if score > best_score:
                second_score = best_score
                best_score = score
                best_skill = skill_dir.name
                best_content = content
            elif score > second_score:
                second_score = score
        except Exception:
            continue

    # Fire when there's a clear winner above the minimum threshold
    if best_skill and best_score >= MIN_SCORE and best_score > second_score:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"[Auto-loaded skill: {best_skill}]\n\n{best_content}"
            }
        }
        print(json.dumps(output))


if __name__ == '__main__':
    main()
