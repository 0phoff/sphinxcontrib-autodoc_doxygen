from lxml import etree as ET

import sphinx
import sphinx.ext
import sphinx.ext.autosummary
from sphinx.util import rpartition
from sphinx.ext.autodoc import ClassDocumenter, Documenter, AutoDirective, py_ext_sig_re

from . import get_doxygen_root
from .xmlutils import DoxygenNodeVisitor


class DoxygenDocumenter(Documenter):
    def parse_name(self):
        """Determine what module to import and what attribute to document.
        Returns True and sets *self.modname*, *self.objpath*, *self.fullname*,
        *self.args* and *self.retann* if parsing and resolving was successful.
        """
        try:
            explicit_modname, path, base, args, retann = \
                py_ext_sig_re.match(self.name).groups()
        except AttributeError:
            self.directive.warn('invalid signature for auto%s (%r)' %
                                (self.objtype, self.name))
            return False

        if explicit_modname is not None:
            modname = explicit_modname[:-2]
            parents = path and path.rstrip('.').split('.') or []
        else:
            modname = None
            parents = []

        self.modname, self.objpath = \
                    self.resolve_name(modname, parents, path, base)

        self.fullname = self.name
        # print('%s parse_name' % type(self))
        # print('  setting self.modname', self.modname)
        # print('  setting self.objpath', self.objpath)
        # print('  setting self.fullname', self.fullname)
        return True

    def format_name(self):
        return self.fullname

    def import_object(self):
        """Import the object given by *self.modname* and *self.objpath* and set
        it as *self.object*.
        Returns True if successful, False if an error occurred.
        """
        pass

    def add_directive_header(self, sig):
        """Add the directive header and options to the generated content."""
        domain = getattr(self, 'domain', 'cpp')
        directive = getattr(self, 'directivetype', self.objtype)
        name = self.format_name()
        sourcename = self.get_sourcename()
        self.add_line(u'.. %s:%s:: %s%s' % (domain, directive, name, sig),
                      sourcename)




class DoxygenClassDocumenter(DoxygenDocumenter):
    objtype = 'doxyclass'
    directivetype = 'class'
    domain = 'cpp'
    priority = 100

    @classmethod
    def can_document_member(cls, member, membername, isattr, parent):
        # print('can_document_member', member, membername, isattr, parent)
        return False

    def import_object(self):
        xpath_query = './/compoundname[text()="%s"]/..' % self.fullname
        #print('import_object')
        #print('  xpath', xpath_query)
        self.object = get_doxygen_root().xpath(xpath_query)[0]
        #print('  setting self.object', self.object)
        return True

    def resolve_name(self, modname, parents, path, base):
        #print('DoxygenClassDocumenter.resolve_name')
        #print('  ', modname, parents, path, base)
        return modname, parents + [base]

    def format_signaure(self):
        return ''

    def get_doc(self, encoding):
        detaileddescription = self.object.find('detaileddescription')
        doc = [DoxygenNodeVisitor().generic_visit(detaileddescription).lines]
        return doc

    def get_object_members(self, want_all):
        members = self.object.findall('.//sectiondef[@kind="public-func"]/memberdef[@kind="function"]')
        names = [m.find('name').text for m in members]
        return True, zip(names, members)

    def filter_members(self, members, want_all):
        ret = []
        for (membername, member) in members:
            ret.append((membername, member, False))
        return ret

    def document_members(self, members, all_members=False):
        super().document_members(members)
        # print('\n'.join(self.directive.result))


class DoxygenMethodDocumenter(DoxygenDocumenter):
    objtype = 'doxymethod'
    directivetype = 'function'
    domain = 'cpp'
    priority = 100

    @classmethod
    def can_document_member(cls, member, membername, isattr, parent):
        if ET.iselement(member) and member.tag == 'memberdef':
            return True
        return False

    def import_object(self):
        xpath_query = './/compoundname[text()="%s"]/../sectiondef[@kind="public-func"]/memberdef[@kind="function"]/name[text()="%s"]/..' % (self.modname, self.objpath)
        #print('DoxygenMethodDocumenter import_object')
        #print('  xpath', xpath_query)
        self.object = get_doxygen_root().xpath(xpath_query)[0]
        #print('  setting self.object', self.object)
        return True

    def resolve_name(self, modname, parents, path, base):
        if modname is None:
            if path:
                mod_cls = path.rstrip('.')
            else:
                mod_cls = None
                # if documenting a class-level object without path,
                # there must be a current class, either from a parent
                # auto directive ...
                mod_cls = self.env.temp_data.get('autodoc:class')
                # ... or from a class directive
                if mod_cls is None:
                    mod_cls = str(self.env.ref_context.get('cpp:lastname'))
                # ... if still None, there's no way to know
                if mod_cls is None:
                    return None, []
            modname, cls = rpartition(mod_cls, '.')
            parents = [cls]

        #print('DoxygenMethodDocumenter.resolve_name')
        #print('  modname', modname)
        #print('  parents', parents)
        #print('  path', path)
        #print('  base', base)
        return '::'.join(filter(lambda x: len(x)> 1,
            [modname] + parents)), base
        #return modname + '::' + '::'.join(parents), base

    def get_doc(self, encoding):
        detaileddescription = self.object.find('detaileddescription')
        doc = [DoxygenNodeVisitor().generic_visit(detaileddescription).lines]
        return doc

    def format_name(self):
        rtype = self.object.find('type').text
        return (rtype and (rtype + ' ') or '') + self.modname + '::' + self.objpath

    def format_signature(self):
        args = self.object.find('argsstring').text
        return args

    def document_members(self, all_members=False):
        pass
