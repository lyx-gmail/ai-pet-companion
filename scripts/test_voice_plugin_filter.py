import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class PluginFilterTests(unittest.TestCase):
    def test_every_caller_defaults_to_selected_baseline_plugins(self):
        path=Path(__file__).resolve().parents[1]/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/plugins_func/loadplugins.py'
        spec=importlib.util.spec_from_file_location('pet_plugin_loader_check',path)
        module=importlib.util.module_from_spec(spec)
        logger=ModuleType('config.logger'); logger.setup_logging=lambda: None
        with patch.dict(sys.modules,{'config.logger':logger}): spec.loader.exec_module(module)
        with patch.object(module.pkgutil,'iter_modules',return_value=[(None,'handle_exit_intent',False),(None,'unused_plugin',False),(None,'play_music',False)]), patch.object(module.importlib,'import_module',return_value=SimpleNamespace(__path__=['fixture'])) as importer:
            module.auto_import_modules('fixture')
        self.assertEqual([call.args[0] for call in importer.call_args_list],['fixture','fixture.handle_exit_intent','fixture.play_music'])


if __name__=='__main__': unittest.main()
