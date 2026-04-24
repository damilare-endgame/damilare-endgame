#!/usr/bin/env python3
"""Auto-deploy to Vercel when deploy keywords are detected in the user's prompt."""
import json
import sys
import os
import re
import subprocess

DEPLOY_PATTERN = re.compile(
    r'\b(deploy|vercel|ship\s+to\s+prod|push\s+to\s+vercel|go\s+live|release)\b',
    re.IGNORECASE
)


def extract_prompt(data):
    for key in ('prompt', 'user_message', 'message', 'text', 'content', 'input'):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
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
    if not prompt or not DEPLOY_PATTERN.search(prompt):
        sys.exit(0)

    cwd = os.getcwd()

    try:
        result = subprocess.run(
            ['vercel', '--prod', '--yes'],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=180,
        )
        output = (result.stdout + result.stderr).strip()
        status = 'succeeded' if result.returncode == 0 else 'failed'
    except FileNotFoundError:
        output = 'vercel CLI not found. Run: npm i -g vercel'
        status = 'failed'
    except subprocess.TimeoutExpired:
        output = 'Deployment timed out after 180s.'
        status = 'timed out'
    except Exception as e:
        output = str(e)
        status = 'failed'

    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'UserPromptSubmit',
            'additionalContext': f'[Vercel auto-deploy {status}]\n\n{output}',
        }
    }))


if __name__ == '__main__':
    main()
