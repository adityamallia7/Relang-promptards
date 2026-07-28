#!/usr/bin/env python3
"""
marked - Markdown parser in Python
Port of marked.js v18
"""

import sys
import re
import urllib.parse

# ---------------------------------------------------------------------------
# Helpers & Escaping
# ---------------------------------------------------------------------------

ESCAPE_TEST = re.compile(r'[&<>"\']')
ESCAPE_REPLACE = re.compile(r'[&<>"\']')
ESCAPE_TEST_NO_ENCODE = re.compile(r'[<>"\']|&(?!(#[0-9]{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)')
ESCAPE_REPLACE_NO_ENCODE = re.compile(r'[<>"\']|&(?!(#[0-9]{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)')

ESCAPE_MAP = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
}

def escape_html(html, encode=True):
    if encode:
        if ESCAPE_TEST.search(html):
            return ESCAPE_REPLACE.sub(lambda m: ESCAPE_MAP[m.group(0)], html)
    else:
        if ESCAPE_TEST_NO_ENCODE.search(html):
            return ESCAPE_REPLACE_NO_ENCODE.sub(lambda m: ESCAPE_MAP[m.group(0)], html)
    return html

def clean_url(href):
    try:
        href = urllib.parse.quote(href, safe="!#$%&'()*+,-./:;=?@[]~_").replace("%25", "%")
    except Exception:
        return None
    return href

def rtrim(str_val, c, invert=False):
    length = len(str_val)
    if length == 0:
        return ""
    s = 0
    while s < length:
        ch = str_val[length - s - 1]
        if (ch == c and not invert) or (ch != c and invert):
            s += 1
        else:
            break
    return str_val[:length - s]

def split_cells(table_row, count=None):
    t = re.sub(r'\\\|', ' |', table_row.replace(r'\|', ' |'))
    # Wait, simple pipe split with backslash handling:
    # Look for unescaped pipes
    raw_cells = []
    current = []
    i = 0
    n = len(table_row)
    while i < n:
        if table_row[i] == '\\' and i + 1 < n and table_row[i+1] == '|':
            current.append('|')
            i += 2
        elif table_row[i] == '|':
            raw_cells.append("".join(current))
            current = []
            i += 1
        else:
            current.append(table_row[i])
            i += 1
    raw_cells.append("".join(current))

    # Strip empty first/last cell if present
    if len(raw_cells) > 0 and not raw_cells[0].strip():
        raw_cells.pop(0)
    if len(raw_cells) > 0 and not raw_cells[-1].strip():
        raw_cells.pop()

    if count is not None:
        if len(raw_cells) > count:
            raw_cells = raw_cells[:count]
        else:
            while len(raw_cells) < count:
                raw_cells.append('')

    return [cell.strip() for cell in raw_cells]

def find_closing_bracket(str_val, b):
    if b[1] not in str_val:
        return -1
    level = 0
    i = 0
    n = len(str_val)
    while i < n:
        if str_val[i] == '\\':
            i += 2
            continue
        if str_val[i] == b[0]:
            level += 1
        elif str_val[i] == b[1]:
            level -= 1
            if level < 0:
                return i
        i += 1
    return -2 if level > 0 else -1

def expand_tabs(str_val, offset=0):
    t = offset
    res = []
    for c in str_val:
        if c == '\t':
            r = 4 - (t % 4)
            res.append(' ' * r)
            t += r
        else:
            res.append(c)
            t += 1
    return "".join(res)


# ---------------------------------------------------------------------------
# Regex Rules Setup
# ---------------------------------------------------------------------------

BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|"
    "dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|"
    "h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|meta|nav|noframes|"
    "ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul"
)

HTML_COMMENT = r'<!--(?:-?>|[\s\S]*?(?:-->|$))'

def make_block_rules():
    newline = re.compile(r'^(?:[ \t]*(?:\n|$))+')
    code = re.compile(r'^((?: {4}| {0,3}\t)[^\n]+(?:\n(?:[ \t]*(?:\n|$))*)?)+')
    fences = re.compile(r'^ {0,3}(`{3,}(?=[^`\n]*(?:\n|$))|~{3,})([^\n]*)(?:\n|$)(?:|([\s\S]*?)(?:\n|$))(?: {0,3}\1[~`]* *(?=\n|$)|$)')
    hr = re.compile(r'^ {0,3}((?:-[\t ]*){3,}|(?:_[ \t]*){3,}|(?:\*[ \t]*){3,})(?:\n+|$)')
    heading = re.compile(r'^ {0,3}(#{1,6})(?=\s|$)(.*)(?:\n+|$)')
    bull = r' {0,3}(?:[*+-]|\d{1,9}[.)])'
    
    # lheading
    lheading = re.compile(
        r'^(?!' + bull + r'|(?: {4}| {0,3}\t)| {0,3}(?:`{3,}|~{3,})| {0,3}>| {0,3}#{1,6}| {0,3}<[^\n>]+>\n)'
        r'((?:.|\n(?!\s*?\n|' + bull + r'|(?: {4}| {0,3}\t)| {0,3}(?:`{3,}|~{3,})| {0,3}>| {0,3}#{1,6}| {0,3}<[^\n>]+>\n))+?)\n {0,3}(=+|-+) *(?:\n+|$)'
    )

    label_re = r'(?:(?!\s*\])(?:\\[\s\S]|[^\[\]\\])+)'
    title_re = r'(?:"(?:\\"?|[^"\\])*"|\'[^\'\n]*(?:\n[^\'\n]+)*\n?\'|\([^()]*\))'
    def_re = re.compile(
        r'^ {0,3}\[' + label_re + r'\]: *(?:\n[ \t]*)?([^<\s][^\s]*|<.*?>)(?:(?: +(?:\n[ \t]*)?| *\n[ \t]*)(?:' + title_re + r'))? *(?:\n+|$)'
    )

    list_re = re.compile(r'^(' + bull + r')([ \t][^\n]*?)?(?:\n|$)')

    html_re = re.compile(
        r'^ {0,3}(?:'
        r'<(script|pre|style|textarea)[\s>][\s\S]*?(?:</\1>[^\n]*\n+|$)'
        r'|' + HTML_COMMENT + r'[^\n]*(\n+|$)'
        r'|<\?[\s\S]*?(?:\?>[^\n]*\n+|$)'
        r'|<![A-Z][\s\S]*?(?:>[^\n]*\n+|$)'
        r'|<!\[CDATA\[[\s\S]*?(?:\]\]>[^\n]*\n+|$)'
        r'|</?(?:' + BLOCK_TAGS + r')(?: +|\n|/?>)[\s\S]*?(?:(?:\n[ \t]*)+\n|$)'
        r'|<(?!script|pre|style|textarea)([a-z][\w-]*)(?: +[a-zA-Z:_][\w.:-]*(?: *= *"[^"\n]*"| *= *\'[^\'\n]*\'| *= *[^\s"\'=<>`]+)?)? */?>(?=[ \t]*(?:\n|$))[\s\S]*?(?:(?:\n[ \t]*)+\n|$)'
        r'|</(?!script|pre|style|textarea)[a-z][\w-]*\s*>(?=[ \t]*(?:\n|$))[\s\S]*?(?:(?:\n[ \t]*)+\n|$)'
        r')', re.IGNORECASE
    )

    table_re = re.compile(
        r'^ *([^\n ].*)\n {0,3}((?:\| *)?:?-+:? *(?:\| *:?-+:? *)*(?:\| *)?)(?:\n((?:(?! *\n|'
        r' {0,3}((?:-[\t ]*){3,}|(?:_[ \t]*){3,}|(?:\*[ \t]*){3,})(?:\n+|$)'
        r'| {0,3}#{1,6}(?:\s|$)'
        r'| {0,3}>'
        r'|(?: {4}| {0,3}\t)[^\n]'
        r'| {0,3}(?:`{3,}(?=[^`\n]*\n)|~{3,})[^\n]*\n'
        r'| {0,3}(?:[*+-]|1[.)])[ \t]'
        r'|</?(?:' + BLOCK_TAGS + r')(?: +|\n|/?>)|<(?:script|pre|style|textarea|!--)'
        r').*(?:\n|$))*)\n*|$)'
    )

    paragraph = re.compile(
        r'^([^\n]+(?:\n(?!'
        r' {0,3}((?:-[\t ]*){3,}|(?:_[ \t]*){3,}|(?:\*[ \t]*){3,})(?:\n+|$)'
        r'| {0,3}#{1,6}(?:\s|$)'
        r'| {0,3}>'
        r'| {0,3}(?:`{3,}(?=[^`\n]*\n)|~{3,})[^\n]*\n'
        r'| {0,3}(?:[*+-]|1[.)])[ \t]+[^ \t\n]'
        r'|</?(?:' + BLOCK_TAGS + r')(?: +|\n|/?>)|<(?:script|pre|style|textarea|!--)'
        r')[^\n]+)*)'
    )

    blockquote = re.compile(
        r'^( {0,3}> ?(' + paragraph.pattern[2:-1] + r'|[^\n]*)(?:\n|$))+'
    )

    text_re = re.compile(r'^[^\n]+')

    return {
        "newline": newline,
        "code": code,
        "fences": fences,
        "hr": hr,
        "heading": heading,
        "lheading": lheading,
        "def": def_re,
        "list": list_re,
        "html": html_re,
        "table": table_re,
        "blockquote": blockquote,
        "paragraph": paragraph,
        "text": text_re,
        "bull": bull,
    }


def make_inline_rules():
    escape = re.compile(r'^\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])')
    tag = re.compile(
        r'^(?:' + HTML_COMMENT.replace('(?:-->|$)', '-->') +
        r'|</[a-zA-Z][\w:-]*\s*>' +
        r'|<[a-zA-Z][\w-]*(?:\s+[a-zA-Z:_][\w.:-]*(?:\s*=\s*"[^"]*"|\s*=\s*\'[^\']*\'|\s*=\s*[^\s"\'=<>`]+)?)*\s*/?>' +
        r'|<\?[\s\S]*?\?>' +
        r'|<![a-zA-Z]+\s[\s\S]*?>' +
        r'|<!\[CDATA\[[\s\S]*?\]\]>)'
    )

    v = r'(?:\[(?:\\[\s\S]|[^\[\]\\])*\]|\\[\s\S]|`+(?!`)[^`]*?`+(?!`)|``+(?=\])|[^\[\]\\`])*?'
    label = v
    href = r'<(?:\\.|[^\n<>\\])+>|[^ \t\n\x00-\x1f]*'
    title = r'"(?:\\"?|[^"\\])*"|\'(?:\\\'?|[^\'\\])*\'|\((?:\\\)?|[^)\\])*\)'

    link = re.compile(r'^!?\[' + label + r'\]\(\s*(' + href + r')(?:(?:[ \t]+(?:\n[ \t]*)?|\n[ \t]*)(?:' + title + r'))?\s*\)')
    u_ref = r'(?!\s*\])(?:\\[\s\S]|[^\[\]\\])+'
    reflink = re.compile(r'^!?\[' + label + r'\]\[' + u_ref + r'\]')
    nolink = re.compile(r'^!?\[' + u_ref + r'\](?:\[\])?')
    reflink_search = re.compile(r'(?:' + reflink.pattern[1:] + r'|' + nolink.pattern[1:] + r'(?!\())')

    code = re.compile(r'^(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)')
    br = re.compile(r'^( {2,}|\\)\n(?!\s*$)')
    del_re = re.compile(r'^(~~?)(?=[^\s~])((?:\\[\s\S]|[^\\])*?(?:\\[\s\S]|[^\s~\\]))\1(?=[^~]|$)')

    autolink = re.compile(r'^<([a-zA-Z][a-zA-Z0-9+.-]{1,31}:[^\s\x00-\x1f<>]*|[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+(?![-_]))>')

    url = re.compile(r'^((?:https?|ftp)://|www\.)(?:[a-zA-Z0-9\-]+\.?)+[^\s<]*|^[A-Za-z0-9._+-]+@[a-zA-Z0-9-_]+(?:\.[a-zA-Z0-9-_]*[a-zA-Z0-9])+(?![-_])')
    backpedal = re.compile(r'(?:[^?!.,:;*_\'"~()&]+|\([^)]*\)|&(?![a-zA-Z0-9]+;$)|[?!.,:;*_\'"~)]+(?!$))+')

    text = re.compile(
        r'^([`~]+|[^`~])(?:(?= {2,}\n)|(?=[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@)|[\s\S]*?(?:(?=[\\<!\[`*~_]|\b_|(?:https?|ftp)://|www\.|$)|[^ ](?= {2,}\n)|[^a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-](?=[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@)))'
    )

    punctuation = re.compile(r'^[^\s\w]', re.UNICODE)
    any_punctuation = re.compile(r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])')

    return {
        "escape": escape,
        "tag": tag,
        "link": link,
        "reflink": reflink,
        "nolink": nolink,
        "reflinkSearch": reflink_search,
        "code": code,
        "br": br,
        "del": del_re,
        "autolink": autolink,
        "url": url,
        "_backpedal": backpedal,
        "text": text,
        "punctuation": punctuation,
        "anyPunctuation": any_punctuation,
    }


BLOCK_RULES = make_block_rules()
INLINE_RULES = make_inline_rules()


# ---------------------------------------------------------------------------
# Lexer & Tokenizer
# ---------------------------------------------------------------------------

class Tokenizer:
    def __init__(self, options=None):
        self.options = options or {}
        self.lexer = None
        self.rules = {"block": BLOCK_RULES, "inline": INLINE_RULES}

    def space(self, src):
        m = self.rules["block"]["newline"].match(src)
        if m and len(m.group(0)) > 0:
            return {"type": "space", "raw": m.group(0)}
        return None

    def code(self, src):
        m = self.rules["block"]["code"].match(src)
        if m:
            raw = m.group(0)
            # Remove trailing blank lines
            lines = raw.split('\n')
            t = len(lines) - 1
            while t >= 0 and re.match(r'^[ \t]*$', lines[t]):
                t -= 1
            n = raw if len(lines) - t <= 2 else '\n'.join(lines[:t+1])
            s = re.sub(r'^(?: {1,4}| {0,3}\t)', '', n, flags=re.MULTILINE)
            return {"type": "code", "raw": n, "codeBlockStyle": "indented", "text": s}
        return None

    def fences(self, src):
        m = self.rules["block"]["fences"].match(src)
        if m:
            raw = m.group(0)
            lang = m.group(2).strip() if m.group(2) else ""
            if lang:
                lang = self.rules["inline"]["anyPunctuation"].sub(r'\1', lang)
            content = m.group(3) if m.group(3) is not None else ""
            
            # ot compensation:
            indent_m = re.match(r'^(\s+)(?:```|~~~)', raw)
            if indent_m:
                indent = indent_m.group(1)
                lines = content.split('\n')
                res_lines = []
                for line in lines:
                    bg = re.match(r'^\s+', line)
                    if bg:
                        bg_str = bg.group(0)
                        if len(bg_str) >= len(indent):
                            res_lines.append(line[len(indent):])
                        else:
                            res_lines.append(line)
                    else:
                        res_lines.append(line)
                content = '\n'.join(res_lines)

            return {"type": "code", "raw": raw, "lang": lang, "text": content}
        return None

    def heading(self, src):
        m = self.rules["block"]["heading"].match(src)
        if m:
            text = m.group(2).strip()
            if text.endswith('#'):
                s = rtrim(text, '#')
                if not s or s.endswith(' '):
                    text = s.strip()
            return {
                "type": "heading",
                "raw": rtrim(m.group(0), '\n'),
                "depth": len(m.group(1)),
                "text": text,
                "tokens": self.lexer.inline(text)
            }
        return None

    def hr(self, src):
        m = self.rules["block"]["hr"].match(src)
        if m:
            return {"type": "hr", "raw": rtrim(m.group(0), '\n')}
        return None

    def blockquote(self, src):
        m = self.rules["block"]["blockquote"].match(src)
        if m:
            raw_all = rtrim(m.group(0), '\n')
            lines = raw_all.split('\n')
            s_acc = ""
            r_acc = ""
            tokens = []

            while len(lines) > 0:
                in_bq = False
                u = []
                a = 0
                for a in range(len(lines)):
                    if re.match(r'^ {0,3}>', lines[a]):
                        u.append(lines[a])
                        in_bq = True
                    elif not in_bq:
                        u.append(lines[a])
                    else:
                        break
                lines = lines[a:] if in_bq else []

                c = '\n'.join(u)
                p = re.sub(r'\n {0,3}((?:=+|-+) *)(?=\n|$)', r'\n    \1', c)
                p = re.sub(r'^ {0,3}>[ \t]?', '', p, flags=re.MULTILINE)

                s_acc = f"{s_acc}\n{c}" if s_acc else c
                r_acc = f"{r_acc}\n{p}" if r_acc else p

                top_state = self.lexer.state["top"]
                self.lexer.state["top"] = True
                self.lexer.block_tokens(p, tokens, True)
                self.lexer.state["top"] = top_state

                if len(lines) == 0:
                    break

            return {"type": "blockquote", "raw": s_acc, "tokens": tokens, "text": r_acc}
        return None

    def list(self, src):
        m = self.rules["block"]["list"].match(src)
        if not m:
            return None

        bull_str = m.group(1).strip()
        is_ordered = len(bull_str) > 1
        list_obj = {
            "type": "list",
            "raw": "",
            "ordered": is_ordered,
            "start": int(bull_str[:-1]) if is_ordered else "",
            "loose": False,
            "items": []
        }

        bull_pattern = r'\d{1,9}\\' + bull_str[-1] if is_ordered else r'\\' + bull_str
        item_regex = re.compile(r'^( {0,3}' + bull_pattern + r')((?:[ \t][^\n]*)?(?:\n|$))')
        
        has_double_blank = False
        was_loose = False

        while src:
            item_match = item_regex.match(src)
            if not item_match or self.rules["block"]["hr"].match(src):
                break
            
            raw_item = item_match.group(0)
            src = src[len(raw_item):]

            first_line = item_match.group(2).split('\n', 1)[0]
            indent_first = expand_tabs(first_line, len(item_match.group(1)))
            next_line = src.split('\n', 1)[0]
            is_blank = not indent_first.strip()
            item_indent = 0
            item_text = ""

            non_space = re.search(r'[^ ]', indent_first)
            if is_blank:
                item_indent = len(item_match.group(1)) + 1
                item_text = indent_first[item_indent:]
            elif non_space:
                idx = non_space.start()
                idx = 1 if idx > 4 else idx
                item_text = indent_first[idx:]
                item_indent = idx + len(item_match.group(1))

            if is_blank and re.match(r'^[ \t]*$', next_line):
                raw_item += next_line + '\n'
                src = src[len(next_line)+1:]

            # Parse item body
            # Simple check for item content continuation
            while src:
                curr_line = src.split('\n', 1)[0]
                if not curr_line.strip():
                    item_text += '\n'
                    raw_item += curr_line + '\n'
                    src = src[len(curr_line)+1:]
                    continue
                
                # If next bullet or hr or fence, break item line scan
                if item_regex.match(curr_line) or self.rules["block"]["hr"].match(curr_line):
                    break
                
                expanded = expand_tabs(curr_line)
                non_sp = re.search(r'[^ ]', expanded)
                if non_sp and non_sp.start() >= item_indent:
                    item_text += '\n' + expanded[item_indent:]
                else:
                    break
                raw_item += curr_line + '\n'
                src = src[len(curr_line)+1:]

            if re.search(r'\n[ \t]*\n[ \t]*$', raw_item):
                list_obj["loose"] = True

            item_dict = {
                "type": "list_item",
                "raw": raw_item,
                "task": False,
                "loose": False,
                "text": item_text.strip('\n'),
                "tokens": []
            }

            # Check task list [ ] or [x]
            task_m = re.match(r'^\[([ xX])\] +', item_dict["text"])
            if task_m:
                item_dict["task"] = True
                item_dict["checked"] = task_m.group(1) != ' '
                item_dict["text"] = item_dict["text"][len(task_m.group(0)):]

            list_obj["items"].append(item_dict)
            list_obj["raw"] += raw_item

        if not list_obj["items"]:
            return None

        # Clean trailing space from last item
        list_obj["raw"] = list_obj["raw"].rstrip()

        for item in list_obj["items"]:
            self.lexer.state["top"] = False
            item["tokens"] = self.lexer.block_tokens(item["text"], [])

        if list_obj["loose"]:
            for item in list_obj["items"]:
                item["loose"] = True
                for tok in item["tokens"]:
                    if tok["type"] == "text":
                        tok["type"] = "paragraph"

        return list_obj

    def html(self, src):
        m = self.rules["block"]["html"].match(src)
        if m:
            raw = m.group(0)
            lines = raw.split('\n')
            t = len(lines) - 1
            while t >= 0 and re.match(r'^[ \t]*$', lines[t]):
                t -= 1
            n = raw if len(lines) - t <= 2 else '\n'.join(lines[:t+1])
            is_pre = m.group(1) in ("pre", "script", "style") if m.group(1) else False
            return {"type": "html", "block": True, "raw": n, "pre": is_pre, "text": n}
        return None

    def def_rule(self, src):
        m = self.rules["block"]["def"].match(src)
        if m:
            tag = re.sub(r'\s+', ' ', m.group(1).lower())
            href = m.group(2) if m.group(2) else ""
            if href.startswith('<') and href.endswith('>'):
                href = href[1:-1]
            href = self.rules["inline"]["anyPunctuation"].sub(r'\1', href)
            title = m.group(3) if m.group(3) else None
            if title:
                title = title[1:-1]
                title = self.rules["inline"]["anyPunctuation"].sub(r'\1', title)
            return {"type": "def", "tag": tag, "raw": rtrim(m.group(0), '\n'), "href": href, "title": title}
        return None

    def table(self, src):
        m = self.rules["block"]["table"].match(src)
        if not m:
            return None
        if not re.search(r'[:|]', m.group(2)):
            return None

        header_raw = split_cells(m.group(1))
        aligns_raw = [a.strip() for a in re.sub(r'^\||\| *$', '', m.group(2)).split('|')]
        rows_raw = m.group(3).strip().split('\n') if m.group(3) and m.group(3).strip() else []

        tbl = {
            "type": "table",
            "raw": rtrim(m.group(0), '\n'),
            "header": [],
            "align": [],
            "rows": []
        }

        if len(header_raw) == len(aligns_raw):
            for a in aligns_raw:
                if re.match(r'^ *-+: *$', a):
                    tbl["align"].append("right")
                elif re.match(r'^ *:-+: *$', a):
                    tbl["align"].append("center")
                elif re.match(r'^ *:-+ *$', a):
                    tbl["align"].append("left")
                else:
                    tbl["align"].append(None)

            for i, h in enumerate(header_raw):
                tbl["header"].append({
                    "text": h,
                    "tokens": self.lexer.inline(h),
                    "header": True,
                    "align": tbl["align"][i]
                })

            for r in rows_raw:
                cells = split_cells(r, len(tbl["header"]))
                row_cells = []
                for i, c in enumerate(cells):
                    row_cells.append({
                        "text": c,
                        "tokens": self.lexer.inline(c),
                        "header": False,
                        "align": tbl["align"][i]
                    })
                tbl["rows"].append(row_cells)

            return tbl
        return None

    def lheading(self, src):
        m = self.rules["block"]["lheading"].match(src)
        if m:
            text = m.group(1).strip()
            depth = 1 if m.group(2).startswith('=') else 2
            return {
                "type": "heading",
                "raw": rtrim(m.group(0), '\n'),
                "depth": depth,
                "text": text,
                "tokens": self.lexer.inline(text)
            }
        return None

    def paragraph(self, src):
        m = self.rules["block"]["paragraph"].match(src)
        if m:
            text = m.group(1)[:-1] if m.group(1).endswith('\n') else m.group(1)
            return {"type": "paragraph", "raw": m.group(0), "text": text, "tokens": self.lexer.inline(text)}
        return None

    def text(self, src):
        m = self.rules["block"]["text"].match(src)
        if m:
            return {"type": "text", "raw": m.group(0), "text": m.group(0), "tokens": self.lexer.inline(m.group(0))}
        return None

    # Inline Tokenizer methods
    def escape(self, src):
        m = self.rules["inline"]["escape"].match(src)
        if m:
            return {"type": "escape", "raw": m.group(0), "text": m.group(1)}
        return None

    def tag(self, src):
        m = self.rules["inline"]["tag"].match(src)
        if m:
            return {
                "type": "html",
                "raw": m.group(0),
                "inLink": self.lexer.state["inLink"],
                "inRawBlock": self.lexer.state["inRawBlock"],
                "block": False,
                "text": m.group(0)
            }
        return None

    def link(self, src):
        m = self.rules["inline"]["link"].match(src)
        if m:
            href = m.group(2).strip() if m.group(2) else ""
            title = m.group(3).strip()[1:-1] if m.group(3) else ""
            if href.startswith('<') and href.endswith('>'):
                href = href[1:-1]
            href = self.rules["inline"]["anyPunctuation"].sub(r'\1', href)
            if title:
                title = self.rules["inline"]["anyPunctuation"].sub(r'\1', title)
            text = m.group(1).replace(r'\[', '[').replace(r'\]', ']')
            is_image = m.group(0).startswith('!')
            return {
                "type": "image" if is_image else "link",
                "raw": m.group(0),
                "href": href,
                "title": title or None,
                "text": text,
                "tokens": self.lexer.inline_tokens(text)
            }
        return None

    def reflink(self, src, links):
        m = self.rules["inline"]["reflink"].match(src) or self.rules["inline"]["nolink"].match(src)
        if m:
            ref = (m.group(2) or m.group(1)).replace('\n', ' ')
            ref_key = re.sub(r'\s+', ' ', ref).lower()
            link_target = links.get(ref_key) if links else None
            if not link_target:
                ch = m.group(0)[0]
                return {"type": "text", "raw": ch, "text": ch}
            
            is_image = m.group(0).startswith('!')
            text = m.group(1)
            return {
                "type": "image" if is_image else "link",
                "raw": m.group(0),
                "href": link_target["href"],
                "title": link_target.get("title"),
                "text": text,
                "tokens": self.lexer.inline_tokens(text)
            }
        return None

    def codespan(self, src):
        m = self.rules["inline"]["code"].match(src)
        if m:
            text = m.group(2).replace('\n', ' ')
            has_non_space = bool(re.search(r'[^ ]', text))
            has_surrounding_space = text.startswith(' ') and text.endswith(' ')
            if has_non_space and has_surrounding_space:
                text = text[1:-1]
            return {"type": "codespan", "raw": m.group(0), "text": text}
        return None

    def br(self, src):
        m = self.rules["inline"]["br"].match(src)
        if m:
            return {"type": "br", "raw": m.group(0)}
        return None

    def del_rule(self, src):
        m = self.rules["inline"]["del"].match(src)
        if m:
            text = m.group(2)
            return {"type": "del", "raw": m.group(0), "text": text, "tokens": self.lexer.inline_tokens(text)}
        return None

    def autolink(self, src):
        m = self.rules["inline"]["autolink"].match(src)
        if m:
            text = m.group(1)
            href = "mailto:" + text if m.group(2) == "@" else text
            return {
                "type": "link",
                "raw": m.group(0),
                "text": text,
                "href": href,
                "tokens": [{"type": "text", "raw": text, "text": text}]
            }
        return None

    def url(self, src):
        m = self.rules["inline"]["url"].match(src)
        if m:
            text = m.group(0)
            if m.group(1) == "www.":
                href = "http://" + text
            elif "@" in text and not text.startswith("http"):
                href = "mailto:" + text
            else:
                href = text
            return {
                "type": "link",
                "raw": text,
                "text": text,
                "href": href,
                "tokens": [{"type": "text", "raw": text, "text": text}]
            }
        return None

    def inline_text(self, src):
        m = self.rules["inline"]["text"].match(src)
        if m:
            return {"type": "text", "raw": m.group(0), "text": m.group(0)}
        return None


class Lexer:
    def __init__(self, options=None):
        self.tokens = []
        self.tokens_links = {}
        self.options = options or {}
        self.tokenizer = Tokenizer(self.options)
        self.tokenizer.lexer = self
        self.inline_queue = []
        self.state = {"inLink": False, "inRawBlock": False, "top": True}

    def lex(self, src):
        src = src.replace('\r\n', '\n').replace('\r', '\n')
        self.block_tokens(src, self.tokens)
        for item in self.inline_queue:
            self.inline_tokens(item["src"], item["tokens"])
        self.inline_queue = []
        return self.tokens

    def block_tokens(self, src, tokens=None, in_blockquote=False):
        if tokens is None:
            tokens = []

        last_len = float('inf')
        while src:
            if len(src) < last_len:
                last_len = len(src)
            else:
                # Prevent infinite loop
                break

            tok = self.tokenizer.space(src)
            if tok:
                src = src[len(tok["raw"]):]
                if len(tok["raw"]) == 1 and len(tokens) > 0:
                    tokens[-1]["raw"] += '\n'
                else:
                    tokens.append(tok)
                continue

            tok = self.tokenizer.code(src)
            if tok:
                src = src[len(tok["raw"]):]
                if len(tokens) > 0 and tokens[-1]["type"] in ("paragraph", "text"):
                    tokens[-1]["raw"] += ('\n' if not tokens[-1]["raw"].endswith('\n') else '') + tok["raw"]
                    tokens[-1]["text"] += '\n' + tok["text"]
                    if self.inline_queue:
                        self.inline_queue[-1]["src"] = tokens[-1]["text"]
                else:
                    tokens.append(tok)
                continue

            tok = self.tokenizer.fences(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.heading(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.hr(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.blockquote(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.list(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.html(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.def_rule(src)
            if tok:
                src = src[len(tok["raw"]):]
                if len(tokens) > 0 and tokens[-1]["type"] in ("paragraph", "text"):
                    tokens[-1]["raw"] += ('\n' if not tokens[-1]["raw"].endswith('\n') else '') + tok["raw"]
                    tokens[-1]["text"] += '\n' + tok["raw"]
                    if self.inline_queue:
                        self.inline_queue[-1]["src"] = tokens[-1]["text"]
                else:
                    if tok["tag"] not in self.tokens_links:
                        self.tokens_links[tok["tag"]] = {"href": tok["href"], "title": tok["title"]}
                        tokens.append(tok)
                continue

            tok = self.tokenizer.table(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.lheading(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            if self.state["top"]:
                tok = self.tokenizer.paragraph(src)
                if tok:
                    src = src[len(tok["raw"]):]
                    tokens.append(tok)
                    continue

            tok = self.tokenizer.text(src)
            if tok:
                src = src[len(tok["raw"]):]
                if len(tokens) > 0 and tokens[-1]["type"] == "text":
                    tokens[-1]["raw"] += ('\n' if not tokens[-1]["raw"].endswith('\n') else '') + tok["raw"]
                    tokens[-1]["text"] += '\n' + tok["text"]
                    if self.inline_queue:
                        self.inline_queue[-1]["src"] = tokens[-1]["text"]
                else:
                    tokens.append(tok)
                continue

            if src:
                break

        self.state["top"] = True
        return tokens

    def inline(self, src, tokens=None):
        if tokens is None:
            tokens = []
        self.inline_queue.append({"src": src, "tokens": tokens})
        return tokens

    def inline_tokens(self, src, tokens=None):
        if tokens is None:
            tokens = []

        last_len = float('inf')
        while src:
            if len(src) < last_len:
                last_len = len(src)
            else:
                break

            tok = self.tokenizer.escape(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.tag(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.link(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.reflink(src, self.tokens_links)
            if tok:
                src = src[len(tok["raw"]):]
                if tok["type"] == "text" and len(tokens) > 0 and tokens[-1]["type"] == "text":
                    tokens[-1]["raw"] += tok["raw"]
                    tokens[-1]["text"] += tok["text"]
                else:
                    tokens.append(tok)
                continue

            # Emphasis / Strong handling
            em_match = self._match_em_strong(src)
            if em_match:
                src = src[len(em_match["raw"]):]
                tokens.append(em_match)
                continue

            tok = self.tokenizer.codespan(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.br(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.del_rule(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            tok = self.tokenizer.autolink(src)
            if tok:
                src = src[len(tok["raw"]):]
                tokens.append(tok)
                continue

            if not self.state["inLink"]:
                tok = self.tokenizer.url(src)
                if tok:
                    src = src[len(tok["raw"]):]
                    tokens.append(tok)
                    continue

            tok = self.tokenizer.inline_text(src)
            if tok:
                src = src[len(tok["raw"]):]
                if len(tokens) > 0 and tokens[-1]["type"] == "text":
                    tokens[-1]["raw"] += tok["raw"]
                    tokens[-1]["text"] += tok["text"]
                else:
                    tokens.append(tok)
                continue

            if src:
                break

        return tokens

    def _match_em_strong(self, src):
        # Match **bold** or *italic* or __bold__ or _italic_
        m = re.match(r'^(\*{1,2}|_{1,2})((?:\\[\s\S]|[^\\])+?)\1', src)
        if m:
            delim = m.group(1)
            text = m.group(2)
            raw = m.group(0)
            if len(delim) == 2:
                return {"type": "strong", "raw": raw, "text": text, "tokens": self.inline_tokens(text)}
            else:
                return {"type": "em", "raw": raw, "text": text, "tokens": self.inline_tokens(text)}
        return None


# ---------------------------------------------------------------------------
# Renderer & Parser
# ---------------------------------------------------------------------------

class Renderer:
    def __init__(self, options=None):
        self.options = options or {}
        self.parser = None

    def space(self, tok):
        return ""

    def code(self, tok):
        text = tok["text"]
        lang = tok.get("lang") or ""
        escaped = tok.get("escaped", False)
        
        lang_str = (lang.split()[0] if lang else "").strip()
        code_text = text if escaped else escape_html(text, encode=True)
        if not code_text.endswith('\n'):
            code_text += '\n'

        if lang_str:
            return f'<pre><code class="language-{escape_html(lang_str)}">{code_text}</code></pre>\n'
        return f'<pre><code>{code_text}</code></pre>\n'

    def blockquote(self, tok):
        content = self.parser.parse(tok["tokens"])
        return f'<blockquote>\n{content}</blockquote>\n'

    def html(self, tok):
        return tok["text"]

    def def_rule(self, tok):
        return ""

    def heading(self, tok):
        depth = tok["depth"]
        content = self.parser.parse_inline(tok["tokens"])
        return f'<h{depth}>{content}</h{depth}>\n'

    def hr(self, tok):
        return "<hr>\n"

    def list(self, tok):
        ordered = tok["ordered"]
        start = tok.get("start", "")
        items_html = "".join(self.listitem(item) for item in tok["items"])
        tag = "ol" if ordered else "ul"
        start_attr = f' start="{start}"' if ordered and start != 1 and start != "" else ""
        return f'<{tag}{start_attr}>\n{items_html}</{tag}>\n'

    def listitem(self, item):
        content = self.parser.parse(item["tokens"])
        if item.get("task"):
            checked_attr = 'checked="" ' if item.get("checked") else ''
            cb = f'<input {checked_attr}disabled="" type="checkbox"> '
            if content.startswith('<p>'):
                content = '<p>' + cb + content[3:]
            else:
                content = cb + content
        return f'<li>{content}</li>\n'

    def paragraph(self, tok):
        content = self.parser.parse_inline(tok["tokens"])
        return f'<p>{content}</p>\n'

    def table(self, tok):
        header_cells = "".join(self.tablecell(cell) for cell in tok["header"])
        header_html = f'<tr>\n{header_cells}</tr>\n'

        rows_html = ""
        for row in tok["rows"]:
            row_cells = "".join(self.tablecell(cell) for cell in row)
            rows_html += f'<tr>\n{row_cells}</tr>\n'

        tbody = f'<tbody>{rows_html}</tbody>' if rows_html else ''
        return f'<table>\n<thead>\n{header_html}</thead>\n{tbody}</table>\n'

    def tablecell(self, cell):
        content = self.parser.parse_inline(cell["tokens"])
        tag = "th" if cell.get("header") else "td"
        align = cell.get("align")
        align_attr = f' align="{align}"' if align else ''
        return f'<{tag}{align_attr}>{content}</{tag}>\n'

    def strong(self, tok):
        return f'<strong>{self.parser.parse_inline(tok["tokens"])}</strong>'

    def em(self, tok):
        return f'<em>{self.parser.parse_inline(tok["tokens"])}</em>'

    def codespan(self, tok):
        return f'<code>{escape_html(tok["text"], encode=True)}</code>'

    def br(self, tok):
        return "<br>"

    def del_rule(self, tok):
        return f'<del>{self.parser.parse_inline(tok["tokens"])}</del>'

    def link(self, tok):
        content = self.parser.parse_inline(tok["tokens"])
        href = clean_url(tok["href"])
        if href is None:
            return content
        title_attr = f' title="{escape_html(tok["title"])}"' if tok.get("title") else ''
        return f'<a href="{href}"{title_attr}>{content}</a>'

    def image(self, tok):
        alt = escape_html(tok.get("text", ""))
        href = clean_url(tok["href"])
        if href is None:
            return alt
        title_attr = f' title="{escape_html(tok["title"])}"' if tok.get("title") else ''
        return f'<img src="{href}" alt="{alt}"{title_attr}>'

    def text(self, tok):
        if "tokens" in tok and tok["tokens"]:
            return self.parser.parse_inline(tok["tokens"])
        if tok.get("escaped"):
            return tok["text"]
        return escape_html(tok["text"])


class Parser:
    def __init__(self, options=None):
        self.options = options or {}
        self.renderer = Renderer(self.options)
        self.renderer.parser = self

    def parse(self, tokens):
        out = []
        for tok in tokens:
            ttype = tok["type"]
            if ttype == "space":
                out.append(self.renderer.space(tok))
            elif ttype == "hr":
                out.append(self.renderer.hr(tok))
            elif ttype == "heading":
                out.append(self.renderer.heading(tok))
            elif ttype == "code":
                out.append(self.renderer.code(tok))
            elif ttype == "table":
                out.append(self.renderer.table(tok))
            elif ttype == "blockquote":
                out.append(self.renderer.blockquote(tok))
            elif ttype == "list":
                out.append(self.renderer.list(tok))
            elif ttype == "html":
                out.append(self.renderer.html(tok))
            elif ttype == "def":
                out.append(self.renderer.def_rule(tok))
            elif ttype == "paragraph":
                out.append(self.renderer.paragraph(tok))
            elif ttype == "text":
                out.append(self.renderer.text(tok))
        return "".join(out)

    def parse_inline(self, tokens, renderer=None):
        if renderer is None:
            renderer = self.renderer
        out = []
        for tok in tokens:
            ttype = tok["type"]
            if ttype == "escape":
                out.append(renderer.text(tok))
            elif ttype == "html":
                out.append(renderer.html(tok))
            elif ttype == "link":
                out.append(renderer.link(tok))
            elif ttype == "image":
                out.append(renderer.image(tok))
            elif ttype == "strong":
                out.append(renderer.strong(tok))
            elif ttype == "em":
                out.append(renderer.em(tok))
            elif ttype == "codespan":
                out.append(renderer.codespan(tok))
            elif ttype == "br":
                out.append(renderer.br(tok))
            elif ttype == "del":
                out.append(renderer.del_rule(tok))
            elif ttype == "text":
                out.append(renderer.text(tok))
        return "".join(out)


# ---------------------------------------------------------------------------
# Main API & CLI Entrypoint
# ---------------------------------------------------------------------------

def parse_markdown(src):
    lexer = Lexer()
    tokens = lexer.lex(src)
    parser = Parser()
    return parser.parse(tokens)

def main():
    # Set stdout encoding to UTF-8
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')
    
    input_text = sys.stdin.read()
    output_html = parse_markdown(input_text)
    sys.stdout.write(output_html)

if __name__ == "__main__":
    main()
