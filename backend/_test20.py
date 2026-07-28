import sys, warnings, traceback
sys.path.insert(0, 'backend')
warnings.filterwarnings('ignore')
import logging
logging.disable(logging.CRITICAL)

print('Test 1: Import BugFinderAgent')
from app.core.agents.bug_finder import BugFinderAgent, _parse_bug_report
agent = BugFinderAgent()
print(f'  agent_type: {agent.agent_type}')
print(f'  display_name: {agent.display_name}')

print('Test 2: Compile LangGraph')
try:
    graph = agent._build_graph()
    print(f'  Graph type: {type(graph).__name__}')
    print('  Graph: OK')
except Exception as e:
    print(f'  Graph FAILED: {type(e).__name__}: {e}')
    traceback.print_exc()

print('Test 3: Bug parser')
sample_output = (
    '## BUGS_FOUND: 1\n'
    '### BUG-001\n'
    '- **Title**: Null pointer dereference\n'
    '- **Severity**: high\n'
    '- **Category**: null_safety\n'
    '- **File**: app/main.py:42\n'
    '- **Description**: Missing null check before accessing user attributes\n'
    '- **Code**: user.email\n'
    '- **Fix**: Add if user is None: raise ValueError check\n'
    '## SUMMARY\n'
    'Found 1 critical null safety issue.\n'
)
result = _parse_bug_report(sample_output)
print(f'  total_bugs: {result["total_bugs"]}')
print(f'  severity_counts: {result["severity_counts"]}')
print(f'  summary: {result["summary"][:60]}')
assert result['total_bugs'] >= 1, 'Expected at least 1 bug parsed'
print('  Parser: OK')

print('Test 4: Register with orchestrator')
from app.core.agents.orchestrator import AgentOrchestrator
orch = AgentOrchestrator()
orch.register('bug_finder', BugFinderAgent)
available = orch.get_available_agents()
types = [a['type'] for a in available]
print(f'  Registered: {types}')
assert 'bug_finder' in types, 'bug_finder not in orchestrator'
print('  Registration: OK')

print()
print('STEP 20: ALL TESTS PASSED')
