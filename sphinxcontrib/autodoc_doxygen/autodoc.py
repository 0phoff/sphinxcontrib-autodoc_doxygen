from __future__ import print_function, absolute_import, division

import re
from six import itervalues
from lxml import etree as ET
from sphinx.ext.autodoc import Documenter, members_option, ALL
from sphinx.errors import ExtensionError
from docutils.parsers.rst.directives import flag

from . import get_doxygen_root, get_auto_defaults
from .xmlutils import format_xml_paragraph, text, tail

# Add regular expressions to xpath
ET.FunctionNamespace("http://exslt.org/regular-expressions").prefix = 're'

class DoxygenDocumenter(Documenter):
    # Variables to store the names of the object being documented. modname and fullname are redundant,
    # and objpath is always the empty list. This is inelegant, but we need to work with the superclass.
    fullname = None  # example: "OpenMM::NonbondedForce" or "OpenMM::NonbondedForce::methodName""
    modname = None   # example: "OpenMM::NonbondedForce" or "OpenMM::NonbondedForce::methodName""
    objname = None   # example: "NonbondedForce"  or "methodName"
    objpath = []     # always the empty list
    object = None    # the xml node for the object

    option_spec = {
        'members': members_option,
    }

    def __init__(self, directive, name, indent=u'', id=None):
        super(DoxygenDocumenter, self).__init__(directive, name, indent)
        if id is not None:
            self.parse_id(id)

    def parse_id(self, id):
        return False

    def parse_name(self):
        """Determine what module to import and what attribute to document.
        Returns True and sets *self.modname*, *self.objname*, *self.fullname*,
        if parsing and resolving was successful.
        """
        # To view the context and order in which all of these methods get called,
        # See, Documenter.generate(). That's the main "entry point" that first
        # calls parse_name(), follwed by import_object(), format_signature(),
        # add_directive_header(), and then add_content() (which calls get_doc())

        # methods in the superclass sometimes use '.' to join namespace/class
        # names with method names, and we don't want that.
        self.name = self.name.replace('.', '::')
        self.fullname = self.name
        self.modname = self.fullname
        self.objpath = []

        if '::' in self.name:
            parts = self.name.split('::')
            self.objname = parts[-1]
        else:
            self.objname = self.name

        return True

    def add_directive_header(self, sig):
        """Add the directive header and options to the generated content."""
        domain = getattr(self, 'domain', 'cpp')
        directive = getattr(self, 'directivetype', self.objtype)
        name = self.format_name()
        sourcename = self.get_sourcename()
        self.add_line(u'.. %s:%s:: %s%s' % (domain, directive, name, sig),
                      sourcename)

    def document_members(self, all_members=False):
        """Generate reST for member documentation.
        If *all_members* is True, do all members, else those given by
        *self.options.members*.
        """
        want_all = all_members or self.options.inherited_members or \
            self.options.members is ALL
        # find out which members are documentable
        members_check_module, members = self.get_object_members(want_all)

        # remove members given by exclude-members
        if self.options.exclude_members:
            members = [(membername, member) for (membername, member) in members
                       if membername not in self.options.exclude_members]

        # document non-skipped members
        memberdocumenters = []
        for (mname, member, isattr) in self.filter_members(members, want_all):
            classes = [cls for cls in itervalues(self.env.app.registry.documenters)
                       if cls.can_document_member(member, mname, isattr, self)]
            if not classes:
                # don't know how to document this member
                continue

            # prefer the documenter with the highest priority
            classes.sort(key=lambda cls: cls.priority)

            documenter = classes[-1](self.directive, mname, indent=self.indent, id=member.get('id'))
            memberdocumenters.append((documenter, isattr))

        for documenter, isattr in memberdocumenters:
            documenter.generate(
                all_members=True, real_modname=self.real_modname,
                check_module=members_check_module and not isattr)

        # reset current objects
        self.env.temp_data['autodoc:module'] = None
        self.env.temp_data['autodoc:class'] = None

    def get_doc(self):
        detaileddescription = self.object.find('detaileddescription')
        doc = [format_xml_paragraph(detaileddescription)]
        return doc

    def get_brief(self):
        briefdescription = self.object.find('briefdescription')
        if briefdescription is None:
            return None

        brief = [format_xml_paragraph(briefdescription)]
        return brief


class DoxygenClassDocumenter(DoxygenDocumenter):
    objtype = 'doxyclass'
    directivetype = 'class'
    domain = 'cpp'
    priority = 100

    @classmethod
    def can_document_member(cls, member, membername, isattr, parent):
        # this method is only called from Documenter.document_members
        # when a higher level documenter (module or namespace) is trying
        # to choose the appropriate documenter for each of its lower-level
        # members. Currently not implemented since we don't have a higher-level
        # doumenter like a DoxygenNamespaceDocumenter.
        return False
    
    def import_object(self):
        """Import the object and set it as *self.object*.  In the call sequence, this
        is executed right after parse_name(), so it can use *self.fullname*, *self.objname*,
        and *self.modname*.
        Returns True if successful, False if an error occurred.
        """
        xpath_query = './/compoundname[text()="%s"]/..' % self.fullname
        match = get_doxygen_root().xpath(xpath_query)
        if len(match) != 1:
            raise ExtensionError(
                '[autodoc_doxygen] could not find class (fullname="%s"). I tried the following xpath: "%s"'
                % (self.fullname, xpath_query)
            )

        self.object = match[0]
        return True

    def format_signaure(self):
        return ''

    def format_name(self):
        return self.fullname

    def get_object_members(self, want_all):
        all_members = self.object.xpath(
            './/sectiondef[@kind="public-func" '
            'or @kind="public-static-func"]/memberdef[@kind="function"]'
        )

        if want_all:
            return False, ((m.find('name').text, m) for m in all_members)
        else:
            if not self.options.members:
                return False, []
            else:
                return False, ((m.find('name').text, m) for m in all_members
                               if m.find('name').text in self.options.members)

    def filter_members(self, members, want_all):
        ret = []
        for (membername, member) in members:
            ret.append((membername, member, False))
        return ret


class DoxygenMethodDocumenter(DoxygenDocumenter):
    objtype = 'doxymethod'
    directivetype = 'function'
    domain = 'cpp'
    priority = 100
    xpath_base = './/compoundname[text()="%s"]/../sectiondef[@kind="public-func" or @kind="public-static-func"]/memberdef[@kind="function"]'
    option_spec = {
        'members': members_option,
        'return': str,
        'args': str,
        'defaults': flag,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.re_angle_open = (re.compile(r'<([^ <>])'), r'< \1')
        self.re_angle_close = (re.compile(r'([^ <>])>'), r'\1 >')
        self.re_split_args = re.compile(",(?![^<>]*>)")

    @classmethod
    def can_document_member(cls, member, membername, isattr, parent):
        if ET.iselement(member) and member.tag == 'memberdef' and member.get('kind') == 'function':
            return True
        return False

    def parse_id(self, id):
        xp = './/*[@id="%s"]' % id
        match = get_doxygen_root().xpath(xp)
        if len(match) > 0:
            match = match[0]
            self.fullname = match.find('./definition').text.split()[-1]
            self.modname = self.fullname
            self.objname = match.find('./name').text
            self.object = match
        return False

    def import_object(self):
        if ET.iselement(self.object):
            # self.object already set from DoxygenDocumenter.parse_name(),
            # caused by passing in the `id` of the node instead of just a
            # classname or method name
            return True

        compound, method = self.fullname.rsplit('::', 1)
        if {'return', 'args'} <= self.directive.genopt.keys():
            ret = self.re_angle_open[0].sub(
                self.re_angle_open[1],
                self.re_angle_close[0].sub(
                    self.re_angle_close[1],
                    self.directive.genopt['return']
                )
            )
            args = self.re_angle_open[0].sub(
                self.re_angle_open[1],
                self.re_angle_close[0].sub(
                    self.re_angle_close[1],
                    self.directive.genopt['args']
                )
            )
            args = '.*,'.join(self.re_split_args.split(args))

            xpath_query = (
                self.xpath_base +
                '[definition[text()="%s %s::%s"] and re:test(argsstring/text(), "(%s)")]'
            ) % (compound, ret, compound, method, args)
        elif 'return' in self.directive.genopt.keys():
            ret = self.re_angle_open[0].sub(
                self.re_angle_open[1],
                self.re_angle_close[0].sub(
                    self.re_angle_close[1],
                    self.directive.genopt['return']
                )
            )
            xpath_query = (
                self.xpath_base +
                '[definition/text()="%s %s::%s"]'
            ) % (compound, ret, compound, method)
        elif 'args' in self.directive.genopt.keys():
            args = self.re_angle_open[0].sub(
                self.re_angle_open[1],
                self.re_angle_close[0].sub(
                    self.re_angle_close[1],
                    self.directive.genopt['args']
                )
            )
            args = '.*,'.join(self.re_split_args.split(args))
            xpath_query = (
                self.xpath_base +
                '[name[text()="%s"] and re:test(argsstring/text(), "(%s)")]'
            ) % (compound, method, args)
        else:
            xpath_query = (
                self.xpath_base +
                '[name[text()="%s"]]'
            ) % (compound, method)

        match = get_doxygen_root().xpath(xpath_query)
        if len(match) == 0:
            raise ExtensionError('[autodoc_doxygen] could not find %s: %s. I tried following query:\n%s' % (self.objtype, self.fullname, xpath_query))
        self.object = match[0]

        return True

    def format_name(self):
        rtype_el = self.object.find('type')
        rtype_el_ref = rtype_el.find('ref')
        if rtype_el_ref is not None:
            rtype = text(rtype_el) + text(rtype_el_ref) + tail(rtype_el_ref) + ' '
        else:
            rtype = rtype_el.text + ' ' if rtype_el.text else ''

        static = 'static ' if self.object.getparent().get('kind') == 'public-static-func' else ''
        signame = static + rtype + self.objname
        return self.format_template_name() + signame

    def format_template_name(self):
        types = [e.text for e in self.object.findall('templateparamlist/param/type')]
        if len(types) == 0:
            return ''
        return 'template <%s>\n' % ','.join(types)

    def format_signature(self):
        auto_defaults = get_auto_defaults()
        defaults = 'defaults' in self.directive.genopt
        params = self.object.findall('param')
        
        result = ''
        for p in params:
            type = p.find('type')
            type_ref = type.find('ref')
            declname = p.findtext('declname')
            defval = p.findtext('defval')
        
            if type_ref is not None:
                result += text(type) + text(type_ref) + tail(type_ref)
            else:
                result += type.text
            if declname:
                result += ' ' + declname
            if (defaults != auto_defaults) and defval:
                result += ' = ' + defval
            result += ', '
        
        return '(' + result[:-2] + ')'

    def document_members(self, all_members=False):
        pass


class DoxygenFunctionDocumenter(DoxygenMethodDocumenter):
    objtype = 'doxyfunction'
    directivetype = 'function'
    domain = 'cpp'
    priority = 100
    xpath_base = './/compoundname[text()="%s"]/../sectiondef[@kind="func"]/memberdef[@kind="function"]'
    option_spec = {
        'return': str,
        'args': str,
        'defaults': flag,
    }
