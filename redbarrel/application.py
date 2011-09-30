""" Application database

    :copyright: Copyright 2011 by the RedBarrel team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""
import os
import copy

from redbarrel import logger
from redbarrel.dsl.parser import build_ast
from redbarrel.dsl.runners import resolve_runner, get_runner_names
from redbarrel.dsl.mapper import WebMapper


_MEDIA = os.path.join(os.path.dirname(__file__), 'media')
_PREFIXES = ['python', 'file', 'proxy', 'directory']
_NONPATH = ('global', 'type', 'worker', 'arbiter', 'root')
_ROOT = os.path.join(os.path.dirname(__file__), 'apps')


# XXX Need to sync on each edit, in the FS

class RedBarrelApplication(object):
    def __init__(self, rbr, context=None):
        if os.path.exists(rbr):
            self.root = os.path.dirname(rbr)
            with open(rbr) as f:
                self.rbr_content = f.read()
        else:
            self.root = os.getcwd()
            self.rbr_content = rbr
        self.root_path = ''
        self.context = context
        self._load_rbr()
        self._commitmapper()

    def sync(self):
        root = os.path.join(_ROOT, self.root_path.lstrip('/'))
        if not os.path.exists(root):
            os.mkdir(root)
        # saving the RBR file
        rbr = os.path.join(root, 'definitions.rbr')
        with open(rbr, 'w') as f:
            # XXX should be str all the time
            if isinstance(self.rbr_content, unicode):
                self.rbr_content = self.rbr_content.encode('utf-8')
            f.write(self.rbr_content)

    def _commitmapper(self):
        self._rbr_content = None
        self._ast = None
        self._globs = None
        self._types = None
        self._mapper = None
        self.sync()

    def _backupmapper(self):
        self._rbr_content = self.rbr_content
        self._ast = self.ast
        self._globs = self.globs
        self._types = self.types
        self._mapper = self.mapper

    def _rollbackmapper(self):
        if self._rbr_content is None:
            raise ValueError("Nothing to rollback")
        self.rbr_content = self._rbr_content
        self.ast = self._ast
        self.globs = self._globs
        self.types = self._types
        self.mapper = self._mapper

    def _load_rbr(self, load_ast=True):
        if load_ast:
            self.ast = build_ast(self.rbr_content)
            # looking for the root path
            for definition in self.ast:
                if definition.type != 'root':
                    continue
                self.root_path = definition.value
                break

        self.globs = self._create_globs()
        self.types = self._create_types()
        self.mapper = WebMapper(self)

    def _resolve_def(self, value, *args, **kw):
        if not isinstance(value, str):
            return value
        prefixed = value.split(':', 1)
        if prefixed[0] not in get_runner_names():
            return value

        res = resolve_runner(value, self.root)(*args, **kw)
        if value == res:
            raise ImportError(value)
        else:
            value = res
        return value

    def _create_types(self):
        # reads the types definitions and loads them
        types = {}
        logger.info('Initializing types...')
        for definition in self.ast:
            if definition.type != 'type':
                continue
            name = definition.left
            types[name] = self._resolve_def(definition.right)
        return types

    def _create_globs(self):
        # reads the globs definitions and loads them
        globs = {}
        logger.info('Initializing globs...')
        for definition in self.ast:
            if definition.type != 'global':
                continue

            name = definition.left
            value = definition.right.value
            globs[name] = self._resolve_def(value,
                                            copy.copy(globs))
        return globs

    def generate(self):
        logger.info('Generating the Web App...')
        for definition in self.ast:
            type_ = definition.type
            if type_ == 'meta':
                self.mapper.set_options(definition.value)
                continue
            elif type_ in _NONPATH:
                continue

            name = definition.left
            args = definition.right
            #print name
            #print args
            #if len(definition) > 2:
            #    args = definition[2]
            #else:
            #    args = []
            self.mapper.add(name, args)
        logger.info('...ready')
        logger.info('')

    def __call__(self, request):
        return self.mapper(request)

    def get_options(self):
        return self.mapper.options

    def set_options(self, options):
        self.mapper.set_options(options)

    def add_def(self, name, definition):
        self.mapper.add(name, definition)

    def del_def(self, name):
        new_ast = []
        for definition in self.ast:
            if definition[0] == 'def' and definition[1] == name:
                continue
            new_ast.append(definition)

        if len(new_ast) < len(self.ast):
            self.ast = new_ast
            self._load_rbr(load_ast=False)
            self.generate()

    def add_content(self, content):
        # syntax check
        try:
            ast = build_ast(content)
        except Exception, e:
            raise SyntaxError(e)

        if ast is None:
            raise SyntaxError()

        # actual ast change
        self._backupmapper()
        try:
            self.rbr_content += '\n%s' % content
            self._load_rbr()
            self.generate()
            self._commitmapper()
        except Exception:
            self._rollbackmapper()
            raise

    def get_hooks(self):
        return self.mapper._hooks

    def get_root(self):
        return self.mapper.root_path