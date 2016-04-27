# -*- coding: utf-8 -*-
"""API to install/remove all themysto nbextensions and server extensions."""

from __future__ import print_function

import os

import psutil
from notebook.notebookapp import NotebookApp
from traitlets.config import Config
from traitlets.config.manager import BaseJSONConfigManager

import themysto

try:
    # notebook >= 4.2.0
    from notebook.nbextensions import _get_config_dir
except ImportError:
    # notebook < 4.2.0
    from themysto.notebook_shim import _get_config_dir


class NotebookRunningError(Exception):
    pass


def notebook_is_running():
    """Return true if a notebook process appears to be running."""
    for p in psutil.process_iter():
        # p.name() can throw exceptions due to zombie processes on Mac OS X, so
        # ignore psutil.ZombieProcess
        # (See https://code.google.com/p/psutil/issues/detail?id=428)

        # It isn't enough to search just the process name, we have to
        # search the process command to see if jupyter-notebook is running.

        # Checking the process command can cause an AccessDenied exception to
        # be thrown for system owned processes, ignore those as well
        try:
            # use lower, since python may be Python, e.g. on OSX
            if ('python' or 'jupyter') in p.name().lower():
                for arg in p.cmdline():
                    # the missing k is deliberate!
                    # The usual string 'jupyter-notebook' can get truncated.
                    if 'jupyter-noteboo' in arg:
                        return True
        except (psutil.ZombieProcess, psutil.AccessDenied):
            pass
        return False


def update_config_list(config, list_key, values, insert):
    """Add or remove items as required to/from a config value which is a list.

    This exists in order to avoid clobbering values other than those which we
    wish to add/remove
    """
    section, list_key = list_key.split('.')
    config[section] = config.get(section, Config())
    conf_list = config[section].setdefault(list_key, [])
    list_alteration_method = 'append' if insert else 'remove'
    for val in values:
        if (val in conf_list) != insert:
            getattr(conf_list, list_alteration_method)(val)
    if not insert:
        # remove empty list
        if len(conf_list) == 0:
            config[section].pop(list_key)
        # remove empty section
        if len(config[section]) == 0:
            config.pop(section)


def toggle_install(install, user=False, sys_prefix=False, config_dir=None,
                   logger=None):
    """Install or remove all themysto nbextensions and server extensions."""
    if notebook_is_running():
        raise NotebookRunningError(
            'Cannot configure while the Jupyter notebook server is running')

    user = False if sys_prefix else user
    if config_dir is None:
        config_dir = _get_config_dir(user=user, sys_prefix=sys_prefix)

    verb = 'Installing' if install else 'Uninstalling'
    if logger:
        logger.info('{} themysto'.format(verb))

    # -------------------------------------------------------------------------
    # notebook config
    cm = BaseJSONConfigManager(config_dir=config_dir)
    config_basename = 'jupyter_notebook_config'
    config = cm.get(config_basename)
    config.setdefault('version', 1)  # avoid warnings about unset version
    if logger:
        logger.info(
            u'- Editing config: {}'.format(cm.file_name(config_basename)))

    # server extensions
    verb = 'Enabling' if install else 'Disabling'
    if logger:
        logger.info('--  {} server extensions'.format(verb))

    if hasattr(NotebookApp, 'nbserver_extensions'):
        server_extensions = config.setdefault(
            'NotebookApp', {}).setdefault('nbserver_extensions', {})
    else:
        server_extensions = config.setdefault(
            'NotebookApp', {}).setdefault('server_extensions', [])

    for servext in themysto._jupyter_server_extension_paths():
        import_name = servext['module']
        if logger:
            logger.info(u"---   {}: {}".format(verb, import_name))
        if hasattr(NotebookApp, 'nbserver_extensions'):
            server_extensions[import_name] = install
        else:
            if install:
                if import_name not in server_extensions:
                    server_extensions.append(import_name)
            else:
                while import_name in server_extensions:
                    server_extensions.pop(server_extensions.index(import_name))

    # nbextensions paths
    if logger:
        logger.info('--  Configuring nbextensions paths')
    update_config_list(config, 'NotebookApp.extra_nbextensions_path', [
        os.path.join(os.path.dirname(themysto.__file__), 'nbextensions'),
        os.path.join(
            os.path.dirname(themysto.__file__), 'nbextensions_configurator',
            'static'),
    ], install)

    # write config for notebook app
    cm.update(config_basename, config)

    # -------------------------------------------------------------------------
    # nbconvert config
    cm = BaseJSONConfigManager(config_dir=config_dir)
    config_basename = 'jupyter_nbconvert_config'
    config = cm.get(config_basename)
    config.setdefault('version', 1)  # avoid warnings about unset version
    if logger:
        logger.info(
            u'- Editing config: {}'.format(cm.file_name(config_basename)))

    # Set extra template path, pre- and post-processors for nbconvert
    if logger:
        logger.info('--  Configuring nbconvert template path')
    # our templates directory
    update_config_list(config, 'Exporter.template_path', [
        '.',
        os.path.join(os.path.dirname(themysto.__file__), 'templates'),
    ], install)
    # our preprocessors
    if logger:
        logger.info('--  Configuring nbconvert preprocessors')
    update_config_list(config, 'Exporter.preprocessors', [
        'themysto.preprocessors.CodeFoldingPreprocessor',
        'themysto.preprocessors.PyMarkdownPreprocessor',
    ], install)
    # our postprocessor class
    if logger:
        logger.info('--  Configuring nbconvert postprocessor_class')
    if install:
        config.setdefault('NbConvertApp', {})['postprocessor_class'] = (
            'themysto.postprocessors.EmbedPostProcessor')
    else:
        nbconvert_conf = config.get('NbConvertApp', {})
        if (nbconvert_conf.get('postprocessor_class') ==
                'themysto.postprocessors.EmbedPostProcessor'):
            nbconvert_conf.pop('postprocessor_class', None)
            if len(nbconvert_conf) < 1:
                config.pop('NbConvertApp')
    # write config for nbconvert app
    cm.update(config_basename, config)


def install(user=False, sys_prefix=False, config_dir=None, logger=None):
    """Edit jupyter config to make themysto extensions available."""
    return toggle_install(
        True, user=user, config_dir=config_dir, logger=logger)


def uninstall(user=False, sys_prefix=False, config_dir=None, logger=None):
    """Edit jupyter config to remove themysto extension availability."""
    return toggle_install(
        False, user=user, config_dir=config_dir, logger=logger)
