import fnmatch
import importlib
import logging
import os
import traceback

from packaging import version

from utils import data
from poll_engine import PoolEngine

class Plugins:

    def __init__(self):
        plugin_names = []
        plugin_folder = "plugins"
        if data.path:
            plugin_folder = data.path[:-1] + '_plugins'
        if not os.path.isdir(plugin_folder):
            return
        files_list = os.listdir(plugin_folder)
        pattern = "*.py"
        for entry in files_list:
            if fnmatch.fnmatch(entry, pattern):
                if os.path.isdir(f"{plugin_folder}/{entry}"):
                    continue
                plugin = entry.split(".")[0]
                try:
                    meta = importlib.import_module(f'{plugin_folder}.{plugin}').Meta
                    meta_info = meta.meta_info
                    if any([version.parse(meta_info['version-min']) > version.parse(data.VERSION),
                            version.parse(meta_info['version-max']) < version.parse(data.VERSION)]):
                        logging.error(f'Module "{entry}" need bot version {meta_info["version-min"]} '
                                      f'- {meta_info["version-max"]}, current is {data.VERSION}')
                        continue
                    if meta_info['type'] == 'vote':
                        PoolEngine.post_vote_list.update(meta.vote_list)
                    importlib.import_module(f"{plugin_folder}.{plugin}").Handler()
                    plugin_names.append(meta_info['name'])
                except Exception as e:
                    logging.error(f'Module "{entry}" is invalid! {e}')
                    logging.error(traceback.format_exc())
        if plugin_names:
            logging.info("Loaded plugins: " + ", ".join(plugin_names))
            data.plugins = plugin_names
