"""Every controller that turns an exception into the user message
"Error applying <operation>: <reason>" must also log it with
logger.exception, so the log file has the full traceback. Before, only the
one-line message existed and a reported error could not be diagnosed."""
import ast
import pathlib

CONTROLLERS = pathlib.Path(__file__).resolve().parent.parent / 'src' / 'controllers'


def _handlers_returning_error_message(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            for stmt in node.body:
                if (isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Tuple)
                        and 'Error applying' in ast.unparse(stmt.value)):
                    yield node
                    break


def test_every_error_applying_message_is_also_logged():
    missing, checked = [], 0
    for path in CONTROLLERS.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for handler in _handlers_returning_error_message(tree):
            checked += 1
            if 'logger.exception' not in ast.unparse(handler):
                missing.append(f'{path.name}:{handler.lineno}')
    assert checked >= 9
    assert not missing, f'not logged: {missing}'
