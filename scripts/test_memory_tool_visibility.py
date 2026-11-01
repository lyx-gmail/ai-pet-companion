import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class VisibilityTests(unittest.TestCase):
    def test_internal_memory_tools_remain_callable_but_are_not_offered_to_model(self):
        path=Path(__file__).resolve().parents[1]/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/core/providers/tools/device_mcp/mcp_executor.py'
        tree=ast.parse(path.read_text(encoding='utf-8'))
        method=next(n for c in tree.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='get_tools')
        body=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),method],type_ignores=[])
        namespace={'ToolDefinition':lambda **args:args,'ToolType':SimpleNamespace(DEVICE_MCP=1)}
        exec(compile(ast.fix_missing_locations(body),str(path),'exec'),namespace)
        descriptors=[{'function':{'name':name}} for name in ('self_pet_get_state','self_pet_memory_offer','self_pet_memory_status')]
        client=SimpleNamespace(get_available_tools=lambda:descriptors)
        result=namespace['get_tools'](SimpleNamespace(conn=SimpleNamespace(mcp_client=client)))
        self.assertEqual(list(result),['self_pet_get_state'])
        self.assertEqual(len(client.get_available_tools()),3)


if __name__=='__main__': unittest.main()
