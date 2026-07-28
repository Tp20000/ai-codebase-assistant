import logging
import re
from typing import Optional, Any

logger = logging.getLogger(__name__)
TREE_SITTER_AVAILABLE = False
try:
    import tree_sitter
    from tree_sitter import Language, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    pass

GRAMMAR_PACKAGES = {
    'python': 'tree_sitter_python',
    'javascript': 'tree_sitter_javascript',
    'typescript': 'tree_sitter_typescript',
    'java': 'tree_sitter_java',
    'go': 'tree_sitter_go',
    'rust': 'tree_sitter_rust',
}
_language_cache: dict = {}

def _load_language(lang_name):
    if lang_name in _language_cache:
        return _language_cache[lang_name]
    if not TREE_SITTER_AVAILABLE:
        return None
    pkg = GRAMMAR_PACKAGES.get(lang_name)
    if not pkg:
        _language_cache[lang_name] = None
        return None
    try:
        mod = __import__(pkg)
        lang = Language(mod.language()) if hasattr(mod, 'language') else None
        _language_cache[lang_name] = lang
        return lang
    except Exception as e:
        _language_cache[lang_name] = None
        return None

def _fn(name, ls, le, params=None, ret=None, method=False, cls=None):
    return {'name': name, 'line_start': ls, 'line_end': le,
            'params': params or [], 'return_type': ret, 'docstring': None,
            'is_method': method, 'class_name': cls, 'decorators': []}

def _cl(name, ls, le, bases=None, methods=None):
    return {'name': name, 'line_start': ls, 'line_end': le,
            'base_classes': bases or [], 'methods': methods or [], 'docstring': None}

def _im(module, names=None, line=0):
    return {'module': module, 'names': names or [], 'alias': None, 'line': line}

class CodeParser:
    def parse(self, source, language, file_path=''):
        if not source or not source.strip():
            return {'functions': [], 'classes': [], 'imports': [], 'parse_method': 'none', 'error': None}
        lang = (language or 'unknown').lower().strip()
        try:
            r = self._re_parse(source, lang)
            r['parse_method'] = 'regex'
            r['error'] = None
            return r
        except Exception as e:
            return {'functions': [], 'classes': [], 'imports': [], 'parse_method': 'failed', 'error': str(e)}

    def _re_parse(self, source, language):
        fns, cls_list, ims = [], [], []
        if language == 'python':
            for m in re.finditer(r'^( *)def (\w+)\s*\(([^)]*)\)(?:\s*->\s*([^:]+))?:', source, re.MULTILINE):
                ln = source[:m.start()].count('\n') + 1
                raw = m.group(3) or ''
                params = [p.strip().split(':')[0].split('=')[0].strip() for p in raw.split(',') if p.strip() and p.strip() not in ('self', 'cls')]
                fns.append(_fn(m.group(2), ln, ln, params=params, ret=m.group(4).strip() if m.group(4) else None, method=len(m.group(1)) > 0))
            for m in re.finditer(r'^class (\w+)(?:\(([^)]*)\))?:', source, re.MULTILINE):
                ln = source[:m.start()].count('\n') + 1
                bases = [b.strip() for b in (m.group(2) or '').split(',') if b.strip()]
                cls_list.append(_cl(m.group(1), ln, ln, bases=bases))
            for m in re.finditer(r'^(?:from ([\w.]+) import (.*)|import ([\w., ]+))', source, re.MULTILINE):
                ln = source[:m.start()].count('\n') + 1
                if m.group(1):
                    ims.append(_im(m.group(1), names=[n.strip() for n in m.group(2).split(',')], line=ln))
                elif m.group(3):
                    for mod in m.group(3).split(','):
                        ims.append(_im(mod.strip(), line=ln))
        elif language in ('javascript', 'typescript'):
            for m in re.finditer(r'(?:function (\w+)|(?:const|let|var) (\w+)\s*=\s*(?:async\s*)?\()', source, re.MULTILINE):
                ln = source[:m.start()].count('\n') + 1
                fns.append(_fn(m.group(1) or m.group(2) or '<anon>', ln, ln))
            for m in re.finditer(r'class (\w+)', source, re.MULTILINE):
                ln = source[:m.start()].count('\n') + 1
                cls_list.append(_cl(m.group(1), ln, ln))
        elif language == 'java':
            for m in re.finditer(r'(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\(', source, re.MULTILINE):
                ln = source[:m.start()].count('\n') + 1
                fns.append(_fn(m.group(1), ln, ln, method=True))
            for m in re.finditer(r'(?:public\s+)?class (\w+)', source, re.MULTILINE):
                ln = source[:m.start()].count('\n') + 1
                cls_list.append(_cl(m.group(1), ln, ln))
        else:
            for m in re.finditer(r'\bfunc(?:tion)?\s+(\w+)\s*\(', source, re.MULTILINE):
                ln = source[:m.start()].count('\n') + 1
                fns.append(_fn(m.group(1), ln, ln))
        return {'functions': fns, 'classes': cls_list, 'imports': ims}
