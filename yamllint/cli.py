# Copyright (C) 2016 Adrien Vergé
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import locale
import os
import platform
import sys

from yamllint import APP_DESCRIPTION, APP_NAME, APP_VERSION
from yamllint import linter
from yamllint.config import YamlLintConfig, YamlLintConfigError
from yamllint.formatters import colored, github, parsable, standard
from yamllint.linter import PROBLEM_LEVELS


def find_files_recursively(items, conf):
    for item in items:
        if os.path.isdir(item):
            for root, dirnames, filenames in os.walk(item):
                for f in filenames:
                    filepath = os.path.join(root, f)
                    if conf.is_yaml_file(filepath):
                        yield filepath
        else:
            yield item


def supports_color():
    supported_platform = not (platform.system() == 'Windows' and not
                              ('ANSICON' in os.environ or
                               ('TERM' in os.environ and
                                os.environ['TERM'] == 'ANSI')))
    return (supported_platform and
            hasattr(sys.stdout, 'isatty') and sys.stdout.isatty())


def show_results(results, args_format, no_warn):
    if args_format == 'auto':
        if ('GITHUB_ACTIONS' in os.environ and
                'GITHUB_WORKFLOW' in os.environ):
            args_format = 'github'
        elif supports_color():
            args_format = 'colored'

    if args_format == 'parsable':
        return parsable.format_results(results, no_warn)
    elif args_format == 'github':
        return github.format_results(results, no_warn)
    elif args_format == 'colored':
        return colored.format_results(results, no_warn)
    else:
        return standard.format_results(results, no_warn)


def find_project_config_filepath(path='.'):
    for filename in ('.yamllint', '.yamllint.yaml', '.yamllint.yml'):
        filepath = os.path.join(path, filename)
        if os.path.isfile(filepath):
            return filepath

    if os.path.abspath(path) == os.path.abspath(os.path.expanduser('~')):
        return None
    if os.path.abspath(path) == os.path.abspath(os.path.join(path, '..')):
        return None
    return find_project_config_filepath(path=os.path.join(path, '..'))


def run(argv=None):
    parser = argparse.ArgumentParser(prog=APP_NAME,
                                     description=APP_DESCRIPTION)
    files_group = parser.add_mutually_exclusive_group(required=True)
    files_group.add_argument('files', metavar='FILE_OR_DIR', nargs='*',
                             default=(),
                             help='files to check')
    files_group.add_argument('-', action='store_true', dest='stdin',
                             help='read from standard input')
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument('-c', '--config-file', dest='config_file',
                              action='store',
                              help='path to a custom configuration')
    config_group.add_argument('-d', '--config-data', dest='config_data',
                              action='store',
                              help='custom configuration (as YAML source)')
    parser.add_argument('--list-files', action='store_true', dest='list_files',
                        help='list files to lint and exit')
    parser.add_argument('-f', '--format',
                        choices=('parsable', 'standard', 'colored', 'github',
                                 'auto'),
                        default='auto', help='format for parsing output')
    parser.add_argument('-s', '--strict',
                        action='store_true',
                        help='return non-zero exit code on warnings '
                             'as well as errors')
    parser.add_argument('--no-warnings',
                        action='store_true',
                        help='output only error level problems')
    parser.add_argument('-v', '--version', action='version',
                        version='{} {}'.format(APP_NAME, APP_VERSION))

    args = parser.parse_args(argv)

    if 'YAMLLINT_CONFIG_FILE' in os.environ:
        user_global_config = os.path.expanduser(
            os.environ['YAMLLINT_CONFIG_FILE'])
    # User-global config is supposed to be in ~/.config/yamllint/config
    elif 'XDG_CONFIG_HOME' in os.environ:
        user_global_config = os.path.join(
            os.environ['XDG_CONFIG_HOME'], 'yamllint', 'config')
    else:
        user_global_config = os.path.expanduser('~/.config/yamllint/config')

    project_config_filepath = find_project_config_filepath()
    try:
        if args.config_data is not None:
            if args.config_data != '' and ':' not in args.config_data:
                args.config_data = 'extends: ' + args.config_data
            conf = YamlLintConfig(content=args.config_data)
        elif args.config_file is not None:
            conf = YamlLintConfig(file=args.config_file)
        elif project_config_filepath:
            conf = YamlLintConfig(file=project_config_filepath)
        elif os.path.isfile(user_global_config):
            conf = YamlLintConfig(file=user_global_config)
        else:
            conf = YamlLintConfig('extends: default')
    except YamlLintConfigError as e:
        print(e, file=sys.stderr)
        sys.exit(-1)

    if conf.locale is not None:
        locale.setlocale(locale.LC_ALL, conf.locale)

    if args.list_files:
        for file in find_files_recursively(args.files, conf):
            if not conf.is_file_ignored(file):
                print(file)
        sys.exit(0)

    results = {}
    for file in find_files_recursively(args.files, conf):
        filepath = file[2:] if file.startswith('./') else file
        try:
            with open(file, newline='') as f:
                problems = linter.run(f, conf, filepath)
        except OSError as e:
            print(e, file=sys.stderr)
            sys.exit(-1)
        results[filepath] = problems

    # read yaml from stdin
    if args.stdin:
        try:
            problems = linter.run(sys.stdin, conf, '')
        except OSError as e:
            print(e, file=sys.stderr)
            sys.exit(-1)
        results['stdin'] = problems

    max_level = show_results(results, args_format=args.format, no_warn=args.no_warnings)

    if max_level == PROBLEM_LEVELS['error']:
        return_code = 1
    elif max_level == PROBLEM_LEVELS['warning']:
        return_code = 2 if args.strict else 0
    else:
        return_code = 0

    sys.exit(return_code)
