import fnmatch
import importlib
import logging
import os
import traceback

from pool_engine import PoolEngine


class Plugins:

    plugins_list = []

    def __init__(self):
        plugin_names = []
        plugin_folder = 'plugins'
        if not os.path.isdir(plugin_folder):
            return
        files_list = os.listdir(plugin_folder)
        pattern = "*.py"
        for entry in files_list:
            if fnmatch.fnmatch(entry, pattern):
                plugin = entry.split(".")[0]
                try:
                    meta = importlib.import_module(f'plugins.{plugin}').Meta
                    meta_info = meta.meta_info
                    if meta_info['type'] == 'vote':
                        PoolEngine.post_vote_list.update(meta.vote_list)
                    importlib.import_module(f"plugins.{plugin}").Handler()
                    plugin_names.append(meta_info['name'])
                    self.plugins_list.append(plugin)
                except Exception as e:
                    logging.error(f'Module "{entry}" is invalid!\n{e}')
                    logging.error(traceback.format_exc())
        print("Loaded plugins: " + ", ".join(plugin_names))
