import os
import json
import shlex
import pprint
import asyncio
import tempfile
import functools
import subprocess

import synapse.exc as s_exc
import synapse.lib.cmd as s_cmd
import synapse.lib.cli as s_cli

ListHelp = '''
Lists all the keys underneath a particular key in the hive.

Syntax:
    hive ls [path]

Notes:
    If path is not specified, the root is listed.
'''

DelHelp = '''
Deletes a key in the cell's hive.

Syntax:
    hive rm {path}

Notes:
    Delete will recursively delete all subkeys underneath path if they exist.
'''

ModHelp = '''
Edits or creates a key in the cell's hive.

Syntax:
    hive edit {path} ({value} | --editor | -f {filename})

Notes:
    One may specify the value directly on the command line, from a file, or use an editor.  For the --editor option,
    the environment variable VISUAL or EDITOR must be set.
'''

def tuplify(obj):
    if isinstance(obj, list):
        return tuple(map(tuplify, obj))
    if isinstance(obj, dict):
        return {k: tuplify(v) for k, v in obj.items()}
    return obj

class HiveCmd(s_cli.Cmd):
    '''
Manipulates values in a cell's Hive.

A Hive is a hierarchy persistent storage mechanism typically used for configuration data.
'''
    _cmd_name = 'hive'

    _cmd_syntax = (
        ('line', {'type': 'glob'}),
    )

    def _make_argparser(self):

        parser = s_cmd.Parser(prog='hive', outp=self, description=self.__doc__)

        subparsers = parser.add_subparsers(title='subcommands', required=True, dest='cmd',
                                           parser_class=functools.partial(s_cmd.Parser, outp=self))

        parser_ls = subparsers.add_parser('ls', help="List entries in the hive", usage=ListHelp)
        parser_ls .add_argument('path', nargs='?', help='Hive path')

        parser_get = subparsers.add_parser('get', help="Get any entry in the hive", usage=ListHelp)
        parser_get.add_argument('path', help='Hive path')

        parser_rm = subparsers.add_parser('rm', help='Delete a key in the hive', usage=DelHelp)
        parser_rm.add_argument('path', help='Hive path')

        parser_edit = subparsers.add_parser('edit', help='Sets/creates a key', usage=ModHelp)
        parser_edit.add_argument('path', help='Hive path')
        group = parser_edit.add_mutually_exclusive_group(required=True)
        group.add_argument('value', nargs='?', help='Value to set')
        group.add_argument('--editor', default=False, action='store_true',
                           help='Opens an editor to set the value')
        group.add_argument('--file', '-f', help='Copies the contents of the file to the path')

        return parser

    async def runCmdOpts(self, opts):
        line = opts.get('line')
        if line is None:
            self.printf(self.__doc__)
            return

        core = self.getCmdItem()

        try:
            opts = self._make_argparser().parse_args(shlex.split(line))
        except s_exc.ParserExit:
            return

        handlers = {
            'ls': self._handle_ls,
            'rm': self._handle_rm,
            'get': self._handle_get,
            'edit': self._handle_edit,
        }
        await handlers[opts.cmd](core, opts)

    @staticmethod
    def parsepath(path):
        return path.split('/')

    async def _handle_ls(self, core, opts):
        path = self.parsepath(opts.path) if opts.path is not None else None
        keys = await core.hivels(path=path)
        if keys is None:
            self.printf('Path not found')
            return
        for key in keys:
            self.printf(key)

    async def _handle_get(self, core, opts):
        path = self.parsepath(opts.path)
        valu = await core.hivegetkey(path)
        if valu is None:
            self.printf(f'{opts.path} not present')
            return
        self.printf(f'{opts.path}: {pprint.pformat(valu)}')

    async def _handle_rm(self, core, opts):
        path = self.parsepath(opts.path)
        await core.hivepopkey(path)

    async def _handle_edit(self, core, opts):
        path = self.parsepath(opts.path)

        if opts.value is not None:
            data = json.loads(opts.value)
            await core.hiveputkey(path, data)
            return
        elif opts.file is not None:
            with open(opts.file) as fh:
                data = json.loads(fh.read())
                await core.hiveputkey(path, data)
                return

        editor = os.getenv('VISUAL', (os.getenv('EDITOR', None)))
        if editor is None:
            self.printf('Environment variable VISUAL or EDITOR must be set for --editor')
            return
        tnam = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as fh:
                old_valu = await core.hivegetkey(path)
                if old_valu is not None:
                    try:
                        js = json.dumps(old_valu, indent=4)
                    except (ValueError, TypeError):
                        self.printf('Value is not JSON-encodable, therefore not editable.')
                        return
                    fh.write(js)
                tnam = fh.name
            while True:
                retn = subprocess.call(f'{editor} {tnam}', shell=True)
                if retn != 0:
                    self.printf('Editor failed with non-zero code.  Aborting.')
                    return
                with open(tnam) as fh:
                    bytz = fh.read()
                    if len(bytz) == 0:
                        self.printf('Empty file.  Not writing key.')
                        return
                    try:
                        valu = json.loads(bytz)
                    except json.JSONDecodeError:
                        self.printf('JSON decode failure.  Reopening.')
                        await asyncio.sleep(1)
                        continue
                    # We lose the tuple/list distinction in the telepath round trip, so tuplify everything to compare
                    if tuplify(valu) == old_valu:
                        self.printf('Valu not changed.  Not writing key.')
                        return
                    await core.hiveputkey(path, valu)
                    break

        finally:
            if tnam is not None:
                os.unlink(tnam)
